import contextlib
from boa.interpret.object import LogItem
from typing import List

class Trace:
    def __init__(self):
        self.events: List[LogItem] = []


class InterpreterContext:
    def __init__(self, global_ctx, contract):
        self.global_ctx = global_ctx
        self._local_variables = [{}]  # list of maps
        self.contract = contract
        self.trace = Trace()

    def set_args(*args):
        print(*args)

    def set_var(self, varname, val):
        for scope in self._local_variables:
            if varname in scope:
                scope[varname] = val
                break
        else:
            self._local_variables[-1][varname] = val

    def get_var(self, varname):
        for scope in self._local_variables:
            if varname in scope:
                return scope[varname]

    @contextlib.contextmanager
    def block_scope(self):
        self._local_variables.append(dict())
        yield
        self._local_variables.pop()
