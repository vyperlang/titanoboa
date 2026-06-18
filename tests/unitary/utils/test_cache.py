from types import SimpleNamespace
from unittest.mock import patch

import pytest
from packaging.version import Version
from vyper.compiler import CompilerData

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


def test_module_fingerprint_accepts_import_infos_metadata():
    dependency = _module_for_fingerprint("dependency")
    module_info = SimpleNamespace(module_t=dependency)
    import_info = _import_info_for_fingerprint(module_info)
    root = _module_for_fingerprint("root", _import_stmt(import_infos=[import_info]))

    assert get_module_fingerprint(root) != get_module_fingerprint(
        _module_for_fingerprint("root")
    )


def test_module_fingerprint_accepts_legacy_import_info_metadata():
    import_info = _import_info_for_fingerprint(
        typ=SimpleNamespace(), compiler_input_hash="dependency"
    )
    root = _module_for_fingerprint("root", _import_stmt(import_info=import_info))

    assert get_module_fingerprint(root) != get_module_fingerprint(
        _module_for_fingerprint("root")
    )


def _module_for_fingerprint(source_hash, *import_stmts):
    return SimpleNamespace(
        import_stmts=list(import_stmts),
        _module=SimpleNamespace(source_sha256sum=source_hash),
    )


def _import_stmt(**metadata):
    return SimpleNamespace(_metadata=metadata)


def _import_info_for_fingerprint(typ, compiler_input_hash="unused"):
    return SimpleNamespace(
        typ=typ,
        compiler_input=SimpleNamespace(sha256sum=compiler_input_hash),
    )


def _to_dict(data: CompilerData) -> dict:
    """
    Serialize the `CompilerData` object to a dictionary for comparison.
    """
    d = data.__dict__.copy()
    d["input_bundle"] = d["input_bundle"].__dict__.copy()
    d["input_bundle"]["_cache"] = d["input_bundle"]["_cache"].__dict__.copy()
    return d
