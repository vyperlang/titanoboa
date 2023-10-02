# the main "entry point" of vyper-related functionality like
# AST handling, traceback construction and ABI (marshaling
# and unmarshaling vyper objects)

import contextlib
import copy
import warnings
from dataclasses import dataclass
from functools import cached_property
from typing import Any, Optional

import vyper
import vyper.ast as vy_ast
import vyper.ir.compile_ir as compile_ir
import vyper.semantics.analysis as analysis
import vyper.semantics.namespace as vy_ns
from eth.codecs import abi
from eth.exceptions import VMError
from eth_typing import Address
from eth_utils import to_canonical_address, to_checksum_address
from vyper.ast.utils import parse_to_ast
from vyper.codegen.core import calculate_type_for_external_return
from vyper.codegen.function_definitions import generate_ir_for_function
from vyper.codegen.function_definitions.common import ExternalFuncIR, InternalFuncIR
from vyper.codegen.global_context import GlobalContext
from vyper.codegen.ir_node import IRnode
from vyper.codegen.module import generate_ir_for_module
from vyper.compiler import output as compiler_output
from vyper.compiler.settings import OptimizationLevel
from vyper.exceptions import VyperException
from vyper.ir.optimizer import optimize
from vyper.semantics.analysis.data_positions import set_data_positions
from vyper.semantics.types import AddressT, EventT, HashMapT, TupleT
from vyper.semantics.types.function import ContractFunctionT
from vyper.utils import method_id

from boa.environment import AddressType, Env, to_int
from boa.profiling import LineProfile, cache_gas_used_for_computation
from boa.util.exceptions import strip_internal_frames
from boa.util.lrudict import lrudict
from boa.vm.gas_meters import ProfilingGasMeter
from boa.vyper import _METHOD_ID_VAR
from boa.vyper.ast_utils import ast_map_of, get_fn_ancestor_from_node, reason_at
from boa.vyper.compiler_utils import (
    _compile_vyper_function,
    generate_bytecode_for_arbitrary_stmt,
    generate_bytecode_for_internal_fn,
)
from boa.vyper.decoder_utils import ByteAddressableStorage, decode_vyper_object
from boa.vyper.event import Event, RawEvent

# error messages for external calls
EXTERNAL_CALL_ERRORS = ("external call failed", "returndatasize too small")

CREATE_ERRORS = ("create failed", "create2 failed")

# error detail where user possibly provided dev revert reason
DEV_REASON_ALLOWED = ("user raise", "user assert")


class VyperDeployer:
    def __init__(self, compiler_data, filename=None):
        self.compiler_data = compiler_data

        # force compilation so that if there are any errors in the contract,
        # we fail at load rather than at deploy time.
        _ = compiler_data.bytecode

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

    # TODO: allow `env=` kwargs and so on
    def at(self, address: AddressType) -> "VyperContract":
        address = to_checksum_address(address)
        ret = VyperContract(
            self.compiler_data,
            override_address=address,
            skip_initcode=True,
            filename=self.filename,
        )
        vm = ret.env.vm
        bytecode = vm.state.get_code(to_canonical_address(address))

        ret._set_bytecode(bytecode)

        ret.env.register_contract(address, ret)

        return ret


