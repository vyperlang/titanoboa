import boa
import pytest

def test_fork_on_dirty_state_fails():
    boa.loads("foo: uint256")

    with pytest.raises(Exception, match="Cannot fork on a dirty state. Set force=True to override."):
        boa.env.fork("doesn't matter")
