# TODO maybe move me to boa/vyper/

import contextlib
import copy
import textwrap
import warnings
from typing import Any

import eth_abi as abi
import vyper
import vyper.ast as vy_ast
import vyper.compiler.output as compiler_output
import vyper.ir.compile_ir as compile_ir
import vyper.semantics.namespace as vy_ns
import vyper.semantics.validation as validation
from eth_utils import to_canonical_address, to_checksum_address
from vyper.ast.signatures.function_signature import FunctionSignature
from vyper.ast.utils import parse_to_ast
from vyper.codegen.core import calculate_type_for_external_return, getpos
from vyper.codegen.function_definitions.common import generate_ir_for_function
from vyper.codegen.ir_node import IRnode
from vyper.codegen.module import parse_external_interfaces
from vyper.codegen.types.types import MappingType, TupleType
from vyper.exceptions import InvalidType, VyperException
from vyper.ir.optimizer import optimize
from vyper.semantics.validation.data_positions import set_data_positions
from vyper.semantics.validation.utils import get_exact_type_from_node
from vyper.utils import abi_method_id, cached_property

from boa.env import AddressT, Env, to_int
from boa.vyper.decoder_utils import ByteAddressableStorage, decode_vyper_object


# build a reverse map from the format we have in pc_pos_map to AST nodes
def ast_map_of(ast_node):
    ast_map = {}
    nodes = [ast_node] + ast_node.get_descendants(reverse=True)
    for node in nodes:
        ast_map[getpos(node)] = node
    return ast_map


# error messages for external calls
EXTERNAL_CALL_ERRORS = ("external call failed", "returndatasize too small")


# id used internally for method id name
_METHOD_ID_VAR = "_calldata_method_id"


