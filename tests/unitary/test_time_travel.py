import pytest

import boa


def test_no_inputs():
    with pytest.raises(ValueError):
        boa.env.time_travel()


def test_block_travel():
    old_block = boa.env.block.number
    old_timestamp = boa.env.block.timestamp
    boa.env.time_travel(blocks=420)
    assert boa.env.block.number == old_block + 420
    assert boa.env.block.timestamp == old_timestamp + 420 * 12


def test_seconds_travel():
    old_timestamp = boa.env.block.timestamp
    old_block = boa.env.block.number
    boa.env.time_travel(seconds=69)
    assert boa.env.block.timestamp == old_timestamp + 69
    assert boa.env.block.number == old_block + 69 // 12


def test_block():
    assert boa.env.block.number == 1
    with boa.env.block.number(2):
        assert boa.env.block.number == 2
        boa.env.block.number = 3
        assert boa.env.block.number == 3
    assert boa.env.block.number == 1
