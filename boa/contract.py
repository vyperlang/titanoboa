# TODO maybe move me to boa/vyper/

import contextlib
import copy
import textwrap
from typing import Any

import eth_abi as abi
import vyper.ast as vy_ast
import vyper.codegen.function_definitions.common as vyper
import vyper.codegen.module as mod
import vyper.ir.compile_ir as compile_ir
import vyper.semantics.namespace as vy_ns
import vyper.semantics.validation as validation
from vyper.ast.signatures.function_signature import FunctionSignature
from vyper.ast.utils import parse_to_ast
from vyper.codegen.core import calculate_type_for_external_return, getpos
from vyper.codegen.ir_node import IRnode
from vyper.codegen.types.types import TupleType
from vyper.exceptions import InvalidType, VyperException
from vyper.semantics.validation.data_positions import set_data_positions
from vyper.semantics.validation.utils import get_exact_type_from_node
from vyper.utils import abi_method_id, cached_property

from boa.env import Env
from boa.vyper.decoder_utils import decode_vyper_object


# build a reverse map from the format we have in pc_pos_map to AST nodes
def ast_map_of(ast_node):
    ast_map = {}
    nodes = [ast_node] + ast_node.get_descendants(reverse=True)
    for node in nodes:
        ast_map[getpos(node)] = node
    return ast_map


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
    def __init__(self, compiler_data):
        self.compiler_data = compiler_data

    def deploy(self, *args, **kwargs):
        return VyperContract(self.compiler_data, *args, **kwargs)

    def deploy_as_factory(self, *args, **kwargs):
        return VyperFactory(self.compiler_data, *args, **kwargs)


# a few lines of shared code between VyperFactory and VyperContract
class _T:
    def __init__(self, compiler_data, env=None, override_address=None):
        self.compiler_data = compiler_data

        if env is None:
            env = Env.get_singleton()

        self.env = env
        if override_address is None:
            self.address = self.env.generate_address()
        else:
            self.address = override_address


# create a factory for use with `create_from_factory`.
# uses a ERC5202 preamble, when calling `create_from_factory` will
# need to use `code_offset=3`
class VyperFactory:
    def __init__(
        self,
        compiler_data,
        env=None,
        override_address=None,
        factory_preamble=b"\xFE\x71\x00",
    ):
        # note slight code duplication with VyperContract ctor,
        # maybe use common base class?
        super().__init__(compiler_data, env, override_address)

        if factory_preamble is None:
            factory_preamble = b""

        factory_bytecode = factory_preamble + compiler_data.bytecode

        # the length of the deployed code in bytes
        len_bytes = len(factory_bytecode).to_bytes(2, "big")
        deploy_bytecode = b"\x61" + len_bytes + b"\x3d\x81\x60\x0a\x3d\x39\xf3"

        deploy_bytecode += factory_bytecode

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


class VyperContract(_T):
    def __init__(self, compiler_data, *args, env=None, override_address=None):
        super().__init__(compiler_data, env, override_address)

        encoded_args = b""

        fns = {fn.name: fn for fn in self.global_ctx._function_defs}

        if "__init__" in fns:
            ctor = VyperFunction(fns.pop("__init__"), self)
            encoded_args = ctor._prepare_calldata(*args)
            encoded_args = encoded_args[4:]  # strip method_id

        self.bytecode = self.env.deploy_code(
            bytecode=self.compiler_data.bytecode + encoded_args, deploy_to=self.address
        )

        # add all functions from the interface to the contract
        for fn in fns.values():
            setattr(self, fn.name, VyperFunction(fn, self))

        self._eval_cache = lrudict(0x1000)
        self._source_map = None
        self._computation = None
        self._fn = None

    @cached_property
    def ast_map(self):
        return ast_map_of(self.compiler_data.vyper_module)

    def debug_frame(self):
        if self._fn is None:
            raise Exception("No frame available")

        frame_info = self._fn.fn_signature.frame_info

        mem = self._computation._memory
        frame_detail = FrameDetail(self._fn.fn_signature.name)
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

    # run a bytecode fragment in the context of the contract,
    # maintaining PCs and CODESIZE semantics
    def _run_bytecode(self, fragment: bytes, calldata_bytes: bytes = b"") -> Any:
        bytecode = self.unoptimized_bytecode + fragment
        fake_codesize = len(self.unoptimized_bytecode)
        method_id = b"dbug"  # note the value doesn't get validated
        computation = self.env.execute_code(
            to_address=self.address,
            bytecode=bytecode,
            data=method_id + calldata_bytes,
            fake_codesize=fake_codesize,
            start_pc=fake_codesize,
        )
        return computation

    def marshal_to_python(self, computation, vyper_typ):
        self._computation = computation  # for further inspection

        if computation.is_error:
            error_msg = f"{repr(computation.error)}"
            error_detail = self.find_error_meta(computation.code)
            if error_detail is not None:
                error_msg = f"{error_msg} <dev: {error_detail}>"
            ast_source = self.find_source_of(computation.code)
            raise BoaError(error_msg, ast_source)

        if vyper_typ is None:
            return None

        return_typ = calculate_type_for_external_return(vyper_typ)
        ret = abi.decode_single(return_typ.abi_type.selector_name(), computation.output)

        # unwrap the tuple if needed
        if not isinstance(vyper_typ, TupleType):
            (ret,) = ret

        return vyper_object(ret, vyper_typ)

    # eval vyper code in the context of this contract
    def eval(self, stmt: str) -> Any:
        bytecode, source_map, typ = self.compile_stmt(stmt)

        self._source_map = source_map

        c = self._run_bytecode(bytecode)
        self._fn = None

        return self.marshal_to_python(c, typ)

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

    @cached_property
    def unoptimized_assembly(self):
        _, runtime, _ = mod.generate_ir_for_module(self.global_ctx)
        return compile_ir.compile_to_assembly(runtime, no_optimize=True)

    @cached_property
    def data_section(self):
        # extract the data section from the bytecode
        return self.bytecode[len(self.compiler_data.bytecode_runtime) :]

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
        ir = vyper.generate_ir_for_function(ast, sigs, self.global_ctx, False)

        # generate bytecode where selector check always succeeds
        ir = IRnode.from_list(
            ["with", "_calldata_method_id", abi_method_id(sig.base_signature), ir]
        )

        assembly = compile_ir.compile_to_assembly(ir)

        # add original bytecode in so that jumpdests in the fragment
        # assemble correctly in final bytecode
        # note this is somewhat kludgy, would be better to be able to
        # pass around the assembly "symbol table"
        vyper_signature_len = len("\xa1\x65vyper\x83\x00\x03\x04")
        # we need to use unoptimized assembly of the contract because
        # otherwise dead code eliminator can strip unused internal functions
        assembly = self.unoptimized_assembly + ["POP"] * vyper_signature_len + assembly

        n_padding = len(self.unoptimized_bytecode)
        bytecode, source_map = compile_ir.assembly_to_evm(assembly)
        bytecode = bytecode[n_padding:]

        # return the source_map since the evaluator might want
        # the error map for this stmt
        ret = bytecode, source_map, typ
        self._eval_cache[source_code] = ret
        return ret


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
        self.contract._fn = self
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
