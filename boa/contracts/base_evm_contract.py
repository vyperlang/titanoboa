from dataclasses import dataclass
from typing import Optional

from eth.abc import ComputationAPI

from boa.environment import Env
from boa.util.abi import Address
from boa.util.exceptions import strip_internal_frames


class _BaseEVMContract:
    """
    Base class for EVM (Ethereum Virtual Machine) contract:
    This includes ABI and Vyper contract.
    """

    # flag to signal whether this contract can be line profiled
    _can_line_profile = False

    def __init__(
        self,
        env: Optional[Env] = None,
        filename: Optional[str] = None,
        address: Optional[Address] = None,
    ):
        self.env = env or Env.get_singleton()
        self._address = address  # this can be overridden by subclasses
        self.filename = filename

    def stack_trace(self, computation: ComputationAPI):  # pragma: no cover
        raise NotImplementedError

    def handle_error(self, computation):
        try:
            raise BoaError(self.stack_trace(computation))
        except BoaError as b:
            # modify the error so the traceback starts in userland.
            # inspired by answers in https://stackoverflow.com/q/1603940/
            raise strip_internal_frames(b) from None

    @property
    def address(self) -> Address:
        if self._address is None:
            # avoid assert, in pytest it would call repr(self) which segfaults
            raise RuntimeError("Contract address is not set")
        return self._address


# TODO: allow only ErrorDetail in here.
# Currently this is list[str|ErrorDetail] (see _trace_for_unknown_contract below)
class StackTrace(list):
    def __str__(self):
        return "\n\n".join(str(x) for x in self)

    @property
    def dev_reason(self) -> str | None:
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
    stack_trace: StackTrace

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
        return f"{err}\n\n{self.stack_trace}"
