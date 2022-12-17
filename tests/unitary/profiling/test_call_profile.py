import pytest
from hypothesis import given, settings  # noqa

import boa
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
@pytest.mark.profile_calls
def test_populate_call_profile_property(boa_contract, a, b):

    boa_contract.foo(a, b)
    boa_contract.bar(a, b)


@pytest.mark.profile_calls
def test_append_to_pytest_call_profile(boa_contract):
    boa_contract.baz(boa.env.generate_address())

    assert "TestContract.foo" in boa.env.profiled_calls.keys()
    assert "TestContract.bar" in boa.env.profiled_calls.keys()
    assert "TestContract.baz" in boa.env.profiled_calls.keys()


@given(addr=strategy("address"))
@settings(**{"max_examples": 100, "deadline": None})
@pytest.mark.profile_calls
def test_hypothesis_profiling(boa_contract, addr):
    boa_contract.baz(addr)


@given(
    a=strategy("uint256", max_value=10**4), b=strategy("uint256", max_value=10**8)
)
@settings(**{"max_examples": 100, "deadline": None})
@pytest.mark.profile_calls
def test_hypothesis_profiling_uint(boa_contract, a, b):
    boa_contract.foo(a, b)


def test_ignore_call_profiling(boa_contract):
    boa_contract.sip()
    assert "TestContract.sip" not in boa.env.profiled_calls.keys()


@pytest.mark.profile_calls
@pytest.mark.parametrize(
    "a,b,c", [(42, 69, 1), (420, 690, 20), (42, 690, 10), (420, 69, 5)]
)
def test_call_variable_iter_method(a, b, c):

    source_code = """
N_ITER: constant(uint256) = 0x00001

@external
@view
def foo(a: uint256, b: uint256) -> uint256:
    d: uint256 = 0
    for j in range(N_ITER):
        d = unsafe_mul(d, isqrt(unsafe_div(a, b) + unsafe_mul(a, b)))
    return d
"""
    source_code = source_code.replace("0x00001", str(c))
    boa_contract = boa.loads(source_code, name="TestVariableLoopContract")

    boa_contract.foo(a, b)


def test_context_manager():

    source_code = """
@external
@view
def foo(a: uint256 = 0):
    x: uint256 = a
"""
    contract = boa.loads(source_code, name="FooContract")
    with boa.env.store_call_profile(True):
        contract.foo()

    assert "FooContract.foo" in boa.env.profiled_calls.keys()
