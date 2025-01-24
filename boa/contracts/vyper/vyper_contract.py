# the main "entry point" of vyper-related functionality like
# AST handling, traceback construction and ABI (marshaling
# and unmarshaling vyper objects)

import contextlib
import copy
import warnings
from collections import namedtuple
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any, Optional

import vyper
import vyper.ast as vy_ast
import vyper.ir.compile_ir as compile_ir
import vyper.semantics.namespace as vy_ns
from eth.exceptions import VMError
from vyper.ast.nodes import VariableDecl
from vyper.ast.parse import parse_to_ast
from vyper.codegen.core import calculate_type_for_external_return
from vyper.codegen.function_definitions import (
    generate_ir_for_external_function,
    generate_ir_for_internal_function,
)
from vyper.codegen.ir_node import IRnode
from vyper.codegen.module import generate_ir_for_module
from vyper.compiler import CompilerData
from vyper.compiler import output as compiler_output
from vyper.compiler.output import build_abi_output, build_solc_json
from vyper.compiler.settings import OptimizationLevel, anchor_settings
from vyper.exceptions import VyperException
from vyper.ir.optimizer import optimize
from vyper.semantics.types import AddressT, DArrayT, HashMapT, SArrayT, StructT, TupleT
from vyper.utils import method_id

from boa import BoaError
from boa.contracts.base_evm_contract import (
    StackTrace,
    _BaseEVMContract,
    _handle_child_trace,
)
from boa.contracts.call_trace import TraceSource
from boa.contracts.event_decoder import decode_log
from boa.contracts.vyper.ast_utils import get_fn_ancestor_from_node, reason_at
from boa.contracts.vyper.compiler_utils import (
    _METHOD_ID_VAR,
    compile_vyper_function,
    generate_bytecode_for_arbitrary_stmt,
    generate_bytecode_for_internal_fn,
)
from boa.contracts.vyper.decoder_utils import (
    ByteAddressableStorage,
    decode_vyper_object,
)
from boa.contracts.vyper.ir_executor import executor_from_ir
from boa.environment import Env
from boa.profiling import cache_gas_used_for_computation
from boa.util.abi import Address, abi_decode, abi_encode
from boa.util.eip1167 import is_eip1167_contract
from boa.util.eip5202 import generate_blueprint_bytecode
from boa.util.lrudict import lrudict
from boa.vm.gas_meters import ProfilingGasMeter
from boa.vm.utils import to_bytes, to_int

# error messages for external calls
EXTERNAL_CALL_ERRORS = ("external call failed", "returndatasize too small")

CREATE_ERRORS = ("create failed", "create2 failed")

# error detail where user possibly provided dev revert reason
DEV_REASON_ALLOWED = ("user raise", "user assert")


class VyperDeployer:
    create_compiler_data = CompilerData  # this may be a different class in plugins

    def __init__(self, compiler_data, filename=None):
        self.compiler_data = compiler_data

        # force compilation so that if there are any errors in the contract,
        # we fail at load rather than at deploy time.
        with anchor_settings(self.compiler_data.settings):
            _ = compiler_data.bytecode, compiler_data.bytecode_runtime

        self.filename = filename

    def __call__(self, *args, **kwargs):
        return self.deploy(*args, **kwargs)

    def deploy(self, *args, **kwargs):
        return VyperContract(
            self.compiler_data, *args, filename=self.filename, **kwargs
        )

    def deploy_as_blueprint(self, *args, **kwargs):
        return VyperBlueprint(
            self.compiler_data, *args, filename=self.filename, **kwargs
        )

    def stomp(self, address: Any, data_section=None) -> "VyperContract":
        address = Address(address)

        ret = self.deploy(override_address=address, skip_initcode=True)
        vm = ret.env.evm
        old_bytecode = vm.get_code(address)
        new_bytecode = self.compiler_data.bytecode_runtime

        immutables_size = self.compiler_data.global_ctx.immutable_section_bytes
        if immutables_size > 0:
            data_section = old_bytecode[-immutables_size:]
            new_bytecode += data_section

        vm.set_code(address, new_bytecode)
        ret.env.register_contract(address, ret)
        ret._set_bytecode(new_bytecode)
        return ret

    # TODO: allow `env=` kwargs and so on
    def at(self, address: Any) -> "VyperContract":
        address = Address(address)

        ret = self.deploy(override_address=address, skip_initcode=True)
        bytecode = ret.env.get_code(address)

        ret._set_bytecode(bytecode)

        ret.env.register_contract(address, ret)
        return ret

    @cached_property
    def solc_json(self):
        """
        Generates a solc "standard json" representation of the Vyper contract.
        """
        return build_solc_json(self.compiler_data)

    @cached_property
    def _constants(self):
        # Make constants available at compile time. Useful for testing. See #196
        return ConstantsModel(self.compiler_data)


