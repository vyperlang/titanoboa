import pytest

import boa


@pytest.fixture(scope="module")
def boa_contract_a():
    source_code = """
@external
def test(i: uint256, j: uint256) -> uint256:
    assert i == j  # dev: raised before memory is initialized

    _b: address = 0x809BAf72e430abD10044fF569Bebe87d466d90c9
    return 0
"""
    return boa.loads(source_code)


# revert triggers a decode of all local variables.
# test that the decode works even if memory is not initialized.
def test_decode_uninitialized_memory(boa_contract_a):
    with boa.reverts():
        boa_contract_a.test(0, 1)
