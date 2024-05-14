import pytest

import boa


def test_no_inputs():
    with pytest.raises(ValueError):
        boa.env.time_travel()


def test_block_travel():
    old_block = boa.env.block_number
    old_timestamp = boa.env.timestamp
    boa.env.time_travel(blocks=420)
    assert boa.env.block_number == old_block + 420
    assert boa.env.timestamp == old_timestamp + 420 * 12


def test_seconds_travel():
    old_timestamp = boa.env.timestamp
    old_block = boa.env.block_number
    boa.env.time_travel(seconds=69)
    assert boa.env.timestamp == old_timestamp + 69
    assert boa.env.block_number == old_block + 69 // 12
