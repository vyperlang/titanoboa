from unittest.mock import patch

import pytest
from vyper.compiler import CompilerData

from boa.contracts.vyper.vyper_contract import VyperDeployer
from boa.interpret import _disk_cache, _loads_partial_vvm, compiler_data, set_cache_dir


@pytest.fixture(autouse=True)
def cache_dir(tmp_path):
    tmp = _disk_cache.cache_dir
    try:
        set_cache_dir(tmp_path)
        yield
    finally:
        set_cache_dir(tmp)


def test_cache_contract_name():
    code = """
x: constant(int128) = 1000
"""
    assert _disk_cache is not None
    test1 = compiler_data(code, "test1", __file__, VyperDeployer)
    test2 = compiler_data(code, "test2", __file__, VyperDeployer)
    test3 = compiler_data(code, "test1", __file__, VyperDeployer)
    assert _to_dict(test1) == _to_dict(test3), "Should hit the cache"
    assert _to_dict(test1) != _to_dict(test2), "Should be different objects"
    assert str(test2.contract_path) == "test2"


def test_cache_vvm():
    code = """
x: constant(int128) = 1000
"""
    version = "0.2.8"
    version2 = "0.3.1"
    assert _disk_cache is not None

    # Mock vvm.compile_source
    with patch("vvm.compile_source") as mock_compile:
        # Set up the mock to return a valid compiler output
        mock_compile.return_value = {"<stdin>": {"abi": [], "bytecode": "0x1234"}}

        assert mock_compile.call_count == 0

        # First call should hit vvm.compile_source
        test1 = _loads_partial_vvm(code, version, "fake_file.vy")
        assert mock_compile.call_count == 1

        # Second call should hit the cache
        test2 = _loads_partial_vvm(code, version, "fake_file.vy")
        assert mock_compile.call_count == 1

        # using a different filename should also hit the cache
        test3 = _loads_partial_vvm(code, version, "fake_fileeeee.vy")
        assert mock_compile.call_count == 1

        # using a different vyper version should *miss* the cache
        _loads_partial_vvm(code, version2, "fake_file.vy")
        assert mock_compile.call_count == 2

    assert test1.abi == test2.abi == test3.abi
    assert test1.bytecode == test2.bytecode == test3.bytecode
    assert test1.filename == test2.filename


def _to_dict(data: CompilerData) -> dict:
    """
    Serialize the `CompilerData` object to a dictionary for comparison.
    """
    d = data.__dict__.copy()
    d["input_bundle"] = d["input_bundle"].__dict__.copy()
    d["input_bundle"]["_cache"] = d["input_bundle"]["_cache"].__dict__.copy()
    return d
