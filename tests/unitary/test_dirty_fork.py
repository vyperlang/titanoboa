import pytest

import boa


def test_fork_on_dirty_state_fails():
    boa.loads("foo: uint256")

    with pytest.raises(
        Exception,
        match="Cannot fork with dirty state. Set allow_dirty=True to override.",
    ):
        boa.fork("fake url", None)


def test_fork_on_dirty_state_fails2():
    boa.env.set_balance(boa.env.eoa, 1)

    with pytest.raises(
        Exception,
        match="Cannot fork with dirty state. Set allow_dirty=True to override.",
    ):
        boa.fork("fake url", None)
