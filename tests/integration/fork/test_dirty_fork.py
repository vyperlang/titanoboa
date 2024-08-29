import pytest

import boa


@pytest.fixture(scope="module", autouse=True)
def _env():
    # start from clean env
    with boa.swap_env(boa.Env()):
        yield


def test_fork_on_dirty_state_fails(rpc_url):
    assert not boa.env.evm.is_forked  # sanity check autouse=True works

    boa.loads("foo: uint256")

    with pytest.raises(
        Exception,
        match="Cannot fork with dirty state. Set allow_dirty=True to override.",
    ):
        boa.fork(rpc_url)


def test_fork_on_dirty_state_fails2(rpc_url):
    boa.env.set_balance(boa.env.eoa, 1)

    with pytest.raises(
        Exception,
        match="Cannot fork with dirty state. Set allow_dirty=True to override.",
    ):
        boa.fork(rpc_url)


def test_allow_dirty(rpc_url):
    boa.env.set_balance(boa.env.eoa, 1)

    boa.fork(rpc_url, allow_dirty=True)