# a few lines of shared code between VyperBlueprint and VyperContract
class _BaseContract:
    def __init__(self, compiler_data, env=None, filename=None):
        self.compiler_data = compiler_data

        if env is None:
            env = Env.get_singleton()

        self.env = env

        self.filename = filename


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
        filename=None,
    ):
        # note slight code duplication with VyperContract ctor,
        # maybe use common base class?
        super().__init__(compiler_data, env, filename)

        if blueprint_preamble is None:
            blueprint_preamble = b""

        blueprint_bytecode = blueprint_preamble + compiler_data.bytecode

        # the length of the deployed code in bytes
        len_bytes = len(blueprint_bytecode).to_bytes(2, "big")
        deploy_bytecode = b"\x61" + len_bytes + b"\x3d\x81\x60\x0a\x3d\x39\xf3"

        deploy_bytecode += blueprint_bytecode

        addr, self.bytecode = self.env.deploy_code(
            bytecode=deploy_bytecode, override_address=override_address
        )

        self.address = to_checksum_address(addr)

        self.env.register_blueprint(compiler_data.bytecode, self)

    @cached_property
    def deployer(self):
        return VyperDeployer(self.compiler_data, filename=self.filename)


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
    contract: "VyperContract"
    error_detail: str  # compiler provided error detail
    dev_reason: DevReason
    frame_detail: FrameDetail
    storage_detail: Optional[FrameDetail]
    ast_source: vy_ast.VyperNode

    @classmethod
    def from_computation(cls, contract, computation):
        error_detail = contract.find_error_meta(computation.code)
        ast_source = contract.find_source_of(computation.code)
        reason = None
        if ast_source is not None:
            reason = DevReason.at_source_location(
                contract.compiler_data.source_code,
                ast_source.lineno,
                ast_source.end_lineno,
            )
        frame_detail = contract.debug_frame(computation)
        storage_detail = contract._storage.dump()

        return cls(
            vm_error=computation.error,
            contract=contract,
            error_detail=error_detail,
            dev_reason=reason,
            frame_detail=frame_detail,
            storage_detail=storage_detail,
            ast_source=ast_source,
        )

    @property
    def pretty_vm_reason(self):
        err = self.vm_error
        # decode error msg if it's "Error(string)"
        # b"\x08\xc3y\xa0" == method_id("Error(string)")
        if isinstance(err.args[0], bytes) and err.args[0][:4] == b"\x08\xc3y\xa0":
            return abi.decode("(string)", err.args[0][4:])[0]

        return repr(err)

    def __str__(self):
        msg = f"{self.contract}\n"

        if self.error_detail is not None:
            msg += f" <compiler: {self.error_detail}>"

        if self.ast_source is not None:
            # VyperException.__str__ does a lot of formatting for us
            msg = str(VyperException(msg, self.ast_source))

        if self.frame_detail is not None:
            self.frame_detail.fn_name = "locals"  # override the displayed name
            if len(self.frame_detail) > 0:
                msg += f" {self.frame_detail}"

        if self.storage_detail is not None:
            self.storage_detail.fn_name = "storage"  # override displayed name
            if len(self.storage_detail) > 0:
                msg += f"\n {self.storage_detail}"

        return msg


class StackTrace(list):
    def __str__(self):
        return "\n\n".join(str(x) for x in self)

    @property
    def last_frame(self):
        return self[-1]


def trace_for_unknown_contract(computation, env):
    ret = StackTrace(
        [f"<Unknown location in unknown contract {computation.msg.code_address.hex()}>"]
    )
    return _handle_child_trace(computation, env, ret)


def _handle_child_trace(computation, env, return_trace):
    if len(computation.children) == 0:
        return return_trace
    if not computation.children[-1].is_error:
        return return_trace
    child = computation.children[-1]
    child_obj = env.lookup_contract(child.msg.code_address)
    if child_obj is None:
        child_trace = trace_for_unknown_contract(child, env)
    else:
        child_trace = child_obj.stack_trace(child)
    return StackTrace(child_trace + return_trace)


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
        # try to match anything
        _check(
            err == frame.pretty_vm_reason
            or err == frame.error_detail
            or err == frame.dev_reason.reason_str,
            "does not match {args}",
        )
        return

    # try to match a specific kwarg
    assert len(kwargs) == 1 and len(args) == 0

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
            f"{frame.vm_error} != {v}",
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


