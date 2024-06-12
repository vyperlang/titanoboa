import itertools
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis.strategies import SearchStrategy

from boa.test import strategy

BASE_TYPES = ["address", "bool", "bytes32", "decimal", "int", "string", "uint"]


@pytest.mark.parametrize("base1,base2", itertools.product(BASE_TYPES, BASE_TYPES))
def test_strategy(base1, base2):
    st = strategy(f"({base1},({base2},{base1}))")
    assert isinstance(st, SearchStrategy)


@given(value=strategy("(uint8,(bool,bytes4),decimal[3])"))
def test_given(value):
    assert len(value) == 3
    basic, nested_tuple, array = value

    assert type(basic) is int
    assert 0 <= basic <= 255

    assert type(nested_tuple) is tuple
    assert len(nested_tuple) == 2
    assert type(nested_tuple[0]) is bool
    assert type(nested_tuple[1]) is bytes
    assert len(nested_tuple[1]) == 4

    assert type(array) is list
    assert len(array) == 3
    assert type(array[0]) is Decimal


def test_kwargs_raises():
    with pytest.raises(TypeError) as e:
        strategy("(uint,uint)", exclude=[(1, 2)])
    assert "_tuple_strategy() got an unexpected keyword argument 'exclude'" == str(
        e.value
    )


def test_bad_type_raises():
    with pytest.raises(ValueError) as e:
        strategy("tuple")
    assert "No strategy available for type: tuple" == str(e.value)
