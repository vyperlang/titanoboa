from dataclasses import dataclass

from boa.contracts.stack_trace import StackTrace


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
            err.args = (frame.pretty_vm_reason, *err.args[1:])
        else:
            err = frame
        return f"{err}\n\n{self.stack_trace}"
