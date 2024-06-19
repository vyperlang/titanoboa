from dataclasses import dataclass
from typing import Optional

from eth.abc import ComputationAPI
from eth.exceptions import VMError
from vyper.exceptions import VyperException

from boa.contracts.trace import DevReason, TraceFrame, TraceSource
from boa.environment import Env
from boa.util.abi import Address, abi_decode
from boa.util.exceptions import strip_internal_frames


class FrameDetail(dict):
    def __init__(self, fn_name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fn_name = fn_name

    def __repr__(self):
        detail = ", ".join(f"{k}={v}" for (k, v) in self.items())
        return f"<{self.fn_name}: {detail}>"


@dataclass
class ErrorDetail:
    vm_error: VMError | None  # the error that caused the revert
    contract_repr: str  # string representation of the contract for the error
    error_detail: str  # compiler provided error detail
    dev_reason: DevReason | None = None
    frame_detail: FrameDetail | None = None
    source: TraceSource | None = None

    @classmethod
    def from_computation(
        cls, computation, contract: Optional["_BaseEVMContract"] = None
    ):
        source, frame_detail = None, None
        if contract is None:
            contract_repr = "0x" + computation.msg.code_address.hex()
            error_detail = f"<Unknown location in unknown contract {contract_repr}>"
        else:
            contract_repr = repr(contract)
            error_detail = contract.find_error_meta(computation)
            source = contract.find_source_of(computation)
            frame_detail = contract.debug_frame(computation)

        return cls(
            vm_error=computation.error if computation.is_error else None,
            contract_repr=computation._contract_repr_before_revert or contract_repr,
            error_detail=error_detail,
            dev_reason=source.dev_reason if source else None,
            frame_detail=frame_detail,
            source=source,
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

        if self.source is not None:
            # VyperException.__str__ does a lot of formatting for us
            msg = str(VyperException(msg, self.source))

        if self.frame_detail is not None:
            self.frame_detail.fn_name = "locals"  # override the displayed name
            if len(self.frame_detail) > 0:
                msg += f" {self.frame_detail}"

        return msg


class _BaseEVMContract:
    """
    Base class for EVM (Ethereum Virtual Machine) contract:
    This includes ABI and Vyper contract.
    """

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

    def find_error_meta(self, computation: ComputationAPI) -> str:  # pragma: no cover
        raise NotImplementedError

    def call_trace(self) -> TraceFrame:
        assert self._computation is not None, "No computation to trace"
        return self._computation.trace

    def _create_error(self, computation):
        try:
            raise BoaError.from_computation(computation, self.env, self)
        except BoaError as error:
            try:
                # modify the error so the traceback starts in userland.
                # inspired by answers in https://stackoverflow.com/q/1603940/
                raise strip_internal_frames(error) from None
            except BoaError as error:
                return error

    @property
    def address(self) -> Address:
        assert self._address is not None
        return self._address

    def find_source_of(self, computation) -> TraceSource | None:
        raise NotImplementedError

    def debug_frame(self, computation=None) -> FrameDetail | None:
        return None


class StackTrace(list[ErrorDetail]):
    def __str__(self):
        return "\n\n".join(str(x) for x in self)

    @property
    def dev_reason(self) -> DevReason | None:
        if self.last_frame is None:
            return None
        return self.last_frame.dev_reason

    @property
    def last_frame(self) -> ErrorDetail:
        return self[-1]


@dataclass
class BoaError(Exception):
    stack_trace: StackTrace

    # perf TODO: don't materialize the stack trace until we need it,
    # i.e. BoaError ctor only takes what is necessary to construct the
    # stack trace but does not require the actual stack trace itself.
    def __str__(self):
        frame = self.stack_trace.last_frame
        err = getattr(frame, "vm_error", None)
        if err is None:
            err = frame.contract_repr + frame.error_detail
        elif not getattr(err, "_already_pretty", False):
            # avoid double patching when str() is called more than once
            setattr(err, "_already_pretty", True)
            err.args = (frame.pretty_vm_reason, *err.args[1:])
        return f"{err}\n\n{self.stack_trace}"

    @classmethod
    def from_computation(
        cls, computation, env, contract: Optional[_BaseEVMContract] = None
    ) -> "BoaError":
        parent_trace = StackTrace([ErrorDetail.from_computation(computation, contract)])
        if len(computation.children) == 0:
            return BoaError(parent_trace)
        if not computation.children[-1].is_error:
            return BoaError(parent_trace)

        child_computation = computation.children[-1]
        child_contract = env.lookup_contract(child_computation.msg.code_address)
        child_frame = ErrorDetail.from_computation(child_computation, child_contract)

        if child_frame.dev_reason is not None and parent_trace.dev_reason is None:
            # Propagate the dev reason from the child frame to the parent
            parent_trace.last_frame.dev_reason = child_frame.dev_reason

        return BoaError(StackTrace([child_frame] + parent_trace))
