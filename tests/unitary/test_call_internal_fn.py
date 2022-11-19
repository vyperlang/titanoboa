import pytest
from hypothesis import given

import boa
from boa.test import strategy

source_code = """
@internal
@pure
def _test_void_func():
    pass


@internal
@pure
def _test_bool(a: uint256, b: bool = False) -> bool:
    return True


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


def test_internal_void_fn(contract):
    assert contract.internal._test_void_func() is None