class lrudict(dict):
    def __init__(self, n, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.n = n

    def __getitem__(self, k):
        val = super().__getitem__(k)
        del self[k]
        super().__setitem__(k, val)
        return val

    def __setitem__(self, k, val):
        if len(self) == self.n:
            del self[next(iter(self))]
        super().__setitem__(k, val)


class VyperDeployer:
    def __init__(self, compiler_data, env=None):
        self.compiler_data = compiler_data

    def deploy(self, *args, **kwargs):
        return VyperContract(self.compiler_data, *args, **kwargs)

    def deploy_as_blueprint(self, *args, **kwargs):
        return VyperBlueprint(self.compiler_data, *args, **kwargs)

    def at(self, address: AddressT) -> "VyperContract":
        address = to_checksum_address(address)
        ret = VyperContract(
            self.compiler_data, override_address=address, skip_init=True
        )
        vm = ret.env.vm
        bytecode = vm.state.get_code(to_canonical_address(address))

        ret._set_bytecode(bytecode)
        return ret


# a few lines of shared code between VyperBlueprint and VyperContract
class _BaseContract:
    def __init__(self, compiler_data, env=None, override_address=None):
        self.compiler_data = compiler_data

        if env is None:
            env = Env.get_singleton()

        self.env = env
        if override_address is None:
            self.address = self.env.generate_address()
        else:
            self.address = override_address


# create a blueprint for use with `create_from_blueprint`.
# uses a ERC5202 preamble, when calling `create_from_blueprint` will
# need to use `code_offset=3`
class VyperBlueprint(_BaseContract):
    def __init__(
        self,
        compiler_data,
        env=None,
        override_address=None,
        blueprint_preamble=b"\xFE\x71\x00",
    ):
        # note slight code duplication with VyperContract ctor,
        # maybe use common base class?
        super().__init__(compiler_data, env, override_address)

        if blueprint_preamble is None:
            blueprint_preamble = b""

        blueprint_bytecode = blueprint_preamble + compiler_data.bytecode

        # the length of the deployed code in bytes
        len_bytes = len(blueprint_bytecode).to_bytes(2, "big")
        deploy_bytecode = b"\x61" + len_bytes + b"\x3d\x81\x60\x0a\x3d\x39\xf3"

        deploy_bytecode += blueprint_bytecode

        self.bytecode = self.env.deploy_code(
            bytecode=deploy_bytecode, deploy_to=self.address
        )


class FrameDetail(dict):
    def __init__(self, fn_name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fn_name = fn_name

    def __repr__(self):
        detail = ", ".join(f"{k}={v}" for (k, v) in self.items())
        return f"<{self.fn_name}: {detail}>"


class StackTrace(list):
    def __repr__(self):
        return "\n".join(repr(x) for x in self)


def unwrap_storage_key(sha3_db, k):
    path = []

    def unwrap(k):
        if k in sha3_db:
            preimage = sha3_db[k]
            slot, k = preimage[:32], preimage[32:]

            unwrap(slot)

        path.append(k)

    unwrap(k)
    return path


def setpath(lens, path, val):
    for i, k in enumerate(path):
        if i == len(path) - 1:
            lens[k] = val
        else:
            lens = lens.setdefault(k, {})


class VarModel:
    def __init__(self, contract, slot, typ):
        self.contract = contract
        self.addr = to_canonical_address(self.contract.address)
        self.accountdb = contract.env.vm.state._account_db
        self.slot = slot
        self.typ = typ

    def _decode(self, slot, typ):
        fakemem = ByteAddressableStorage(self.accountdb, self.addr, slot)
        return decode_vyper_object(fakemem, typ)

    def _dealias(self, maybe_address):
        try:
            return self.contract.env.lookup_alias(maybe_address)
        except:  # not found, return the input
            return maybe_address

    def get(self):
        if isinstance(self.typ, MappingType):
            ret = {}
            for k in self.contract.env.sstore_trace.get(self.contract.address, {}):
                path = unwrap_storage_key(self.contract.env.sha3_trace, k)
                if to_int(path[0]) != self.slot:
                    continue

                path = path[1:]

                ty = self.typ
                for i, p in enumerate(path):
                    path[i] = decode_vyper_object(memoryview(p), ty.keytype)
                    ty = ty.valuetype

                val = self._decode(to_int(k), ty)

                if val:
                    # decode aliases
                    path = [self._dealias(p) for p in path]
                    setpath(ret, path, val)
            return ret

        else:
            return self._decode(self.slot, self.typ)


# data structure to represent the storage variables in a contract
class StorageModel:
    def __init__(self, contract):
        compiler_data = contract.compiler_data
        for k, v in compiler_data.global_ctx._globals.items():
            is_storage = not v.is_immutable
            if is_storage:  # check that v
                slot = compiler_data.storage_layout["storage_layout"][k]["slot"]
                setattr(self, k, VarModel(contract, slot, v.typ))


class VyperContract(_BaseContract):
    def __init__(
        self, compiler_data, *args, env=None, override_address=None, skip_init=False
    ):
        super().__init__(compiler_data, env, override_address)

        self.env.register_contract(self.address, self)

        fns = {fn.name: fn for fn in self.global_ctx._function_defs}
        # add all functions from the interface to the contract

        self._ctor = None
        if "__init__" in fns:
            self._ctor = VyperFunction(fns.pop("__init__"), self)

        for fn in fns.values():
            setattr(self, fn.name, VyperFunction(fn, self))

        self._storage = StorageModel(self)

        self._eval_cache = lrudict(0x1000)
        self._source_map = None
        self._computation = None

        if not skip_init:
            self._run_init(*args)

    def _run_init(self, *args):
        encoded_args = b""

        if self._ctor:
            encoded_args = self._ctor._prepare_calldata(*args)
            encoded_args = encoded_args[4:]  # strip method_id

        initcode = self.compiler_data.bytecode + encoded_args
        self.bytecode = self.env.deploy_code(bytecode=initcode, deploy_to=self.address)

    # manually set the runtime bytecode, instead of using deploy
    def _set_bytecode(self, bytecode: bytes) -> None:
        if bytecode[-self.data_section_size :] != self.compiler_data.bytecode_runtime:
            warnings.warn(f"casted bytecode does not match compiled bytecode at {self}")
        self.bytecode = bytecode

    def __str__(self):
        return (
            f"<{self.compiler_data.contract_name} at {to_checksum_address(self.address)}, "
            f"compiled with vyper-{vyper.__version__}+{vyper.__commit__}>"
        )

    @cached_property
    def deployer(self):
        return VyperDeployer(self.compiler_data, env=self.env)

    # is this actually useful?
    def at(self, *args, **kwargs):
        return self.deployer.wrap(*args, **kwargs)

    @cached_property
    def ast_map(self):
        return ast_map_of(self.compiler_data.vyper_module)

    def debug_frame(self, computation=None):
        if computation is None:
            computation = self._computation

        node = self.find_source_of(computation.code)
        if node is None:
            return None

        fn = node.get_ancestor(vy_ast.FunctionDef)

        frame_info = self.compiler_data.function_signatures[fn.name].frame_info

        mem = computation._memory
        frame_detail = FrameDetail(fn.name)
        for k, v in frame_info.frame_vars.items():
            if v.location.name != "memory":
                continue
            ofst = v.pos
            size = v.typ.memory_bytes_required
            frame_detail[k] = decode_vyper_object(mem.read(ofst, size), v.typ)

        return frame_detail

    @property
    def global_ctx(self):
        return self.compiler_data.global_ctx

    @property
    def source_map(self):
        if self._source_map is None:
            _, self._source_map = compile_ir.assembly_to_evm(
                self.compiler_data.assembly_runtime
            )
        return self._source_map

    def find_error_meta(self, code_stream):
        error_map = self.source_map.get("error_map", {})
        for pc in reversed(code_stream._trace):
            if pc in error_map:
                return error_map[pc]
        return None

    def find_source_of(self, code_stream, is_initcode=False):
        pc_map = self.source_map["pc_pos_map"]
        for pc in reversed(code_stream._trace):
            if pc in pc_map and pc_map[pc] in self.ast_map:
                return self.ast_map[pc_map[pc]]

        return None

    def marshal_to_python(self, computation, vyper_typ):
        self._computation = computation  # for further inspection

        if computation.is_error:
            self.handle_error(computation)

        if vyper_typ is None:
            return None

        return_typ = calculate_type_for_external_return(vyper_typ)
        ret = abi.decode_single(return_typ.abi_type.selector_name(), computation.output)

        # unwrap the tuple if needed
        if not isinstance(vyper_typ, TupleType):
            (ret,) = ret

        return vyper_object(ret, vyper_typ)

    def handle_error(self, computation):
        err = computation.error

        # decode error msg if it's "Error(string)"
        # b"\x08\xc3y\xa0" == method_id("Error(string)")
        if isinstance(err.args[0], bytes) and err.args[0][:4] == b"\x08\xc3y\xa0":
            err.args = (
                abi.decode_single("(string)", err.args[0][4:])[0],
                *err.args[1:],
            )

        error_msg = f"{repr(computation.error)} "

        stack_trace = self.vyper_stack_trace(computation)

        for (c, computation) in stack_trace:
            error_msg += f"\n\n{c}\n"

            error_detail = self.find_error_meta(computation.code)
            if error_detail is not None:
                error_msg += f" <dev: {error_detail}>"

            ast_source = c.find_source_of(computation.code)
            if ast_source is not None:
                # VyperException.__str__ does a lot of formatting for us
                error_msg = str(VyperException(error_msg, ast_source))

            frame_detail = c.debug_frame(computation)
            if frame_detail is not None:
                frame_detail.fn_name = "locals"  # override the displayed name
                if len(frame_detail) > 0:
                    error_msg += f" {frame_detail}"

        raise BoaError(error_msg)

    def vyper_stack_trace(self, computation):
        ret = [(self, computation)]
        error_detail = self.find_error_meta(computation.code)
        if error_detail not in EXTERNAL_CALL_ERRORS:
            return ret
        if len(computation.children) < 1:
            return ret
        if not computation.children[-1].is_error:
            return ret
        child = computation.children[-1]
        child_obj = self.env.lookup_contract(child.msg.code_address)
        child_trace = child_obj.vyper_stack_trace(child)
        return child_trace + ret

    # eval vyper code in the context of this contract
    def eval(self, stmt: str) -> Any:
        tmp = self._source_map

        bytecode, source_map, typ = self.compile_stmt(stmt)
        self._source_map = source_map

        method_id = b"dbug"  # note dummy method id, doesn't get validated
        c = self.env.execute_code(
            to_address=self.address, bytecode=bytecode, data=method_id
        )

        ret = self.marshal_to_python(c, typ)

        self._source_map = tmp  # restore

        return ret

    @cached_property
    def _ast_module(self):
        module = copy.deepcopy(self.compiler_data.vyper_module)

        # do the same thing as vyper_module_folded but skip getter expansion
        vy_ast.folding.fold(module)
        with vy_ns.get_namespace().enter_scope():
            validation.add_module_namespace(module, self.compiler_data.interface_codes)
            validation.validate_functions(module)
            # we need to cache the namespace right here(!).
            # set_data_positions will modify the type definitions in place.
            self._cache_namespace(vy_ns.get_namespace())

        vy_ast.expansion.remove_unused_statements(module)
        # calculate slots for all storage variables, tagging
        # the types in the namespace.
        set_data_positions(module, storage_layout_overrides=None)

        return module

    # the global namespace is expensive to compute, so cache it
    def _cache_namespace(self, namespace):
        # copy.copy doesn't really work on Namespace objects, copy by hand
        ret = vy_ns.Namespace()
        ret._scopes = copy.deepcopy(namespace._scopes)
        for s in namespace._scopes:
            for n in s:
                ret[n] = namespace[n]
        self._vyper_namespace = ret

    @contextlib.contextmanager
    def override_vyper_namespace(self):
        # ensure self._vyper_namespace is computed
        m = self._ast_module  # noqa: F841
        try:
            with vy_ns.override_global_namespace(self._vyper_namespace):
                yield
        finally:
            self._vyper_namespace["self"].members.pop("__boa_debug__", None)

    # for eval(), we need unoptimized assembly, since the dead code
    # eliminator might prune a dead function (which we want to eval)
    @cached_property
    def unoptimized_assembly(self):
        runtime = self.compiler_data.ir_runtime
        return compile_ir.compile_to_assembly(runtime, no_optimize=True)

    @cached_property
    def data_section_size(self):
        return self.global_ctx.immutable_section_bytes

    @cached_property
    def data_section(self):
        # extract the data section from the bytecode
        if self.data_section_size:
            return self.bytecode[-self.data_section_size :]
        else:
            return b""

    @cached_property
    def unoptimized_bytecode(self):
        s, _ = compile_ir.assembly_to_evm(
            self.unoptimized_assembly, insert_vyper_signature=True
        )
        return s + self.data_section

    # compile a fragment (single expr or statement) in the context
    # of the contract, returning the ABI encoded value if it is an expr.
    def compile_stmt(self, source_code: str) -> Any:
        # this method is super slow so we cache compilation results
        if source_code in self._eval_cache:
            return self._eval_cache[source_code]

        ast = parse_to_ast(source_code)
        vy_ast.folding.fold(ast)
        ast = ast.body[0]

        typ = None
        return_sig = ""
        debug_body = source_code

        ifaces = self.compiler_data.interface_codes

        if isinstance(ast, vy_ast.Expr):
            with self.override_vyper_namespace():
                try:
                    typ = get_exact_type_from_node(ast.value)
                    return_sig = f"-> {typ}"
                    debug_body = f"return {source_code}"
                except InvalidType:
                    pass

        # wrap code in function so that we can easily generate code for it
        wrapper_code = textwrap.dedent(
            f"""
            @external
            @payable
            def __boa_debug__() {return_sig}:
                {debug_body}
        """
        )

        ast = parse_to_ast(wrapper_code, ifaces)
        vy_ast.folding.fold(ast)

        # annotate ast
        with self.override_vyper_namespace():
            validation.add_module_namespace(ast, self.compiler_data.interface_codes)
            validation.validate_functions(ast)

        ast = ast.body[0]

        sig = FunctionSignature.from_definition(ast, self.global_ctx)
        ast._metadata["signature"] = sig

        sigs = {"self": self.compiler_data.function_signatures}
        ir = generate_ir_for_function(ast, sigs, self.global_ctx, False)
        # generate bytecode where selector check always succeeds
        ir = IRnode.from_list(
            ["with", _METHOD_ID_VAR, abi_method_id(sig.base_signature), ir]
        )

        # skip optimizing; we will optimize a couple lines down anyway
        assembly = compile_ir.compile_to_assembly(ir, no_optimize=True)

        # add original assembly in so that jumpdests in the fragment
        # assemble correctly in final bytecode
        # note this is somewhat kludgy
        assembly.extend(self.unoptimized_assembly)

        # note: optimize_assembly optimizes in place.
        compile_ir._optimize_assembly(assembly)

        bytecode, source_map = compile_ir.assembly_to_evm(assembly)

        # tack on the data section
        bytecode += self.data_section

        # return the bytecode and other artifacts associated with
        # this build
        ret = bytecode, source_map, typ
        self._eval_cache[source_code] = ret
        return ret

    @cached_property
    def _sigs(self):
        sigs = {}
        global_ctx = self.compiler_data.global_ctx
        if global_ctx._contracts or global_ctx._interfaces:
            sigs = parse_external_interfaces(sigs, global_ctx)
        sigs["self"] = self.compiler_data.function_signatures
        return sigs


# inherit from VyperException for pretty tracebacks
class BoaError(VyperException):
    pass


class VyperFunction:
    def __init__(self, fn_ast, contract):
        self.fn_ast = fn_ast
        self.contract = contract
        self.env = contract.env

    def __repr__(self):
        return repr(self.fn_ast)

    @cached_property
    def fn_signature(self):
        return self.contract.compiler_data.function_signatures[self.fn_ast.name]

    @cached_property
    def ir(self):
        # patch compiler_data to have IR for every function
        sigs = self.contract._sigs
        global_ctx = self.contract.global_ctx

        ir = generate_ir_for_function(self.fn_ast, sigs, global_ctx, False)
        return optimize(ir)

    @cached_property
    def assembly(self):
        ir = IRnode.from_list(
            ["with", _METHOD_ID_VAR, ["shr", 224, ["calldataload", 0]], self.ir]
        )
        return compile_ir.compile_to_assembly(ir)

    @cached_property
    def opcodes(self):
        return compiler_output._build_opcodes(self.bytecode)

    @cached_property
    def bytecode(self):
        bytecode, _ = compile_ir.assembly_to_evm(self.assembly)
        return bytecode

    # hotspot, cache the signature computation
    def args_abi_type(self, num_kwargs):
        if not hasattr(self, "_signature_cache"):
            self._signature_cache = {}
        if num_kwargs in self._signature_cache:
            return self._signature_cache[num_kwargs]

        # align the kwargs with the signature
        sig_kwargs = self.fn_signature.default_args[:num_kwargs]
        sig_args = self.fn_signature.base_args + sig_kwargs
        args_abi_type = (
            "(" + ",".join(arg.typ.abi_type.selector_name() for arg in sig_args) + ")"
        )
        method_id = abi_method_id(self.fn_signature.name + args_abi_type).to_bytes(
            4, "big"
        )
        self._signature_cache[num_kwargs] = (method_id, args_abi_type)

        return method_id, args_abi_type

    def _prepare_calldata(self, *args, **kwargs):
        if (
            not len(self.fn_signature.base_args)
            <= len(args)
            <= len(self.fn_signature.args)
        ):
            raise Exception(f"bad args to {self}")

        # align the kwargs with the signature
        # sig_kwargs = self.fn_signature.default_args[: len(kwargs)]

        total_non_base_args = len(kwargs) + len(args) - len(self.fn_signature.base_args)
        method_id, args_abi_type = self.args_abi_type(total_non_base_args)

        # allow things with `.address` to be encode-able
        args = [getattr(arg, "address", arg) for arg in args]

        encoded_args = abi.encode_single(args_abi_type, args)
        return method_id + encoded_args

    def __call__(self, *args, **kwargs):
        calldata_bytes = self._prepare_calldata(*args, **kwargs)
        computation = self.env.execute_code(
            to_address=self.contract.address,
            bytecode=self.contract.bytecode,
            data=calldata_bytes,
        )

        typ = self.fn_signature.return_type
        return self.contract.marshal_to_python(computation, typ)


_typ_cache = {}


def vyper_object(val, vyper_type):
    # make a thin wrapper around whatever type val is,
    # and tag it with _vyper_type metadata

    vt = type(val)
    if vt is bool:
        # https://stackoverflow.com/q/2172189
        # bool is not ambiguous wrt vyper type anyways.
        return val

    if vt not in _typ_cache:
        # ex. class int_wrapper(int): pass
        _typ_cache[vt] = type(f"{vt.__name__}_wrapper", (vt,), {})

    t = _typ_cache[type(val)]

    ret = t(val)
    ret._vyper_type = vyper_type
    return ret
