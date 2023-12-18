import sys
import types
from dataclasses import dataclass


# take an exception instance, and strip frames in the target module
# from the traceback
def strip_internal_frames(exc, module_name=None):
    ei = sys.exc_info()
    frame = ei[2].tb_frame

    if module_name is None:
        module_name = frame.f_globals["__name__"]

    while frame.f_globals.get("__name__", None) == module_name:
        frame = frame.f_back

    # kwargs incompatible with pypy here
    # tb_next=None, tb_frame=frame, tb_lasti=frame.f_lasti, tb_lineno=frame.f_lineno
    tb = types.TracebackType(None, frame, frame.f_lasti, frame.f_lineno)
    return ei[1].with_traceback(tb)


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

    # TODO: maybe should be:
    # child_obj = (
    #   env.lookup_contract(child.msg.code_address)
    #   or env._code_registry.get(child.msg.code)
    # )
    child_obj = env.lookup_contract(child.msg.code_address)

    if child_obj is None:
        child_trace = trace_for_unknown_contract(child, env)
    else:
        child_trace = child_obj.stack_trace(child)
    return StackTrace(child_trace + return_trace)


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
