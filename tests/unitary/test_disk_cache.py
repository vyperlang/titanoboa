import boa
from boa.interpret import set_cache_dir

LIB = """
x: uint256

@internal
@view
def _get() -> uint256:
    return self.x
"""

MID = """
import lib

uses: lib

@external
@view
def first() -> uint256:
    return lib._get()

@external
@view
def second() -> uint256:
    return lib.x
"""

MAIN = """
import lib
import mid

initializes: lib
initializes: mid[lib := lib]
exports: (mid.first, mid.second)
"""


def test_cache_reloads_module_used_by_initialized_module(tmp_path, monkeypatch):
    # the cached `CompilerData` reaches the same `ModuleInfo` through a
    # reference cycle via the AST; reading it back must not fail
    (tmp_path / "lib.vy").write_text(LIB)
    (tmp_path / "mid.vy").write_text(MID)
    (tmp_path / "main.vy").write_text(MAIN)
    monkeypatch.chdir(tmp_path)

    from boa.interpret import _disk_cache

    saved = _disk_cache.cache_dir
    try:
        set_cache_dir(tmp_path / "cache")
        first = boa.load_partial("main.vy")
        second = boa.load_partial("main.vy")
    finally:
        set_cache_dir(saved)

    assert second.compiler_data is not first.compiler_data
    assert second.compiler_data.bytecode == first.compiler_data.bytecode
