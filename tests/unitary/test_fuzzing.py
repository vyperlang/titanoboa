import pytest

import boa

code = """
@external
def identity(a: uint256) -> uint256:
    return a

@external
def sometimes_raises(a: uint256) -> uint256:
    assert a % 2 == 0
    return a

@external
def overloaded(a: uint256, b: bool = True) -> uint256:
    assert b
    return a
"""


@pytest.fixture(scope="module")
def contract():
    return boa.loads(code, filename="MyFuzzContract.vy")


def test_identity(contract):
    @boa.fuzz(contract.identity)
    def _test(a):
        assert a == contract.identity(a)

    _test()


def test_sometimes_raises(contract):
    @boa.fuzz(contract.sometimes_raises)
    def _test(a):
        if a % 2 != 0:
            with boa.reverts():
                contract.sometimes_raises(a)
        else:
            assert a == contract.sometimes_raises(a)

    _test()


def test_overloaded(contract):
    @boa.fuzz(contract.overloaded)
    def _test(a, b):
        if not b:
            with boa.reverts():
                contract.overloaded(a, b)
        else:
            assert a == contract.overloaded(a, b)

    @boa.fuzz(contract.overloaded)
    def _test_default(a, b):
        # ignores b
        assert a == contract.overloaded(a)

    _test()
    _test_default()
