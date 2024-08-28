import pytest

from boa import Env


@pytest.fixture
def env():
    return Env()


def test_env_nickname(env):
    assert env.nickname == "pyevm"
