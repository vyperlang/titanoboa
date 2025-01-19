from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple, Optional

from eth.abc import ComputationAPI

from boa.contracts.call_trace import TraceFrame
from boa.contracts.event_decoder import RawLogEntry
from boa.environment import Env
from boa.util.abi import Address
from boa.util.exceptions import strip_internal_frames

if TYPE_CHECKING:
    from boa.contracts.vyper.vyper_contract import DevReason
    from boa.vm.py_evm import titanoboa_computation


class _BaseEVMContract:
    """
    Base class for EVM (Ethereum Virtual Machine) contract:
    This includes ABI and Vyper contract.
    """

    # flag to signal whether this contract can be line profiled
    _can_line_profile = False

    def __init__(
        self,
        name: str,
        env: Optional[Env] = None,
        filename: Optional[str] = None,
        address: Optional[Address] = None,
    ):
        self.env = env or Env.get_singleton()
        self.contract_name = name
        self._address = address  # this can be overridden by subclasses
        self.filename = filename
        self._computation: Optional[ComputationAPI] = None

    def stack_trace(self, computation: ComputationAPI):  # pragma: no cover
        raise NotImplementedError

    def call_trace(self) -> TraceFrame:
        assert self._computation is not None, "No computation to trace"
        return self._computation.call_trace

    def handle_error(self, computation):
        try:
            raise BoaError.create(computation, self)
        except BoaError as b:
            # modify the error so the traceback starts in userland.
            # inspired by answers in https://stackoverflow.com/q/1603940/
            raise strip_internal_frames(b) from b

    @property
    def address(self) -> Address:
        if self._address is None:
            # avoid assert, in pytest it would call repr(self) which segfaults
            raise RuntimeError("Contract address is not set")
        return self._address

    # ## handling events
    def _get_logs(self, computation, include_child_logs):
        if computation is None:
            return []

        if include_child_logs:
            return list(computation.get_raw_log_entries())

        return computation._log_entries

    def get_logs(
        self, computation=None, include_child_logs=True, strict=True
    ) -> list["RawLogEntry | NamedTuple"]:
        if computation is None:
            computation = self._computation

        entries = self._get_logs(computation, include_child_logs)

        # py-evm log format is (log_id, topics, data)
        # sort on log_id
        entries = sorted(entries)

        ret: list["RawLogEntry | NamedTuple"] = []
        for e in entries:
            log_entry = RawLogEntry(*e)
            logger_address = log_entry.address
            c = self.env.lookup_contract(logger_address)
            decoded_log = None
            if c is not None:
                try:
                    decoded_log = c.decode_log(log_entry)
                except Exception as exc:
                    if strict:
                        raise exc

            if decoded_log is None:  # decoding unsuccessful
                ret.append(log_entry)
            else:
                ret.append(decoded_log)

        return ret


class StackTrace(list):  # list[str|ErrorDetail]
    def __str__(self):
        return "\n\n".join(str(x) for x in self)

    @property
    def dev_reason(self) -> Optional["DevReason"]:
        if self.last_frame is None or isinstance(self.last_frame, str):
            return None
        return self.last_frame.dev_reason

    @property
    def last_frame(self):
        return self[-1]


def _trace_for_unknown_contract(computation, env):
    err = f"   <Unknown contract 0x{computation.msg.code_address.hex()}>"
    trace = StackTrace([err])
    return _handle_child_trace(computation, env, trace)


def _handle_child_trace(computation, env, return_trace):
    if len(computation.children) == 0:
        return return_trace
    if not computation.children[-1].is_error:
        return return_trace
    child = computation.children[-1]

    # TODO: maybe should be:
    # child_obj = (
    #   env.lookup_contract(child.msg.code_address)
    #   or env._code_registry.get(child.msg.code)
    # )
    child_obj = env.lookup_contract(child.msg.code_address)

    if child_obj is None:
        child_trace = _trace_for_unknown_contract(child, env)
    else:
        child_trace = child_obj.stack_trace(child)

    if child_trace.dev_reason is not None and return_trace.dev_reason is None:
        # Propagate the dev reason from the child frame to the parent
        return_trace.last_frame.dev_reason = child_trace.dev_reason

    return StackTrace(child_trace + return_trace)


@dataclass
class BoaError(Exception):
    call_trace: TraceFrame
    stack_trace: StackTrace

    @classmethod
    def create(cls, computation: "titanoboa_computation", contract: _BaseEVMContract):
        return cls(computation.call_trace, contract.stack_trace(computation))

    # perf TODO: don't materialize the stack trace until we need it,
    # i.e. BoaError ctor only takes what is necessary to construct the
    # stack trace but does not require the actual stack trace itself.
    def __str__(self):
        frame = self.stack_trace.last_frame
        if hasattr(frame, "vm_error"):
            err = frame.vm_error
            if not getattr(err, "_already_pretty", False):
                # avoid double patching when str() is called more than once
                setattr(err, "_already_pretty", True)
                err.args = (frame.pretty_vm_reason, *err.args[1:])
        else:
            err = frame

        ret = f"{err}\n\n{self.stack_trace}"
        call_tree = str(self.call_trace)
        ledge = "=" * 72
        return f"\n{ledge}\n{call_tree}\n{ledge}\n\n{ret}"
