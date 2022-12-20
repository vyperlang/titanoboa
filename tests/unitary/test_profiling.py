import pytest
from hypothesis import given, settings

import boa
from boa.test import strategy


@pytest.fixture(scope="module")
def external_contract():
    source_code = """
@external
@view
def foo(a: uint256) -> uint256:
    return unsafe_div(isqrt(a) * 100, 2)
"""
    return boa.loads(source_code, name="ExternalContract")


@pytest.fixture(scope="module")
def source_contract(external_contract):
    source_code = """
interface Foo:
    def foo(a: uint256) -> uint256: view

FOO: immutable(address)

@external
def __init__(_foo_address: address):
    FOO = _foo_address

@external
@view
def bar(b: uint256) -> uint256:
    c: uint256 = Foo(FOO).foo(b)
    return c
"""
    return boa.loads(source_code, external_contract.address, name="TestContract")


@pytest.fixture(scope="module")
def variable_loop_contract():

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
def test_ignore_profiling(variable_loop_contract, a, b, c):

    variable_loop_contract.foo(a, b, c)
    assert not boa.env._cached_call_profiles


@pytest.mark.parametrize(
    "a,b,c", [(42, 69, 150), (420, 690, 20000), (42, 690, 10000), (420, 69, 5000)]
)
@pytest.mark.profile
def test_call_variable_iter_method(variable_loop_contract, a, b, c):
    variable_loop_contract.foo(a, b, c)

    assert boa.env._cached_call_profiles
    assert boa.env._cached_line_profiles


@given(
    a=strategy("uint256", max_value=10**4),
    b=strategy("uint256", max_value=10**8),
    c=strategy("uint256", max_value=10**6),
)
@settings(max_examples=100, deadline=None)
@pytest.mark.profile
def test_fuzz_profiling(variable_loop_contract, a, b, c):
    variable_loop_contract.foo(a, b, c)


@pytest.mark.profile
def test_profile():

    source_code = """
@external
@view
def foo(a: uint256 = 0):
    x: uint256 = a
"""
    contract = boa.loads(source_code, name="FooContract")
    contract.foo()


@pytest.mark.profile
def test_external_call(source_contract):
    source_contract.bar(10)
