import pytest

import boa
from boa import NetworkEnv

address = "0x0000000000000000000000000000000000000065"


def test_set_balance_network():
    with pytest.raises(NotImplementedError):
        NetworkEnv.set_balance(boa.env, address, 0)


def test_set_code_network():
    with pytest.raises(NotImplementedError):
        NetworkEnv.set_code(boa.env, address, b"")


def test_set_storage_network():
    with pytest.raises(NotImplementedError):
        NetworkEnv.set_storage(boa.env, address, 0, 0)


def test_balance():
    assert boa.env.get_balance(address) == 0
    balance = 1000
    boa.env.set_balance(address, balance)
    assert boa.env.get_balance(address) == balance


def test_code():
    assert boa.env.get_code(address) == b""
    code = b"some test code"
    boa.env.set_code(address, code)
    assert boa.env.get_code(address) == code


def test_storage():
    storage = 12381920371289
    assert boa.env.get_storage(address, 0) == 0
    boa.env.set_storage(address, 0, storage)
    assert boa.env.get_storage(address, 0) == storage
