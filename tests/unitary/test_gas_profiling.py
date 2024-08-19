import pytest
from hypothesis import given, settings

import boa
from boa.profiling import global_profile
from boa.test import strategy


@pytest.fixture(scope="module")
def external_contract():
    source_code = """
@external
@view
def foo(a: uint256) -> uint256:
    return self._foo(a)


@internal
@pure
def _foo(b: uint256) -> uint256:
    return unsafe_div(isqrt(b) * 100, 2)
"""
    return boa.loads(source_code, name="ExternalContract")


@pytest.fixture(scope="module")
def source_contract(external_contract):
    source_code = """
interface Foo:
    def foo(a: uint256) -> uint256: view

FOO: immutable(address)

@deploy
def __init__(_foo_address: address):
    FOO = _foo_address

@external
@view
def bar(b: uint256) -> uint256:
    c: uint256 = staticcall Foo(FOO).foo(b)
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
    for j: uint256 in range(1000):
        d = d + a + b
        if d > c:
            break
    return d

@external
@view
def _barfoo(a: uint256, b: uint256, c: uint256) -> uint256:
    d: uint256 = 0
    for j: uint256 in range(1000):
        d = (d * a) // b
        if d > c:
            break
    return d
"""
    return boa.loads(source_code, name="TestVariableLoopContract")


@pytest.mark.parametrize(
    "a,b,c", [(42, 69, 150), (420, 690, 20000), (42, 690, 10000), (420, 69, 5000)]
)
@pytest.mark.ignore_profiling
def test_ignore_profiling(variable_loop_contract, a, b, c):
    # TODO: not sure this is testing what it intends to
    cached_profiles = [global_profile().call_profiles, global_profile().line_profiles]

    variable_loop_contract.foo(a, b, c)

    assert global_profile().call_profiles == cached_profiles[0]
    assert global_profile().line_profiles == cached_profiles[1]


@pytest.mark.parametrize(
    "a,b,c", [(42, 69, 150), (420, 690, 20000), (42, 690, 10000), (420, 69, 5000)]
)
@pytest.mark.gas_profile
def test_call_variable_iter_method(variable_loop_contract, a, b, c):
    variable_loop_contract.foo(a, b, c)
    variable_loop_contract._barfoo(a, b, c)

    assert global_profile().call_profiles
    assert global_profile().line_profiles


@given(
    a=strategy("uint256", max_value=10**4),
    b=strategy("uint256", max_value=10**8),
    c=strategy("uint256", max_value=10**6),
)
@settings(max_examples=100, deadline=None)
@pytest.mark.gas_profile
def test_fuzz_profiling(variable_loop_contract, a, b, c):
    variable_loop_contract.foo(a, b, c)


@pytest.mark.gas_profile
def test_external_call(source_contract):
    source_contract.bar(10)


@pytest.mark.gas_profile
def test_gas_profile():
    source_code = """
@external
@view
def foo(a: uint256 = 0):
    x: uint256 = a
"""
    contract = boa.loads(source_code, name="FooContract")
    contract.foo()


@pytest.mark.gas_profile
def test_profile_empty_function():
    source_code = """
@external
@view
def bar():
    pass
"""
    contract = boa.loads(source_code, name="EmptyFooContract")
    contract.bar()


@pytest.mark.gas_profile
def test_profile_long_contract():
    source_code = """
@external
@view
def bar() -> uint256:
    a: uint256 = 1 + 2 + 123124129847129847120 + 1028371928319724128 - 123123 - 123123 + 12312938712983712  # noqa: E501
    return a
"""
    contract = boa.loads(source_code, name="LongFooContract")
    contract.bar()


@pytest.mark.gas_profile
def test_profile_long_names():
    source_code = """
@external
@view
def bar_foo_baz_foobar_baz_something_something_anything_nothing_everything() -> uint256:
    a: uint256 = 1 + 2 + 123124129847129847120 + 1028371928319724128 - 123123 - 123123 + 12312938712983712  # noqa: E501
    return a
"""
    contract = boa.loads(source_code, name="LongFooBarBazNameContract")
    contract.bar_foo_baz_foobar_baz_something_something_anything_nothing_everything()
