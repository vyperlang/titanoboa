import contextlib
import boa
import pytest

source_code = """
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

@external
def baz(x: uint256) -> uint256:
    return x + 1  # rekt: overflow!
"""


@contextlib.contextmanager
def check_raises():
    try:
        yield
        raise Exception("Did not raise")
    except ValueError:  # boa.reverts checks
        pass


@pytest.fixture(scope="module")
def contract():
    return boa.loads(source_code)


def test_always_reverts(contract):
    with boa.reverts():  # wildcard. always catches
        contract.foo(1)


def test_does_not_revert(contract):
    with check_raises():
        with boa.reverts():
            contract.foo(0)  # does not revert


def test_revert_reason(contract):
    # kwarg version
    with boa.reverts(reason="x is 1"):
        contract.foo(1)

    # arg version
    with boa.reverts("x is 1"):
        contract.foo(1)


def test_revert_wrong_reason_type(contract):
    with check_raises():
        with boa.reverts(foooo="x is 1"):
            contract.foo(1)


def test_revert_wrong_reason_string(contract):
    with check_raises():
        with boa.reverts(reason="x is 2"):
            contract.foo(1)


def test_reverts_correct_reason(contract):
    with boa.reverts(vm_error="x is not 4"):
        contract.foo(3)

    with boa.reverts(compiler="safeadd"):
        contract.foo(2**256 - 1)

    with boa.reverts(compiler="safeadd"):
        contract.bar(2**256 - 1)


def test_reason_does_not_stomp_compiler_reason(contract):
    # check that reason cannot stomp compiler reason: here the revert should
    # be because of overflow and not because x is not 5.
    with check_raises():
        with boa.reverts(rekt="x is not 5"):
            contract.bar(2**256 - 1)


def test_compiler_overflow(contract):
    # but only in assert statements. in other cases, stomp!
    with boa.reverts(rekt="overflow!"):
        contract.baz(2**256 - 1)


def test_compiler_reason_does_not_stop_dev_reason(contract):
    # check that compiler reason does not stomp dev reason
    with check_raises():
        with boa.reverts(compiler="safeadd"):
            contract.bar(3)
