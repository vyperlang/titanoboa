import pytest

import boa


def test_no_inputs():
    with pytest.raises(ValueError):
        boa.env.time_travel()


def test_block_travel():
    old_block = boa.env.evm.block_number
    old_timestamp = boa.env.evm.timestamp
    boa.env.time_travel(blocks=420)
    assert boa.env.evm.block_number == old_block + 420
    assert boa.env.evm.timestamp == old_timestamp + 420 * 12


def test_seconds_travel():
    old_timestamp = boa.env.evm.timestamp
    old_block = boa.env.evm.block_number
    boa.env.time_travel(seconds=69)
    assert boa.env.evm.timestamp == old_timestamp + 69
    assert boa.env.evm.block_number == old_block + 69 // 12