# a few lines of shared code between VyperBlueprint and VyperContract
class _BaseVyperContract(_BaseEVMContract):
    def __init__(
        self,
        compiler_data: CompilerData,
        contract_name: Optional[str] = None,
        env: Optional[Env] = None,
        filename: Optional[str] = None,
    ):
        if contract_name is None:
            contract_name = Path(compiler_data.contract_path).stem

        super().__init__(contract_name, env, filename)
        self.compiler_data = compiler_data

        with anchor_settings(self.compiler_data.settings):
            _ = compiler_data.bytecode, compiler_data.bytecode_runtime

        if (capabilities := getattr(env, "capabilities", None)) is not None:
            compiler_evm_version = self.compiler_data.settings.evm_version
            if not capabilities.check_evm_version(compiler_evm_version):
                msg = "EVM version mismatch! tried to deploy "
                msg += f"{compiler_evm_version} but network only has "
                msg += f"{capabilities.describe_capabilities()}"
                raise Exception(msg)

    @cached_property
    def deployer(self):
        return VyperDeployer(self.compiler_data, filename=self.filename)

    @cached_property
    def abi(self):
        return build_abi_output(self.compiler_data)

    @cached_property
    def _constants(self):
        return ConstantsModel(self.compiler_data)


# create a blueprint for use with `create_from_blueprint`.
# uses a ERC5202 preamble, when calling `create_from_blueprint` will
# need to use `code_offset=3`
class VyperBlueprint(_BaseVyperContract):
    def __init__(
        self,
        compiler_data,
        env=None,
        override_address=None,
        blueprint_preamble=None,
        contract_name=None,
        filename=None,
        gas=None,
    ):
        super().__init__(compiler_data, contract_name, env, filename)

        deploy_bytecode = generate_blueprint_bytecode(
            compiler_data.bytecode, blueprint_preamble
        )

        addr, computation = self.env.deploy(
            bytecode=deploy_bytecode, override_address=override_address, gas=gas
        )
        if computation.is_error:
            raise computation.error

        self.bytecode = computation.output

        self._address = Address(addr)

        self.env.register_blueprint(compiler_data.bytecode, self)