class StorageVar:
    def __init__(self, contract, slot, typ):
        self.contract = contract
        self.addr = to_canonical_address(self.contract.address)
        self.accountdb = contract.env.vm.state._account_db
        self.slot = slot
        self.typ = typ

    def _decode(self, slot, typ, truncate_limit=None):
        n = typ.memory_bytes_required
        if truncate_limit is not None and n > truncate_limit:
            return None  # indicate failure to caller

        fakemem = ByteAddressableStorage(self.accountdb, self.addr, slot)
        return decode_vyper_object(fakemem, typ)

    def _dealias(self, maybe_address):
        try:
            return self.contract.env.lookup_alias(maybe_address)
        except KeyError:  # not found, return the input
            return maybe_address

    def get(self, truncate_limit=None):
        if isinstance(self.typ, HashMapT):
            ret = {}
            for k in self.contract.env.sstore_trace.get(self.contract.address, {}):
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

                val = self._decode(to_int(k), ty, truncate_limit)

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
        for k, v in compiler_data.global_ctx.variables.items():
            is_storage = not v.is_immutable and not v.is_constant
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
        for k, v in compiler_data.global_ctx.variables.items():
            if v.is_immutable:  # check that v
                ofst = compiler_data.storage_layout["code_layout"][k]["offset"]
                immutable_raw_bytes = data_section[ofst:]
                value = decode_vyper_object(immutable_raw_bytes, v.typ)
                setattr(self, k, value)

    def dump(self):
        return FrameDetail("immutables", vars(self))

    def __repr__(self):
        return repr(self.dump())


