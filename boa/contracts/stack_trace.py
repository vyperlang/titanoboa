from dataclasses import dataclass


class StackTrace(list):
    def __str__(self):
        return "\n\n".join(str(x) for x in self)

    @property
    def last_frame(self):
        return self[-1]


def _trace_for_unknown_contract(computation, env):
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
        child_trace = _trace_for_unknown_contract(child, env)
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
        if hasattr(frame, "vm_error"):
            err = frame.vm_error
            err.args = (frame.pretty_vm_reason, *err.args[1:])
        else:
            err = frame
        return f"{err}\n\n{self.stack_trace}"
