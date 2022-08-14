import contextlib
import boa

contract = """
@external
def foo(x: uint256):
    if x == 0:
        return
    if x == 1:
        raise  # reason: x is 1
    if x > 1:
        assert x + 1 == 5, "x is not 4"

@external
def bar(x: uint256):
    # test the other syntax
    assert x + 1 == 6  # @rekt x is not 5
"""

@contextlib.contextmanager
def check_raises():
    try:
        yield
        raise Exception("Did not raise")
    except ValueError:  # boa.reverts checks
        pass


c = boa.loads(contract)

with boa.reverts():  # wildcard. always catches
    c.foo(1)

with check_raises():
    with boa.reverts():
        c.foo(0)  # does not revert

# kwarg version
with boa.reverts(reason="x is 1"):
    c.foo(1)
# arg version
with boa.reverts("x is 1"):
    c.foo(1)

with check_raises():
    with boa.reverts(foooo="x is 1"):  # wrong reason type
        c.foo(1)
with check_raises():
    with boa.reverts(reason="x is 2"):  # wrong reason string
        c.foo(1)

with boa.reverts(vm_error="x is not 4"):
    c.foo(3)

with boa.reverts(compiler="safeadd"):
    c.foo(2**256 - 1)

with boa.reverts(compiler="safeadd"):
    c.bar(2**256 - 1)

with check_raises():
    # check that reason cannot stomp compiler reason
    with boa.reverts(rekt="x is not 5"):
        c.bar(2**256 - 1)

with check_raises():
    # check that compiler reason does not stomp dev reason
    with boa.reverts(compiler="safeadd"):
        c.bar(3)

print("success.")
