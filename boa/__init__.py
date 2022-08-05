import contextlib
import sys

from boa.env import Env, enable_pyevm_verbose_logging
from boa.interpret import BoaError, load, load_partial, loads, loads_partial

# turn off tracebacks if we are in repl
# https://stackoverflow.com/a/64523765
if hasattr(sys, "ps1"):
    pass
    # sys.tracebacklimit = 0

env = Env.get_singleton()


@contextlib.contextmanager
def reverts():
    try:
        yield
        raise Exception("Did not revert")
    except BoaError:
        pass


def eval(code):
    return loads("").eval(code)
