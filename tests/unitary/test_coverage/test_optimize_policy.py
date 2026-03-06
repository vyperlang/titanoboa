"""Tests that lock the coverage optimization policy in interpret.py."""

import warnings

import coverage
import pytest
from vyper.compiler.settings import OptimizationLevel

import boa
from boa.environment import Env
from boa.interpret import compiler_data, set_cache_dir
from tests.coverage_utils import saved_coverage_state

SOURCE = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        return 0
"""


@pytest.fixture(autouse=True)
def isolate(tmp_path):
    from boa.interpret import _disk_cache

    saved = _disk_cache.cache_dir
    try:
        set_cache_dir(tmp_path)
        with saved_coverage_state():
            yield
    finally:
        set_cache_dir(saved)


def test_coverage_forces_no_optimization():
    """Default optimize becomes NONE when coverage is enabled, with warning."""
    Env._coverage_enabled = True
    Env._branch_coverage_enabled = True
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        data = compiler_data(SOURCE, "test", "test.vy")
    assert data.settings.optimize == OptimizationLevel.NONE
    cov_warnings = [x for x in w if "optimize=NONE" in str(x.message)]
    assert len(cov_warnings) == 1


def test_coverage_explicit_optimize_warns():
    """Explicit non-NONE optimize emits a warning when coverage is on."""
    Env._coverage_enabled = True
    Env._branch_coverage_enabled = True
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        data = compiler_data(SOURCE, "test", "test.vy", optimize=OptimizationLevel.GAS)
    assert len(w) == 1
    assert "branch coverage may be inaccurate" in str(w[0].message)
    # user's choice is preserved
    assert data.settings.optimize == OptimizationLevel.GAS


def test_coverage_explicit_none_no_warning():
    """Explicit optimize=NONE with coverage emits no warning."""
    Env._coverage_enabled = True
    Env._branch_coverage_enabled = True
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        compiler_data(SOURCE, "test", "test.vy", optimize=OptimizationLevel.NONE)
    cov_warnings = [x for x in w if "coverage" in str(x.message).lower()]
    assert cov_warnings == []


def test_no_coverage_no_forced_optimize():
    """Without coverage, optimize is NOT forced to NONE."""
    Env._coverage_enabled = False
    data = compiler_data(SOURCE, "test", "test.vy")
    assert data.settings.optimize != OptimizationLevel.NONE


def test_coverage_flag_without_branch_does_not_force_optimize():
    """Coverage flag alone without branch must not force optimize=NONE."""
    Env._coverage_enabled = True
    data = compiler_data(SOURCE, "test", "test.vy")
    assert data.settings.optimize != OptimizationLevel.NONE


def test_branch_mode_optimized_contract_skips_branch_arcs(tmp_path):
    """Optimized contracts should not record executed branch arcs."""
    vy_path = tmp_path / "optimized.vy"
    vy_path.write_text(SOURCE)

    cov = coverage.Coverage(branch=True, config_file=False, data_file=None)
    cov.set_option("run:plugins", ["boa.coverage"])
    cov.start()
    try:
        c = boa.load(str(vy_path), compiler_args={"optimize": OptimizationLevel.GAS})
        c.foo(10)
    finally:
        cov.stop()

    analysis = cov._analyze(str(vy_path))
    assert dict(analysis.executed_branch_arcs()) == {}
    assert cov.get_data().lines(str(vy_path))
