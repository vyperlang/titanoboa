import pytest

from boa import Env, NetworkEnv


@pytest.fixture
def env():
    return Env()


def test_env_nickname(env):
    assert env.nickname == "pyevm"
