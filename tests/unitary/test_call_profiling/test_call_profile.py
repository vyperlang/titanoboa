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


@pytest.fixture(scope="module")
def boa_contract():
    return boa.loads(source_code, name="TestContract")


@pytest.mark.parametrize("a,b", [(42, 69), (420, 690), (42, 690), (420, 69)])
# @pytest.mark.profile_calls
def test_populate_call_profile_property(boa_contract, a, b):

    boa_contract.foo(a, b)
    boa_contract.bar(a, b)


@pytest.mark.profile_calls
def test_append_to_pytest_call_profile(boa_contract):
    boa_contract.baz(boa.env.generate_address())
