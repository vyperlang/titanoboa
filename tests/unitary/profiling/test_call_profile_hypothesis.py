import pytest
from hypothesis import given, settings

import boa
from boa.test import strategy

SETTINGS = {"max_examples": 100, "deadline": None}

source_code = """
@external
@view
def foo(a: uint256) -> uint256:
    return unsafe_mul(a, a/2) + unsafe_div(a, a/17)

"""


@pytest.fixture(scope="module")
def boa_contract():
    return boa.loads(source_code, name="TestContract")


@given(value=strategy("uint256", min_value=10, max_value=10000))
@settings(**SETTINGS)
@pytest.mark.profile_calls
def test_profile_hypothesis(boa_contract, value):
    boa_contract.foo(value)
