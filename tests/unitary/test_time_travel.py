import pytest

import boa


def test_revert_negative_inputs():
    with pytest.raises(ValueError):
        boa.env.time_travel(seconds=-1)
    with pytest.raises(ValueError):
        boa.env.time_travel(blocks=-1)


def test_no_inputs():
    with pytest.raises(ValueError):
        boa.env.time_travel()


def test_block_travel():
    old_block = boa.env.block_number
    old_timestamp = boa.env.timestamp
    boa.env.time_travel(blocks=42069, block_delta=12)
    assert boa.env.block_number == old_block + 42069
    assert boa.env.timestamp == old_timestamp + 42069 * 12


def test_seconds_travel():
    old_timestamp = boa.env.timestamp
    old_block = boa.env.block_number
    boa.env.time_travel(seconds=42069, block_delta=12)
    assert boa.env.timestamp == old_timestamp + 42069
    assert boa.env.block_number == old_block + 42069 // 12
