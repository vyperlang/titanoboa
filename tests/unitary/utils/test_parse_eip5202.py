import pytest

from boa.util.eip5202 import parse_erc5202

ERC5202_VERSION = 0


def test_parse_erc5202():
    blueprint_bytecode = b"\xFE\x71\x00abcd"
    assert parse_erc5202(blueprint_bytecode) == (ERC5202_VERSION, None, b"abcd")


def test_parse_erc5202_with_data():
    blueprint_bytecode = b"\xFE\x71\x01\x04dataabcd"
    assert parse_erc5202(blueprint_bytecode) == (ERC5202_VERSION, b"data", b"abcd")


def test_parse_erc5202_bad_bytecode():
    with pytest.raises(ValueError) as e:
        parse_erc5202(b"")
    assert str(e.value) == "Not a blueprint!"


def test_parse_erc5202_reserved_bits():
    with pytest.raises(ValueError) as e:
        parse_erc5202(b"\xFE\x71\x03")
    assert str(e.value) == "Reserved bits are set"


def test_parse_erc5202_empty_initcode():
    with pytest.raises(ValueError) as e:
        parse_erc5202(b"\xFE\x71\x01\x04")
    assert str(e.value) == "Empty initcode!"