class FrameDetail(dict):
    def __init__(self, fn_name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fn_name = fn_name

    def __repr__(self):
        detail = ", ".join(f"{k}={v}" for (k, v) in self.items())
        return f"<{self.fn_name}: {detail}>"


@dataclass
class DevReason:
    reason_type: str
    reason_str: str

    @classmethod
    def at_source_location(
        cls, source_code: str, lineno: int, end_lineno: int
    ) -> Optional["DevReason"]:
        s = reason_at(source_code, lineno, end_lineno)
        if s is None:
            return None
        reason_type, reason_str = s
        return cls(reason_type, reason_str)

    def __str__(self):
        return f"<{self.reason_type}: {self.reason_str}>"


@dataclass
class ErrorDetail:
    vm_error: VMError
    contract_repr: str  # string representation of the contract for the error
    error_detail: str  # compiler provided error detail
    dev_reason: DevReason
    frame_detail: FrameDetail
    ast_source: vy_ast.VyperNode

    @classmethod
    def from_computation(cls, contract, computation):
        error_detail = contract.find_error_meta(computation)
        ast_source = contract.find_source_of(computation)
        reason = None
        if ast_source is not None:
            reason = DevReason.at_source_location(
                ast_source.full_source_code, ast_source.lineno, ast_source.end_lineno
            )
        frame_detail = contract.debug_frame(computation)

        contract_repr = computation._contract_repr_before_revert or repr(contract)
        return cls(
            vm_error=computation.error,
            contract_repr=contract_repr,
            error_detail=error_detail,
            dev_reason=reason,
            frame_detail=frame_detail,
            ast_source=ast_source,
        )

    @property
    def pretty_vm_reason(self):
        err = self.vm_error
        # decode error msg if it's "Error(string)"
        # b"\x08\xc3y\xa0" == method_id("Error(string)")
        if isinstance(err.args[0], bytes) and err.args[0][:4] == b"\x08\xc3y\xa0":
            return abi_decode("(string)", err.args[0][4:])[0]

        return repr(err)

    def __str__(self):
        msg = f"{self.contract_repr}\n"

        if self.error_detail is not None:
            msg += f" <compiler: {self.error_detail}>"

        if self.ast_source is not None:
            # VyperException.__str__ does a lot of formatting for us
            msg = str(VyperException(msg, self.ast_source))

        if self.frame_detail is not None:
            self.frame_detail.fn_name = "locals"  # override the displayed name
            if len(self.frame_detail) > 0:
                msg += f" {self.frame_detail}"

        return msg


# "pattern match" a BoaError. tries to match fields of the error
# to the args/kwargs provided. raises if no match
def check_boa_error_matches(error, *args, **kwargs):
    assert isinstance(error, BoaError)

    def _check(cond, msg=""):
        if not cond:
            raise ValueError(msg)

    frame = error.stack_trace.last_frame
    if len(args) > 0:
        assert len(args) == 1, "multiple args!"
        assert len(kwargs) == 0, "can't mix args and kwargs!"
        err = args[0]
        if isinstance(frame, str):
            # frame for unknown contracts is a string
            _check(err in frame, f"{frame} does not match {args}")
            return

        # try to match anything
        _check(
            err == frame.pretty_vm_reason
            or err == frame.error_detail
            or (frame.dev_reason and err == frame.dev_reason.reason_str),
            f"does not match {args}",
        )
        return

    # try to match a specific kwarg
    assert len(kwargs) == 1 and len(args) == 0

    if isinstance(frame, str):
        # frame for unknown contracts is a string
        raise ValueError(f"expected {kwargs} but got {frame}")

    # don't accept magic
    if frame.dev_reason:
        assert frame.dev_reason.reason_type not in ("vm_error", "compiler")

    k, v = next(iter(kwargs.items()))
    if k == "compiler":
        _check(v == frame.error_detail, f"{frame.error_detail} != {v}")
    elif k == "vm_error":
        _check(
            frame.error_detail == "user revert with reason"
            and v == frame.pretty_vm_reason,
            f"{frame.pretty_vm_reason} != {v}",
        )
    # assume it is a dev reason string
    else:
        assert_ast_types = (vy_ast.Assert, vy_ast.Raise)
        if frame.ast_source.get_ancestor(assert_ast_types) is not None:
            # if it's a dev reason on an assert statement, check that
            # we are actually handling the user assertion and not some other
            # error_detail.
            _check(
                frame.error_detail in DEV_REASON_ALLOWED,
                f"expected <{k}: {v}> but got <compiler: {frame.error_detail}>",
            )
        _check(
            frame.dev_reason is not None
            and k == frame.dev_reason.reason_type
            and v == frame.dev_reason.reason_str,
            f"expected <{k}: {v}> but got {frame.dev_reason}",
        )


# using sha3 preimages, take a storage key and undo
# hashes to get the sequence of hashes ("path") that gave us this image.
def unwrap_storage_key(sha3_db, k):
    path = []

    def unwrap(k):
        k_bytes = to_bytes(k)
        if k_bytes in sha3_db:
            preimage = sha3_db[k_bytes]
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


class StorageVar:
    def __init__(self, contract, slot, typ):
        self.contract = contract
        self.addr = self.contract._address
        self.slot = slot
        self.typ = typ

    def _decode(self, slot, typ, truncate_limit=None):
        n = typ.memory_bytes_required
        if truncate_limit is not None and n > truncate_limit:
            return None  # indicate failure to caller

        fakemem = ByteAddressableStorage(self.contract.env.evm, self.addr, slot)
        return decode_vyper_object(fakemem, typ)

    def _dealias(self, maybe_address):
        try:
            return self.contract.env.lookup_alias(maybe_address)
        except KeyError:  # not found, return the input
            return maybe_address

    def get(self, truncate_limit=None):
        if isinstance(self.typ, HashMapT):
            ret = {}
            for k in self.contract.env.sstore_trace.get(self.addr, {}):
                path = unwrap_storage_key(self.contract.env.sha3_trace, k)
                if to_int(path[0]) != self.slot:
                    continue

                path = path[1:]  # drop the slot
                path_t = []

                ty = self.typ
                for i, p in enumerate(path):
                    path[i] = decode_vyper_object(memoryview(p), ty.key_type)
                    path_t.append(ty.key_type)
                    ty = ty.value_type

                val = self._decode(k, ty, truncate_limit)

                # set val only if value is nonzero
                if val:
                    # decode aliases as needed/possible
                    dealiased_path = []
                    for p, t in zip(path, path_t):
                        if isinstance(t, AddressT):
                            p = self._dealias(p)
                        dealiased_path.append(p)
                    setpath(ret, dealiased_path, val)

            return ret

        else:
            return self._decode(self.slot, self.typ, truncate_limit)


# data structure to represent the storage variables in a contract
class StorageModel:
    def __init__(self, contract):
        compiler_data = contract.compiler_data
        # TODO: recurse into imported modules
        for k, v in contract.module_t.variables.items():
            is_storage = not (v.is_immutable or v.is_constant or v.is_transient)
            if is_storage:
                slot = compiler_data.storage_layout["storage_layout"][k]["slot"]
                setattr(self, k, StorageVar(contract, slot, v.typ))

    def dump(self):
        ret = FrameDetail("storage")

        for k, v in vars(self).items():
            t = v.get(truncate_limit=1024)
            if t is None:
                t = "<truncated>"  # too large, truncated
            ret[k] = t

        return ret


# data structure to represent the storage variables in a contract
class ImmutablesModel:
    def __init__(self, contract):
        compiler_data = contract.compiler_data
        data_section = memoryview(contract.data_section)
        # TODO: recurse into imported modules
        for k, v in contract.module_t.variables.items():
            if v.is_immutable:  # check that v
                ofst = compiler_data.storage_layout["code_layout"][k]["offset"]
                immutable_raw_bytes = data_section[ofst:]
                value = decode_vyper_object(immutable_raw_bytes, v.typ)
                setattr(self, k, value)

    def dump(self):
        return FrameDetail("immutables", vars(self))

    def __repr__(self):
        return repr(self.dump())


# data structure to represent the constants in a contract
class ConstantsModel:
    def __init__(self, compiler_data: CompilerData):
        for v in compiler_data.annotated_vyper_module.get_children(VariableDecl):
            if v.is_constant:
                setattr(self, v.target.id, v.value.get_folded_value().value)

    def dump(self):
        return FrameDetail("constants", vars(self))

    def __repr__(self):
        return repr(self.dump())


class VyperContract(_BaseVyperContract):
    _can_line_profile = True

    def __init__(
        self,
        compiler_data: CompilerData,
        *args,
        value=0,
        env: Env = None,
        override_address: Address = None,
        # whether to skip constructor
        skip_initcode=False,
        created_from: Address = None,
        contract_name=None,
        filename: str = None,
        gas=None,
    ):
        super().__init__(compiler_data, contract_name, env, filename)

        self.created_from = created_from
        self._computation = None
        self._source_map = None

        # add all exposed functions from the interface to the contract
        exposed_fns = {
            fn_t.name: fn_t.decl_node
            for fn_t in compiler_data.global_ctx.exposed_functions
        }

        # set external methods as class attributes:
        self._ctor = None
        if compiler_data.global_ctx.init_function is not None:
            self._ctor = VyperFunction(
                compiler_data.global_ctx.init_function.decl_node, self
            )

        if skip_initcode:
            if value:
                raise Exception("nonzero value but initcode is being skipped")
            addr = Address(override_address)
        else:
            addr = self._run_init(
                *args, value=value, override_address=override_address, gas=gas
            )
        self._address = addr

        for fn_name, fn in exposed_fns.items():
            setattr(self, fn_name, VyperFunction(fn, self))

        # set internal methods as class.internal attributes:
        self.internal = lambda: None
        for fn in self.module_t.function_defs:
            if not fn._metadata["func_type"].is_internal:
                continue
            setattr(self.internal, fn.name, VyperInternalFunction(fn, self))

        # TODO: set library methods as class.internal attributes?

        # not sure if this is accurate in the presence of modules
        self._function_id = len(self.module_t.function_defs)

        self._storage = StorageModel(self)

        self._eval_cache = lrudict(0x1000)

        self.env.register_contract(self._address, self)

    def _run_init(self, *args, value=0, override_address=None, gas=None):
        encoded_args = b""
        if self._ctor:
            encoded_args = self._ctor.prepare_calldata(*args)

        initcode = self.compiler_data.bytecode + encoded_args
        with self._anchor_source_map(self._deployment_source_map):
            address, computation = self.env.deploy(
                bytecode=initcode,
                value=value,
                override_address=override_address,
                gas=gas,
                contract=self,
            )

            self._computation = computation
            self.bytecode = computation.output

            if computation.is_error:
                self.handle_error(computation)

            return address

    @cached_property
    def _deployment_source_map(self):
        with anchor_settings(self.compiler_data.settings):
            _, source_map = compile_ir.assembly_to_evm(self.compiler_data.assembly)
            return source_map

    # manually set the runtime bytecode, instead of using deploy
    def _set_bytecode(self, bytecode: bytes) -> None:
        to_check = bytecode
        if self.data_section_size != 0:
            to_check = bytecode[: -self.data_section_size]
        assert isinstance(self.compiler_data, CompilerData)
        if to_check != self.compiler_data.bytecode_runtime:
            warnings.warn(
                f"casted bytecode does not match compiled bytecode at {self}",
                stacklevel=2,
            )
        self.bytecode = bytecode

    def __repr__(self):
        ret = (
            f"<{self.compiler_data.contract_path} at {self.address}, "
            f"compiled with vyper-{vyper.__version__}+{vyper.__commit__}>"
        )

        if self.created_from is not None:
            ret += f" (created by {self.created_from})"

        dump_storage = True  # maybe make this configurable in the future
        storage_detail = self._storage.dump()
        if dump_storage and len(storage_detail) > 0:
            ret += f"\n{storage_detail}"

        return ret

    @cached_property
    def _immutables(self):
        return ImmutablesModel(self)

    # is this actually useful?
    def at(self, address):
        return self.deployer.at(address)

    def _get_fn_from_computation(self, computation):
        node = self.find_source_of(computation)
        return get_fn_ancestor_from_node(node)

    def debug_frame(self, computation=None):
        if computation is None:
            computation = self._computation

        fn = self._get_fn_from_computation(computation)
        if fn is None:
            # TODO: figure out why fn is None.
            return None

        fn_t = fn._metadata["func_type"]

        frame_info = fn_t._ir_info.frame_info

        mem = computation._memory
        frame_detail = FrameDetail(fn.name)

        # ensure memory is initialized for `decode_vyper_object()`
        mem.extend(frame_info.frame_start, frame_info.frame_size)
        for k, v in frame_info.frame_vars.items():
            if v.location.name != "memory":
                continue
            ofst = v.pos
            size = v.typ.memory_bytes_required
            frame_detail[k] = decode_vyper_object(mem.read(ofst, size), v.typ)

        return frame_detail

    @property
    def module_t(self):
        return self.compiler_data.global_ctx

    # TODO: maybe rename to `ast_map`
    @property
    def source_map(self):
        if self._source_map is None:
            with anchor_settings(self.compiler_data.settings):
                assembly = self.compiler_data.assembly_runtime
                _, self._source_map = compile_ir.assembly_to_evm(assembly)
        return self._source_map

    def find_error_meta(self, computation):
        if hasattr(computation, "vyper_error_msg"):
            # this is set by ir executor currently.
            return computation.vyper_error_msg

        code_stream = computation.code
        error_map = self.source_map.get("error_map", {})
        for pc in reversed(code_stream._trace):
            if pc in error_map:
                return error_map[pc]
        return None

    def find_source_of(self, computation):
        if hasattr(computation, "vyper_source_pos"):
            # this is set by ir executor currently.
            return self.source_map.get(computation.vyper_source_pos)

        code_stream = computation.code
        ast_map = self.source_map["pc_raw_ast_map"]
        for pc in reversed(code_stream._trace):
            if pc in ast_map:
                return ast_map[pc]
        return None

    def trace_source(self, computation) -> Optional["VyperTraceSource"]:
        if (node := self.find_source_of(computation)) is None:
            return None
        return VyperTraceSource(self, node, method_id=computation.msg.data[:4])

    @cached_property
    def event_for(self):
        module_t = self.compiler_data.global_ctx
        return {e.event_id: e for e in module_t.used_events}

    @cached_property
    def event_abi_for(self):
        return {
            k: event_t.to_toplevel_abi_dict()[0]
            for k, event_t in self.event_for.items()
        }

    def decode_log(self, raw_log):
        # use decode_log() because it is convenient, but we probably
        # want to specialize this for vyper contracts as is done in
        # marshal_to_python/vyper_object.
        return decode_log(self._address, self.event_abi_for, raw_log)

    def marshal_to_python(self, computation, vyper_typ):
        self._computation = computation  # for further inspection

        if computation.is_error:
            self.handle_error(computation)

        # cache gas used for call if profiling is enabled
        gas_meter = self.env.get_gas_meter_class()
        if gas_meter == ProfilingGasMeter:
            cache_gas_used_for_computation(self, computation)

        if vyper_typ is None:
            return None

        # selfdestruct
        if len(computation.beneficiaries) > 0:
            return None

        return_typ = calculate_type_for_external_return(vyper_typ)
        ret = abi_decode(return_typ.abi_type.selector_name(), computation.output)

        # unwrap the tuple if needed
        if not isinstance(vyper_typ, TupleT):
            (ret,) = ret

        return vyper_object(ret, vyper_typ)

    def stack_trace(self, computation=None):
        computation = computation or self._computation
        is_minimal_proxy = is_eip1167_contract(self.bytecode)
        ret = StackTrace([ErrorDetail.from_computation(self, computation)])
        error_detail = self.find_error_meta(computation)
        if (
            error_detail not in EXTERNAL_CALL_ERRORS + CREATE_ERRORS
            and not is_minimal_proxy
        ):
            return ret
        return _handle_child_trace(computation, self.env, ret)

    def ensure_id(self, fn_t):  # mimic vyper.codegen.module.IDGenerator api
        if fn_t._function_id is None:
            fn_t._function_id = self._function_id
            self._function_id += 1

    @cached_property
    def _vyper_namespace(self):
        module = self.compiler_data.annotated_vyper_module
        # make a copy of the namespace, since we might modify it
        ret = copy.copy(module._metadata["namespace"])
        ret._scopes = copy.deepcopy(ret._scopes)
        if len(ret._scopes) == 0:
            # funky behavior in Namespace.enter_scope()
            ret._scopes.append(set())
        return ret

    @contextlib.contextmanager
    def override_vyper_namespace(self):
        # ensure self._vyper_namespace is computed
        contract_members = self._vyper_namespace["self"].typ.members
        try:
            to_keep = set(contract_members.keys())
            with vy_ns.override_global_namespace(self._vyper_namespace):
                yield
        finally:
            # drop all keys which were added while yielding
            keys = list(contract_members.keys())
            for k in keys:
                if k not in to_keep:
                    contract_members.pop(k)

    # for eval(), we need unoptimized assembly, since the dead code
    # eliminator might prune a dead function (which we want to eval)
    @cached_property
    def unoptimized_assembly(self):
        with anchor_settings(self.compiler_data.settings):
            runtime = self.unoptimized_ir[1]
            return compile_ir.compile_to_assembly(
                runtime, optimize=OptimizationLevel.NONE
            )

    @cached_property
    def data_section_size(self):
        return self.module_t.immutable_section_bytes

    @cached_property
    def data_section(self):
        # extract the data section from the bytecode
        if self.data_section_size:
            return self.bytecode[-self.data_section_size :]
        else:
            return b""

    @cached_property
    def unoptimized_bytecode(self):
        with anchor_settings(self.compiler_data.settings):
            s, _ = compile_ir.assembly_to_evm(
                self.unoptimized_assembly, insert_vyper_signature=True
            )
            return s + self.data_section

    @cached_property
    def unoptimized_ir(self):
        settings = copy.copy(self.compiler_data.settings)
        settings.optimize = OptimizationLevel.NONE
        with anchor_settings(settings):
            return generate_ir_for_module(self.module_t)

    @cached_property
    def ir_executor(self):
        _, ir_runtime = self.unoptimized_ir
        with anchor_settings(self.compiler_data.settings):
            return executor_from_ir(ir_runtime, self.compiler_data)

    @contextlib.contextmanager
    def _anchor_source_map(self, source_map):
        tmp = self._source_map
        try:
            self._source_map = source_map
            yield
        finally:
            self._source_map = tmp

    def eval(
        self,
        stmt: str,
        value: int = 0,
        gas: Optional[int] = None,
        sender: Optional[Address] = None,
    ) -> Any:
        """eval vyper code in the context of this contract"""

        # this method is super slow so we cache compilation results
        if stmt not in self._eval_cache:
            self._eval_cache[stmt] = generate_bytecode_for_arbitrary_stmt(stmt, self)
        _, ir_executor, bytecode, source_map, typ = self._eval_cache[stmt]

        with self._anchor_source_map(source_map):
            method_id = b"dbug"  # note dummy method id, doesn't get validated
            c = self.env.execute_code(
                to_address=self._address,
                sender=sender,
                data=method_id,
                value=value,
                gas=gas,
                contract=self,
                override_bytecode=bytecode,
                ir_executor=ir_executor,
            )

            return self.marshal_to_python(c, typ)

    # inject a function into this VyperContract without affecting the
    # contract's source code. useful for testing private functionality
    def inject_function(self, fn_source_code, force=False):
        if not hasattr(self, "inject"):
            self.inject = lambda: None

        # get an AST so we know the fn name; work is doubled in
        # _compile_vyper_function but no way around it.
        fn_ast = parse_to_ast(fn_source_code).body[0]
        if hasattr(self.inject, fn_ast.name) and not force:
            raise ValueError(f"already injected: {fn_ast.name}")

        # ensure self._vyper_namespace is computed
        self._vyper_namespace["self"].typ.members.pop(fn_ast.name, None)
        f = _InjectVyperFunction(self, fn_source_code)
        setattr(self.inject, fn_ast.name, f)


class VyperFunction:
    def __init__(self, fn_ast, contract):
        super().__init__()
        self.fn_ast = fn_ast
        self.contract = contract
        self.env = contract.env

        self.__doc__ = (
            fn_ast.doc_string.value if hasattr(fn_ast, "doc_string") else None
        )
        self.__module__ = self.contract.compiler_data.contract_path

    def __repr__(self):
        return f"{self.contract.compiler_data.contract_path}.{self.fn_ast.name}"

    def __str__(self):
        return repr(self.func_t)

    @cached_property
    def _source_map(self):
        return self.contract.source_map

    @property
    def func_t(self):
        return self.fn_ast._metadata["func_type"]

    @cached_property
    def ir(self):
        module_t = self.contract.module_t

        if self.func_t.is_internal:
            res = generate_ir_for_internal_function(self.fn_ast, module_t, False)
            ir = res.func_ir
        else:
            res = generate_ir_for_external_function(self.fn_ast, module_t)
            ir = res.common_ir

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
        sig_kwargs = self.func_t.keyword_args[:num_kwargs]
        sig_args = self.func_t.positional_args + sig_kwargs
        args_abi_type = (
            "(" + ",".join(arg.typ.abi_type.selector_name() for arg in sig_args) + ")"
        )
        abi_sig = self.func_t.name + args_abi_type

        _method_id = method_id(abi_sig)
        self._signature_cache[num_kwargs] = (_method_id, args_abi_type)

        return _method_id, args_abi_type

    def prepare_calldata(self, *args, **kwargs):
        n_total_args = self.func_t.n_total_args
        n_pos_args = self.func_t.n_positional_args

        if not n_pos_args <= len(args) <= n_total_args:
            expectation_str = f"expected between {n_pos_args} and {n_total_args}"
            if n_pos_args == n_total_args:
                expectation_str = f"expected {n_total_args}"
            raise Exception(
                f"bad args to `{repr(self.func_t)}` "
                f"({expectation_str}, got {len(args)})"
            )

        # align the kwargs with the signature
        # sig_kwargs = self.func_t.default_args[: len(kwargs)]

        total_non_base_args = len(kwargs) + len(args) - n_pos_args

        args = [getattr(arg, "address", arg) for arg in args]

        method_id, args_abi_type = self.args_abi_type(total_non_base_args)
        encoded_args = abi_encode(args_abi_type, args)

        if self.func_t.is_constructor or self.func_t.is_fallback:
            return encoded_args

        return method_id + encoded_args

    def __call__(self, *args, value=0, gas=None, sender=None, **kwargs):
        calldata_bytes = self.prepare_calldata(*args, **kwargs)

        # getattr(x, attr, None) swallows exceptions. use explicit hasattr+getattr
        ir_executor = None
        if hasattr(self, "_ir_executor"):
            ir_executor = self._ir_executor

        override_bytecode = None
        if hasattr(self, "_override_bytecode"):
            override_bytecode = self._override_bytecode

        # note: this anchor doesn't do anything on the default implementation.
        # the source map is overridden in subclasses
        with self.contract._anchor_source_map(self._source_map):
            computation = self.env.execute_code(
                to_address=self.contract._address,
                sender=sender,
                data=calldata_bytes,
                value=value,
                gas=gas,
                is_modifying=self.func_t.is_mutable,
                override_bytecode=override_bytecode,
                ir_executor=ir_executor,
                contract=self.contract,
            )

            typ = self.func_t.return_type
            return self.contract.marshal_to_python(computation, typ)


class VyperInternalFunction(VyperFunction):
    """Internal contract functions are exposed by wrapping it with a dummy
    external contract function, appending the wrapper's ast at the top of
    the contract and then generating bytecode to run internal methods
    (as external methods).
    """

    @cached_property
    def _compiled(self):
        return generate_bytecode_for_internal_fn(self)

    # OVERRIDE so that __call__ uses the specially crafted bytecode
    @cached_property
    def _override_bytecode(self):
        _, _, bytecode, _, _ = self._compiled
        return bytecode

    @cached_property
    def _ir_executor(self):
        _, ir_executor, _, _, _ = self._compiled
        return ir_executor

    # OVERRIDE so that __call__ uses corresponding source map
    @cached_property
    def _source_map(self):
        _, _, _, source_map, _ = self._compiled
        return source_map


class VyperTraceSource(TraceSource):
    def __init__(
        self, contract: VyperContract, node: vy_ast.VyperNode, method_id: bytes
    ):
        self.contract = contract
        self.node = node
        self.method_id = method_id

    def __str__(self):
        return f"{self.contract.contract_name}.{self.func_t.name}:{self.node.lineno}"

    def __repr__(self):
        return repr(self.node)

    @cached_property
    def _func_t_helper(self):
        method_id_int = int(self.method_id.hex(), 16)
        for fn_t in self.contract.compiler_data.global_ctx.exposed_functions:
            for schema, id_ in fn_t.method_ids.items():
                if id_ == method_id_int:
                    return schema, fn_t

    @property
    def func_t(self):
        return self._func_t_helper[1]

    @cached_property
    def args_abi_type(self) -> str:
        schema, fn_t = self._func_t_helper
        return schema.replace(f"{fn_t.name}(", "(")

    @cached_property
    def _argument_names(self) -> list[str]:
        return [arg.name for arg in self.func_t.arguments]

    @cached_property
    def return_abi_type(self) -> str:  # must be implemented by subclasses
        typ = self.func_t.return_type
        if typ is None:
            return "()"
        return typ.abi_type.selector_name()


class _InjectVyperFunction(VyperFunction):
    def __init__(self, contract, fn_source):
        ast, ir_executor, bytecode, source_map, _ = compile_vyper_function(
            fn_source, contract
        )
        super().__init__(ast, contract)

        # OVERRIDES so that __call__ does the right thing
        self._override_bytecode = bytecode
        self._ir_executor = ir_executor
        self._source_map = source_map


_typ_cache: dict[StructT, type] = {}


def _get_struct_type(st: StructT):
    if st in _typ_cache:
        return _typ_cache[st]

    typ = namedtuple(st._id, list(st.tuple_keys()), rename=True)  # type: ignore[misc]

    _typ_cache[st] = typ
    return typ


def vyper_object(val, vyper_type):
    # handling for complex types. recurse
    if isinstance(vyper_type, StructT):
        struct_t = _get_struct_type(vyper_type)
        assert isinstance(val, tuple)
        item_types = list(vyper_type.tuple_members())
        assert len(val) == len(item_types)
        val = [vyper_object(item, item_t) for (item, item_t) in zip(val, item_types)]
        return struct_t(*val)

    if isinstance(vyper_type, TupleT):
        assert isinstance(val, tuple)
        item_types = list(vyper_type.tuple_members())
        assert len(val) == len(item_types)
        val = [vyper_object(item, item_t) for (item, item_t) in zip(val, item_types)]
        return tuple(val)

    if isinstance(vyper_type, (SArrayT, DArrayT)):
        assert isinstance(val, list)
        child_t = vyper_type.value_type
        return [vyper_object(item, child_t) for item in val]

    # note: we can add special handling for addresses, interfaces, contracts here
    return val
