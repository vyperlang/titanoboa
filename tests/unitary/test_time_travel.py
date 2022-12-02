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
    state = boa.env.vm.state
    old_block = state.block_number
    old_timestamp = state.timestamp
    boa.env.time_travel(blocks=42069, block_delta=12)
    assert state.block_number == old_block + 42069
    assert state.timestamp == old_timestamp + 42069 * 12


def test_seconds_travel():
    state = boa.env.vm.state
    old_timestamp = state.timestamp
    old_block = state.block_number
    boa.env.time_travel(seconds=42069, block_delta=12)
    assert state.timestamp == old_timestamp + 42069
    assert state.block_number == old_block + 42069 // 12
