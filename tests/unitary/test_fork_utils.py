import pytest

import boa
from boa import NetworkEnv

address = "0x0000000000000000000000000000000000000065"


def test_code_non_fork():
    with pytest.raises(AssertionError):
        NetworkEnv.set_code(boa.env, address, b"")


def test_storage_non_fork():
    with pytest.raises(AssertionError):
        NetworkEnv.set_storage(boa.env, address, 0, 0)


def test_code():
    assert boa.env.get_code(address) == b""
    code = b"some test code"
    boa.env.set_code(address, code)
    assert boa.env.get_code(address) == code


def test_storage(monkeypatch):
    storage = 12381920371289
    assert boa.env.get_storage(address, 0) == 0
    boa.env.set_storage(address, 0, storage)
    assert boa.env.get_storage(address, 0) == storage
