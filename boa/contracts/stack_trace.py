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
