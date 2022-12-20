import pytest
from hypothesis import given, settings  # noqa

import boa
from boa.profiling import SelectorInfo
from boa.test import strategy

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

@external
@view
def sip():
    x: uint256 = 10
"""


@pytest.fixture(scope="module")
def boa_contract():
    return boa.loads(source_code, name="TestContract")


@pytest.mark.parametrize("a,b", [(42, 69), (420, 690), (42, 690), (420, 69)])
@pytest.mark.call_profile
def test_populate_call_profile_property(boa_contract, a, b):

    boa_contract.foo(a, b)
    boa_contract.bar(a, b)


@pytest.mark.call_profile
def test_append_to_pytest_call_profile(boa_contract):
    boa_contract.foo(42, 69)
    boa_contract.bar(420, 690)
    boa_contract.baz(boa.env.generate_address())

    addr = boa_contract.address
    fns = [
        SelectorInfo("foo", "TestContract", addr),
        SelectorInfo("bar", "TestContract", addr),
        SelectorInfo("baz", "TestContract", addr),
    ]

    for fn in fns:
        assert fn in boa.env._cached_call_profiles.keys()


@given(addr=strategy("address"))
@settings(**{"max_examples": 100, "deadline": None})
@pytest.mark.call_profile
def test_hypothesis_profiling(boa_contract, addr):
    boa_contract.baz(addr)


@given(
    a=strategy("uint256", max_value=10**4), b=strategy("uint256", max_value=10**8)
)
@settings(**{"max_examples": 100, "deadline": None})
@pytest.mark.call_profile
def test_hypothesis_profiling_uint(boa_contract, a, b):
    boa_contract.foo(a, b)


def test_ignore_call_profiling(boa_contract):
    boa_contract.sip()
    sip_fn = SelectorInfo("sip", "TestContract", boa_contract.address)
    assert sip_fn not in boa.env._cached_call_profiles.keys()


@pytest.fixture(scope="module")
def boa_contract_variable():

    source_code = """
@external
@view
def foo(a: uint256, b: uint256, c: uint256) -> uint256:
    d: uint256 = 0
    for j in range(1000):
        d = d + a + b
        if d > c:
            break
    return d
"""
    return boa.loads(source_code, name="TestVariableLoopContract")


@pytest.mark.parametrize(
    "a,b,c", [(42, 69, 150), (420, 690, 20000), (42, 690, 10000), (420, 69, 5000)]
)
@pytest.mark.call_profile
def test_call_variable_iter_method(boa_contract_variable, a, b, c):
    boa_contract_variable.foo(a, b, c)


@pytest.mark.call_profile
def test_profile():

    source_code = """
@external
@view
def foo(a: uint256 = 0):
    x: uint256 = a
"""
    contract = boa.loads(source_code, name="FooContract")
    contract.foo()