class VyperContract(_BaseContract):
    def __init__(
        self,
        compiler_data,
        *args,
        env=None,
        override_address=None,
        # whether or not to skip constructor
        skip_initcode=False,
        created_from=None,
        filename=None,
    ):
        super().__init__(compiler_data, env, filename)

        self.created_from = created_from

        # add all exposed functions from the interface to the contract
        external_fns = {
            fn.name: fn
            for fn in self.global_ctx.functions
            if fn._metadata["type"].is_external
        }

        # set external methods as class attributes:
        self._ctor = None
        if "__init__" in external_fns:
            self._ctor = VyperFunction(external_fns.pop("__init__"), self)

        if skip_initcode:
            self.address = to_checksum_address(override_address)
        else:
            self.address = self._run_init(*args, override_address=override_address)

        for fn_name, fn in external_fns.items():
            setattr(self, fn_name, VyperFunction(fn, self))

        # set internal methods as class.internal attributes:
        self.internal = lambda: None
        for fn in self.global_ctx.functions:
            if not fn._metadata["type"].is_internal:
                continue
            setattr(self.internal, fn.name, VyperInternalFunction(fn, self))

        self._storage = StorageModel(self)

        self._eval_cache = lrudict(0x1000)
        self._source_map = None
        self._computation = None

        self.env.register_contract(self.address, self)

    def _run_init(self, *args, override_address=None):
        encoded_args = b""
        if self._ctor:
            encoded_args = self._ctor.prepare_calldata(*args)

        initcode = self.compiler_data.bytecode + encoded_args
        addr, self.bytecode = self.env.deploy_code(
            bytecode=initcode, override_address=override_address
        )
        return to_checksum_address(addr)

    # manually set the runtime bytecode, instead of using deploy
    def _set_bytecode(self, bytecode: bytes) -> None:
        to_check = bytecode
        if self.data_section_size != 0:
            to_check = bytecode[: -self.data_section_size]
        if to_check != self.compiler_data.bytecode_runtime:
            warnings.warn(
                f"casted bytecode does not match compiled bytecode at {self}",
                stacklevel=2,
            )
        self.bytecode = bytecode

    def __repr__(self):
        ret = (
            f"<{self.compiler_data.contract_name} at {to_checksum_address(self.address)}, "
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

    @cached_property
    def deployer(self):
        # TODO add test
        return VyperDeployer(self.compiler_data, filename=self.filename)

    # is this actually useful?
    def at(self, address):
        return self.deployer.at(address)

    @cached_property
    def ast_map(self):
        return ast_map_of(self.compiler_data.vyper_module)

    def _get_fn_from_computation(self, computation):
        node = self.find_source_of(computation.code)
        return get_fn_ancestor_from_node(node)

    def debug_frame(self, computation=None):
        if computation is None:
            computation = self._computation

        fn = self._get_fn_from_computation(computation)
        if fn is None:
            # TODO: figure out why fn is None.
            return None

        frame_info = self.compiler_data.function_signatures[fn.name]._ir_info.frame_info

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

    # ## handling events
    def _get_logs(self, computation, include_child_logs):
        if computation is None:
            return []

        if include_child_logs:
            return list(computation.get_raw_log_entries())

        return computation._log_entries

    def get_logs(self, computation=None, include_child_logs=True):
        if computation is None:
            computation = self._computation

        entries = self._get_logs(computation, include_child_logs)

        # py-evm log format is (log_id, topics, data)
        # sort on log_id
        entries = sorted(entries)

        ret = []
        for e in entries:
            logger_address = e[1]
            c = self.env.lookup_contract(logger_address)
            if c is not None:
                ret.append(c.decode_log(e))
            else:
                ret.append(RawEvent(e))

        return ret

    @cached_property
    def event_for(self):
        m = self.compiler_data.vyper_module_folded._metadata["type"]
        return {e.event_id: e for e in m.events.values()}

    def decode_log(self, e):
        log_id, address, topics, data = e
        assert to_canonical_address(self.address) == address
        event_hash = topics[0]
        event_t = self.event_for[event_hash]

        topic_typs = []
        arg_typs = []
        for is_topic, typ in zip(event_t.indexed, event_t.arguments.values()):
            if not is_topic:
                arg_typs.append(typ)
            else:
                topic_typs.append(typ)

        decoded_topics = []
        for typ, t in zip(topic_typs, topics[1:]):
            # convert to bytes for abi decoder
            encoded_topic = t.to_bytes(32, "big")
            decoded_topics.append(
                abi.decode(typ.abi_type.selector_name(), encoded_topic)
            )

        tuple_typ = TupleT(arg_typs)

        args = abi.decode(tuple_typ.abi_type.selector_name(), data)

        return Event(log_id, self.address, event_t, decoded_topics, args)

    def marshal_to_python(self, computation, vyper_typ):
        self._computation = computation  # for further inspection

        if computation.is_error:
            self.handle_error(computation)

        # cache gas used for call if profiling is enabled
        gas_meter = self.env.vm.state.computation_class._gas_meter_class
        if gas_meter == ProfilingGasMeter:
            cache_gas_used_for_computation(self, computation)

        if vyper_typ is None:
            return None

        return_typ = calculate_type_for_external_return(vyper_typ)
        ret = abi.decode(return_typ.abi_type.selector_name(), computation.output)

        # unwrap the tuple if needed
        if not isinstance(vyper_typ, TupleT):
            (ret,) = ret

        return vyper_object(ret, vyper_typ)

    def handle_error(self, computation):
        try:
            raise BoaError(self.stack_trace(computation))
        except BoaError as b:
            # modify the error so the traceback starts in userland.
            # inspired by answers in https://stackoverflow.com/q/1603940/
            raise strip_internal_frames(b) from None

    def stack_trace(self, computation=None):
        computation = computation or self._computation
        ret = StackTrace([ErrorDetail.from_computation(self, computation)])
        error_detail = self.find_error_meta(computation.code)
        if error_detail not in EXTERNAL_CALL_ERRORS + CREATE_ERRORS:
            return ret
        return _handle_child_trace(computation, self.env, ret)

    def line_profile(self, computation=None):
        computation = computation or self._computation
        ret = LineProfile.from_single(self, computation)
        for child in computation.children:
            child_obj = self.env.lookup_contract(child.msg.code_address)
            # TODO: child obj is opaque contract that calls back into known contract
            if child_obj is not None:
                ret.merge(child_obj.line_profile(child))
        return ret

    @cached_property
    def _ast_module(self):
        module = copy.deepcopy(self.compiler_data.vyper_module)

        # do the same thing as vyper_module_folded but skip getter expansion
        vy_ast.folding.fold(module)
        with vy_ns.get_namespace().enter_scope():
            analysis.add_module_namespace(module, self.compiler_data.interface_codes)
            analysis.validate_functions(module)
            # we need to cache the namespace right here(!).
            # set_data_positions will modify the type definitions in place.
            self._cache_namespace(vy_ns.get_namespace())

        vy_ast.expansion.remove_unused_statements(module)
        # calculate slots for all storage variables, tagging
        # the types in the namespace.
        set_data_positions(module, storage_layout_overrides=None)

        # ensure _ir_info is generated for all functions in this copied/shadow
        # namespace
        _ = generate_ir_for_module(GlobalContext(module))

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
            self._vyper_namespace["self"].typ.members.pop("__boa_debug__", None)

    # for eval(), we need unoptimized assembly, since the dead code
    # eliminator might prune a dead function (which we want to eval)
    @cached_property
    def unoptimized_assembly(self):
        runtime = self.compiler_data.ir_runtime
        return compile_ir.compile_to_assembly(runtime, optimize=OptimizationLevel.NONE)

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
        if stmt in self._eval_cache:
            bytecode, source_map, typ = self._eval_cache[stmt]
        else:
            bytecode, source_map, typ = generate_bytecode_for_arbitrary_stmt(stmt, self)
            self._eval_cache[stmt] = (bytecode, source_map, typ)

        with self._anchor_source_map(source_map):
            method_id = b"dbug"  # note dummy method id, doesn't get validated
            c = self.env.execute_code(
                to_address=self.address,
                sender=sender,
                data=method_id,
                value=value,
                gas=gas,
                contract=self,
                override_bytecode=bytecode,
            )

            ret = self.marshal_to_python(c, typ)

            return ret

    # inject a function into this VyperContract without affecting the
    # contract's source code. useful for testing private functionality
    def inject_function(self, fn_source_code, force=False):
        if not hasattr(self, "inject"):
            self.inject = lambda: None

        # get an AST so we know the fn name; work is doubled in
        # _compile_vyper_function but no way around it.
        fn_ast = parse_to_ast(fn_source_code, {}).body[0]
        if hasattr(self.inject, fn_ast.name) and not force:
            raise ValueError(f"already injected: {fn_ast.name}")

        # ensure self._vyper_namespace is computed
        m = self._ast_module  # noqa: F841
        self._vyper_namespace["self"].typ.members.pop(fn_ast.name, None)
        f = _InjectVyperFunction(self, fn_source_code)
        setattr(self.inject, fn_ast.name, f)


class VyperFunction:
    def __init__(self, fn_ast, contract):
        self.fn_ast = fn_ast
        self.contract = contract
        self.env = contract.env

    def __repr__(self):
        return f"{self.contract.compiler_data.contract_name}.{self.fn_ast.name}"

    @cached_property
    def _source_map(self):
        return self.contract.source_map

    @property
    def func_t(self):
        return self.fn_ast._metadata["type"]

    @cached_property
    def ir(self):
        # patch compiler_data to have IR for every function
        global_ctx = self.contract.global_ctx

        res = generate_ir_for_function(self.fn_ast, global_ctx, False)
        if isinstance(res, InternalFuncIR):
            ir = res.func_ir
        elif isinstance(res, ExternalFuncIR):
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
        # allow things with `.address` to be encode-able
        args = [getattr(arg, "address", arg) for arg in args]

        method_id, args_abi_type = self.args_abi_type(total_non_base_args)
        encoded_args = abi.encode(args_abi_type, args)

        if self.func_t.is_constructor or self.func_t.is_fallback:
            return encoded_args

        return method_id + encoded_args

    def __call__(self, *args, value=0, gas=None, sender=None, **kwargs):
        calldata_bytes = self.prepare_calldata(*args, **kwargs)
        # getattr(x, attr, None) swallows exceptions. use explicit hasattr+getattr
        override_bytecode = None
        if hasattr(self, "override_bytecode"):
            override_bytecode = self.override_bytecode
        with self.contract._anchor_source_map(self._source_map):
            computation = self.env.execute_code(
                to_address=self.contract.address,
                sender=sender,
                data=calldata_bytes,
                value=value,
                gas=gas,
                is_modifying=self.func_t.is_mutable,
                override_bytecode=override_bytecode,
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
    def override_bytecode(self):
        bytecode, _, _ = self._compiled
        return bytecode

    # OVERRIDE so that __call__ uses corresponding source map
    @cached_property
    def _source_map(self):
        _, source_map, _ = self._compiled
        return source_map


# a contract which we only have the ABI for.
# TODO refactor:
# right now inherits functionality from VyperContract
# but would be better to put this in like BaseContract
# and have both BaseContract => InterfaceContract
# and separately BaseContract => VyperContract
class ABIContract(VyperContract):
    def __init__(self, name, functions, events, address, created_from=None, env=None):
        if env is None:
            env = Env.get_singleton()
        self.env = env

        self._name = name
        self._events = events
        self._functions = functions

        for func_t in self._functions:
            setattr(self, func_t.name, ABIFunction(func_t, self))

        self.address = to_checksum_address(address)
        self.created_from = created_from

        self._source_map = {"pc_pos_map": {}}  # override

    @cached_property
    def method_id_map(self):
        ret = {}
        for func_t in self._functions:
            for abi_sig, method_id_int in func_t.method_ids.items():
                method_id_bytes = method_id_int.to_bytes(4, "big")
                assert method_id_bytes not in ret  # vyper guarantees unique method ids
                ret[method_id_bytes] = abi_sig
        return ret

    def stack_trace(self, computation=None):
        computation = computation or self._computation
        calldata_method_id = bytes(computation.msg.data[:4])
        abi_sig = self.method_id_map[calldata_method_id]
        ret = StackTrace([f"  (unknown location in {self}.{abi_sig})"])
        return _handle_child_trace(computation, self.env, ret)

    @property
    def deployer(self):
        return ABIContractFactory(self._name, self._functions, self._events)

    def __repr__(self):
        ret = f"<{self._name} interface at {to_checksum_address(self.address)}>"

        if self.created_from is not None:
            ret += f" (created by {self.created_from})"

        return ret

    # OVERRIDE
    @cached_property
    def event_for(self):
        return {e.event_id: e for e in self._events}


# name Factory instead of Deployer because it doesn't actually do any
# contract deployment.
class ABIContractFactory:
    def __init__(self, name, functions, events):
        self._name = name
        self._functions = functions
        self._events = events

    @classmethod
    def from_abi_dict(cls, abi, name=None):
        if name is None:
            name = "<anonymous contract>"

        functions = [
            ContractFunctionT.from_abi(i) for i in abi if i.get("type") == "function"
        ]

        # warn on functions with same name
        _tmp = set()
        for f in functions:
            if f.name in _tmp:
                warnings.warn(
                    f"{name} overloads {f.name}! overloaded methods "
                    "might not work correctly at this time",
                    stacklevel=1,
                )
            _tmp.add(f.name)

        events = [EventT.from_abi(i) for i in abi if i.get("type") == "event"]

        return cls(name, functions, events)

    def at(self, address) -> ABIContract:
        address = to_checksum_address(address)

        ret = ABIContract(self._name, self._functions, self._events, address)

        bytecode = ret.env.vm.state.get_code(to_canonical_address(address))
        if bytecode == b"":
            warnings.warn(
                "requested {ret} but there is no bytecode at that address!",
                stacklevel=2,
            )

        ret.env.register_contract(address, ret)

        return ret


class ABIFunction(VyperFunction):
    def __init__(self, func_t, contract):
        self.contract = contract
        self.env = contract.env
        self._func_t = func_t

    def __repr__(self):
        return f"{self.contract._name}.{self._func_t.name}"

    # OVERRIDE
    @property
    def func_t(self):
        return self._func_t

    # OVERRIDE
    @cached_property
    def _source_map(self):
        return {"pc_pos_map": {}}


class _InjectVyperFunction(VyperFunction):
    def __init__(self, contract, fn_source):
        ast, bytecode, source_map, _ = _compile_vyper_function(fn_source, contract)
        super().__init__(ast, contract)

        self.override_bytecode = bytecode

        # OVERRIDE so that __call__ uses special source map
        self._source_map = source_map


@dataclass
class BoaError(Exception):
    stack_trace: StackTrace

    # perf TODO: don't materialize the stack trace until we need it,
    # i.e. BoaError ctor only takes what is necessary to construct the
    # stack trace but does not require the actual stack trace itself.
    def __str__(self):
        frame = self.stack_trace.last_frame
        err = frame.vm_error
        err.args = (frame.pretty_vm_reason, *err.args[1:])
        return f"{err}\n\n{self.stack_trace}"


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
