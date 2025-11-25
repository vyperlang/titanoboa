import math

import pytest
from eth_hash.auto import keccak
from hypothesis import given
from hypothesis.strategies import characters

import boa
from boa.test import strategy

source_code = """
interface Foo:
    def foo(): nonpayable

_a: uint256

@internal
@pure
def _test_void_func():
    pass

@internal
@pure
def _test_list(a: int128) -> int128[1]:
    return [a]

@internal
@pure
def _test_call_internal() -> bool:
    return self._test_bool(1)

@internal
@pure
def _test_bool(a: uint256, b: bool = False) -> bool:
    if b:
        return b
    else:
        return True

@internal
def _test_repeat(z: int128) -> int128:
    x: int128 = 0
    for i: int128 in range(6):
        x = x + z
    return x


@internal
def _test_interface(s: Foo) -> Foo:
    return s


@internal
@pure
def _sqrt(val: uint256) -> uint256:
    return isqrt(val)

@internal
@pure
def _keccak256(val: String[32]) -> bytes32:
    return keccak256(val)

@internal
@pure
def _sort(unsorted_x: uint256[3]) -> uint256[3]:
    x: uint256[3] = unsorted_x
    temp_var: uint256 = x[0]
    if x[0] < x[1]:
        x[0] = x[1]
        x[1] = temp_var
    if x[0] < x[2]:
        temp_var = x[0]
        x[0] = x[2]
        x[2] = temp_var
    if x[1] < x[2]:
        temp_var = x[1]
        x[1] = x[2]
        x[2] = temp_var

    return x

@external
@view
def sort(unsorted_x: uint256[3]) -> uint256[3]:
    return self._sort(unsorted_x)
"""


@pytest.fixture(scope="module")
def contract():
    return boa.loads(source_code)


@given(a=strategy("uint256"), b=strategy("bool"))
def test_internal(contract, a, b):
    assert contract.internal._test_bool(a, b)


@given(value=strategy("uint256[3]"))
def test_internal_vs_external(contract, value):
    assert contract.internal._sort(value) == contract.sort(value)


@given(a=strategy("uint256"))
def test_internal_default(contract, a):
    assert contract.internal._test_bool(a)


@given(a=strategy("int128"))
def test_list(contract, a):
    assert contract.internal._test_list(a) == [a]


def test_call_internal(contract):  # todo: this doesn't cover goto label stmt
    assert contract.internal._test_call_internal()


def test_internal_void_fn(contract):
    assert contract.internal._test_void_func() is None


def test_repeat(contract):
    assert contract.internal._test_repeat(9) == 54


@given(a=strategy("address"))
def test_interface(contract, a):
    assert contract.internal._test_interface(a) == a


@given(a=strategy("uint256"))
def test_isqrt(contract, a):
    assert contract.internal._sqrt(a) == math.isqrt(a)


@given(a=strategy("string", max_size=32, alphabet=characters(codec="ascii")))
def test_keccak(contract, a):
    assert contract.internal._keccak256(a) == keccak(a.encode())


@given(a=strategy("uint256"), b=strategy("uint256"))
def test_internal_default_2(a, b):
    def method(name: str):
        return f"""
def {name}(x: uint256 = {b}) -> uint256:
    return x
        """

    code = f"""
@external
{method("m_external")}

@internal
{method("m_internal")}
    """

    contract = boa.loads(code)

    assert contract.m_external(a) == a
    assert contract.m_external() == b

    assert contract.internal.m_internal(a) == a
    assert contract.internal.m_internal() == b
