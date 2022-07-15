import sys

from boa.env import Env
from boa.interpret import contract, load, load_partial, loads, loads_partial

# turn off tracebacks if we are in repl
# https://stackoverflow.com/a/64523765
if hasattr(sys, "ps1"):
    pass
    # sys.tracebacklimit = 0

env = Env.get_singleton()
