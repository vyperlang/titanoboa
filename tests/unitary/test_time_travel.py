import pytest

import boa


def test_no_inputs():
    with pytest.raises(ValueError):
        boa.env.time_travel()


def test_block_travel():
    state = boa.env.evm.vm.state
    old_block = state.block_number
    old_timestamp = state.timestamp
    boa.env.time_travel(blocks=420)
    assert state.block_number == old_block + 420
    assert state.timestamp == old_timestamp + 420 * 12


def test_seconds_travel():
    state = boa.env.evm.vm.state
    old_timestamp = state.timestamp
    old_block = state.block_number
    boa.env.time_travel(seconds=69)
    assert state.timestamp == old_timestamp + 69
    assert state.block_number == old_block + 69 // 12
