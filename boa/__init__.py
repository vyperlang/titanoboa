import sys

from boa.interpret import load

# turn off tracebacks if we are in repl
# https://stackoverflow.com/a/64523765
if hasattr(sys, "ps1"):
    pass
    # sys.tracebacklimit = 0
