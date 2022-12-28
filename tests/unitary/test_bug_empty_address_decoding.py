import pytest

import boa


@pytest.fixture(scope="module")
def boa_contract_throws_error():
    source_code = """
@external
def test(i: uint256, j: uint256) -> uint256:
    assert i != j  # dev: lorem ipsum

    _test: address[3] = empty(address[3])
    return 0
"""
    return boa.loads(source_code)


@pytest.fixture(scope="module")
def boa_contract_works():
    source_code = """
@external
def test(i: uint256, j: uint256) -> uint256:
    assert i != j  # dev: lorem ipsum

    _test: uint256[3] = empty(uint256[3])
    return 0
"""
    return boa.loads(source_code)


def test_revert_throws_valueerror(boa_contract_throws_error):

    with pytest.raises(ValueError) as caught_exception:
        with boa.reverts(), boa.env.prank(boa.env.generate_address()):
            boa_contract_throws_error.test(0, 0)

    assert (
        caught_exception.value.args[0]
        == "Unknown format b'', attempted to normalize to '0x'"
    )


def test_revert_works(boa_contract_works):

    with boa.reverts(), boa.env.prank(boa.env.generate_address()):
        boa_contract_works.test(0, 0)
