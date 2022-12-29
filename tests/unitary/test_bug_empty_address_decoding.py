import pytest

import boa


@pytest.fixture(scope="module")
def boa_contract_a():
    source_code = """
@external
def test(i: uint256, j: uint256) -> uint256:
    assert i != j  # dev: lorem ipsum

    _b: address = 0x809BAf72e430abD10044fF569Bebe87d466d90c9
    return 0
"""
    return boa.loads(source_code)


@pytest.fixture(scope="module")
def boa_contract_b():
    source_code = """
@external
def test(i: uint256, j: uint256) -> uint256:
    assert i != j  # dev: lorem ipsum

    _b: address = empty(address)
    return 0
"""
    return boa.loads(source_code)


def test_bug_with_nonempty_address(boa_contract_a):

    with boa.reverts(), boa.env.prank(boa.env.generate_address()):
        boa_contract_a.test(0, 0)


def test_bug_with_address(boa_contract_b):

    with boa.reverts(), boa.env.prank(boa.env.generate_address()):
        boa_contract_b.test(0, 0)
