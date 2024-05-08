import pytest

import boa
from boa.vm.fork import AccountDBFork

address = "0x0000000000000000000000000000000000000065"


def test_code_non_fork():
    with pytest.raises(AssertionError):
        boa.env.set_code(address, b"")


def test_storage_non_fork():
    with pytest.raises(AssertionError):
        boa.env.set_storage(address, 0, 0)


def test_code():
    boa.env.evm._set_account_db_class(AccountDBFork)
    assert boa.env.get_code(address) == b""
    code = b"some test code"
    boa.env.set_code(address, code)
    assert boa.env.get_code(address) == code


def test_storage(monkeypatch):
    storage = 12381920371289
    boa.env.evm._set_account_db_class(AccountDBFork)
    assert boa.env.get_storage(address, 0) == 0
    boa.env.set_storage(address, 0, storage)
    assert boa.env.get_storage(address, 0) == storage
