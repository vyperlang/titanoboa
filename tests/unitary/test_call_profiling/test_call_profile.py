import pytest

import boa

source_code = """
N_ITER: constant(uint256) = 10

@external
@view
def foo(a: uint256, b: uint256) -> uint256:
    return unsafe_mul(a, b) + unsafe_div(a, b)

@external
@view
def bar(a: uint256, b: uint256) -> uint256:
    d: uint256 = 0
    for j in range(N_ITER):
        d = unsafe_mul(d, isqrt(unsafe_div(a, b) + unsafe_mul(a, b)))
    return d

@external
@view
def baz(c: address):
    assert c != empty(address)
"""

SETTINGS = {"max_examples": 20, "deadline": None}


@pytest.fixture(scope="module")
def boa_contract():
    return boa.loads(source_code, name="TestContract")


def test_call_profiling_disabled_by_default(boa_contract):

    assert not boa_contract.profile_calls
    assert not boa_contract.call_profile


@pytest.mark.parametrize(
    "a,b,c", [(42, 69, 1), (420, 690, 2), (42, 690, 3), (420, 69, 4)]
)
@pytest.mark.profile_calls("boa_contract.foo", "boa_contract.bar")
def test_populate_call_profile_property(boa_contract, a, b, c):

    boa_contract.foo(a, b)
    boa_contract.bar(a, b)

    assert boa_contract.call_profile


@pytest.mark.profile_calls("boa_contract.baz")
def test_append_to_pytest_call_profile(boa_contract):
    boa_contract.baz(boa.env.generate_address())
