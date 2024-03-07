from unittest.mock import MagicMock

import boa
from boa.ipython import TitanoboaMagic, load_ipython_extension


def test_vyper_eval():
    magic = TitanoboaMagic()
    assert magic.vyper("empty(int8)") == 0
    assert magic.eval("empty(int8)") == 0


def test_vyper_deployer():
    cell = """
@external
@pure
def test() -> bool:
    return True
"""
    magic = TitanoboaMagic()
    magic.shell = MagicMock(user_ns={})
    deployer = magic.vyper("c", cell)
    assert deployer is boa.ipython._contracts["c"]
    assert deployer is magic.shell.user_ns["c"]
    assert deployer.deploy().test() == 1


def test_vyper_contract():
    cell = """
@external
@pure
def test() -> bool:
    return True
"""
    magic = TitanoboaMagic()
    magic.shell = MagicMock(user_ns={})
    contract = magic.contract("c", cell)
    assert contract is boa.ipython._contracts["c"]
    assert contract is magic.shell.user_ns["c"]
    assert contract.test() == 1


def test_load_ipython_extension():
    ipy_module = MagicMock()
    load_ipython_extension(ipy_module)
    ipy_module.register_magics.assert_called_once_with(TitanoboaMagic)
