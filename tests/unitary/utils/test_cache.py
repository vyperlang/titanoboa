from types import SimpleNamespace
from unittest.mock import patch

import pytest
from packaging.version import Version
from vyper.compiler import CompilerData

import boa.interpret as interpret
from boa.contracts.vyper.vyper_contract import VyperDeployer
from boa.interpret import (
    _disk_cache,
    _loads_partial_vvm,
    compiler_data,
    get_module_fingerprint,
    set_cache_dir,
)


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
    test1 = compiler_data(code, "test1", "test1.vy", VyperDeployer)  # noqa: F841
    test2 = compiler_data(code, "test2", "test2.vy", VyperDeployer)
    test3 = compiler_data(code, "test1", "test1.vy", VyperDeployer)  # noqa: F841
    # TODO: these asserts no longer work for vyper 0.4.1, investigate
    # assert test1 == test3, "Should hit the cache"
    # assert _to_dict(test1) != _to_dict(test2), "Should be different objects"
    assert str(test2.contract_path) == "test2.vy"


def test_cache_vvm():
    code = """
x: constant(int128) = 1000
"""
    version = Version("0.2.8")
    version2 = Version("0.3.1")
    assert _disk_cache is not None

    # Mock vvm.compile_source
    with patch("vvm.compile_source") as mock_compile:
        # Set up the mock to return a valid compiler output
        mock_compile.return_value = {"<stdin>": {"abi": [], "bytecode": "0x1234"}}

        assert mock_compile.call_count == 0

        # First call should hit vvm.compile_source
        test1 = _loads_partial_vvm(code, version, None, "fake_file.vy")
        assert mock_compile.call_count == 1

        # Second call should hit the cache
        test2 = _loads_partial_vvm(code, version, None, "fake_file.vy")
        assert mock_compile.call_count == 1

        # using a different filename should also hit the cache
        test3 = _loads_partial_vvm(code, version, None, "fake_fileeeee.vy")
        assert mock_compile.call_count == 1

        # using a different vyper version should *miss* the cache
        _loads_partial_vvm(code, version2, None, "fake_file.vy")
        assert mock_compile.call_count == 2

    assert test1.abi == test2.abi == test3.abi
    assert test1.bytecode == test2.bytecode == test3.bytecode
    assert test1.filename == test2.filename


def test_module_fingerprint_tracks_imported_module_changes(tmp_path, monkeypatch):
    data = _compiler_data_with_import(tmp_path, monkeypatch, imported_return_value=1)
    fingerprint = get_module_fingerprint(data.global_ctx)

    changed_data = _compiler_data_with_import(
        tmp_path, monkeypatch, imported_return_value=2
    )
    changed_fingerprint = get_module_fingerprint(changed_data.global_ctx)

    assert changed_fingerprint != fingerprint


def test_module_fingerprint_accepts_vyper_05_import_infos_shape(tmp_path, monkeypatch):
    data = _compiler_data_with_import(tmp_path, monkeypatch, imported_return_value=1)
    fingerprint = get_module_fingerprint(data.global_ctx)

    _rewrite_import_metadata_to_vyper_05_shape(data.global_ctx)

    assert get_module_fingerprint(data.global_ctx) == fingerprint


def _compiler_data_with_import(tmp_path, monkeypatch, imported_return_value):
    _write_imported_module(tmp_path, imported_return_value)
    monkeypatch.setattr(interpret, "_search_path", [str(tmp_path)])
    source = (tmp_path / "main.vy").read_text()
    return compiler_data(source, "main", tmp_path / "main.vy", VyperDeployer)


def _write_imported_module(tmp_path, imported_return_value):
    (tmp_path / "lib.vy").write_text(
        f"""
@internal
def x() -> uint256:
    return {imported_return_value}
"""
    )
    (tmp_path / "main.vy").write_text(
        """
import lib

@external
def foo() -> uint256:
    return lib.x()
"""
    )


def _rewrite_import_metadata_to_vyper_05_shape(module_t):
    for stmt in module_t.import_stmts:
        if "import_infos" in stmt._metadata:
            continue
        import_info = stmt._metadata.pop("import_info")
        stmt._metadata["import_infos"] = [_module_info_import(import_info)]


def _module_info_import(import_info):
    typ = import_info.typ
    if not hasattr(typ, "module_t"):
        typ = SimpleNamespace(module_t=typ)
    return SimpleNamespace(typ=typ, compiler_input=import_info.compiler_input)


def _to_dict(data: CompilerData) -> dict:
    """
    Serialize the `CompilerData` object to a dictionary for comparison.
    """
    d = data.__dict__.copy()
    d["input_bundle"] = d["input_bundle"].__dict__.copy()
    d["input_bundle"]["_cache"] = d["input_bundle"]["_cache"].__dict__.copy()
    return d
