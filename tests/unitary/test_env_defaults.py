import pytest

from boa import Env, NetworkEnv


@pytest.fixture
def env():
    return Env()


@pytest.fixture
def network_env():
    url = "http://localhost:8545"
    return NetworkEnv(url)


def test_env_nickname(env):
    assert env.nickname == "pyevm"


def test_env_new_nickname(env):
    new_nickname = "new_nickname"
    env.set_nickname(new_nickname)
    assert env.nickname == new_nickname
