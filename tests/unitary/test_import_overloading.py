import pytest
import sys
import contextlib
import os

from boa.interpret import VyperDeployer

@contextlib.contextmanager
def mock_sys_path(path):
    anchor = sys.path
    try:
        sys.path = [path]
        yield
    finally:
        sys.path = anchor

@contextlib.contextmanager
def workdir(path):
    tmp = os.getcwd()
    try:
        os.chdir(path)
        with mock_sys_path("."):
            yield
    finally:
        os.chdir(tmp)

def test_imports(tmp_path):
    code = """
totalSupply: public(uint256)

@external
def __init__(initial_supply: uint256):
    self.totalSupply = initial_supply
    """

    filepath = tmp_path / "foo" / "bar.vy"
    filepath.parent.mkdir(parents=True)

    with filepath.open("w") as f:
        f.write(code)

    with workdir(tmp_path):
        from foo import bar

        assert isinstance(bar, VyperDeployer)
        contract = bar.deploy(100)
        assert contract.totalSupply() == 100

        from foo import bar as baz
        assert isinstance(baz, VyperDeployer)
        assert baz is bar
