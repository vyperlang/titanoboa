import pytest

import boa

source_code_a = """
@external
@view
def foo(a: uint256) -> uint256:
    return unsafe_div(isqrt(a) * 100, 2)
"""

source_code_b = """
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


@pytest.fixture(scope="module")
def external_contract():
    return boa.loads(source_code_a, name="ExternalContract")


@pytest.fixture(scope="module")
def boa_contract(external_contract):
    return boa.loads(source_code_b, external_contract.address, name="TestContract")


@pytest.mark.profile
def test_single_computation(external_contract):
    external_contract.foo(2000)
    lp = external_contract.line_profile().summary()
    assert lp


@pytest.mark.profile
def test_external_call(boa_contract):
    boa_contract.bar(10)
    lp = boa_contract.line_profile().summary()
    assert lp
