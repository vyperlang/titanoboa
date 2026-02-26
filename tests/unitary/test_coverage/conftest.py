import contextlib
import os
import tempfile

import coverage
import pytest

import boa
from boa.coverage import TitanoboaReporter
from boa.environment import Env
from boa.interpret import _disk_cache, set_cache_dir


@pytest.fixture(autouse=True)
def isolate_cache(tmp_path):
    saved = _disk_cache.cache_dir
    try:
        set_cache_dir(tmp_path)
        yield
    finally:
        set_cache_dir(saved)


def _check_branch_coverage(vyper_source, calls_fn):
    """Run branch coverage in-process and return missing_branch_arcs.

    Args:
        vyper_source: Vyper source code string
        calls_fn: callable(contract) that exercises the contract

    Returns:
        dict of {line: [target_lines]} for missing branch arcs
    """
    saved_coverage = Env._coverage_enabled
    fd, vy_path = tempfile.mkstemp(suffix=".vy")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(vyper_source)

        cov = coverage.Coverage(branch=True, config_file=False, data_file=None)
        cov.set_option("run:plugins", ["boa.coverage"])
        cov.start()
        try:
            c = boa.load(vy_path)
            calls_fn(c)
        finally:
            cov.stop()

        analysis = cov._analyze(vy_path)
        return dict(analysis.missing_branch_arcs())
    finally:
        Env._coverage_enabled = saved_coverage
        os.unlink(vy_path)


def _check_full_branch_coverage(vyper_source, calls_fn):
    """Return (possible_arcs, executed_arcs, missing_arcs) for branch coverage.

    possible_arcs: set of (from_line, to_line) tuples
    executed_arcs: dict {line: [target_lines]} for executed branch arcs
    missing_arcs: dict {line: [target_lines]} for missing branch arcs
    """
    saved_coverage = Env._coverage_enabled
    fd, vy_path = tempfile.mkstemp(suffix=".vy")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(vyper_source)
        cov = coverage.Coverage(branch=True, config_file=False, data_file=None)
        cov.set_option("run:plugins", ["boa.coverage"])
        cov.start()
        try:
            c = boa.load(vy_path)
            calls_fn(c)
        finally:
            cov.stop()
        analysis = cov._analyze(vy_path)
        return (
            set(analysis.arc_possibilities()),
            dict(analysis.executed_branch_arcs()),
            dict(analysis.missing_branch_arcs()),
        )
    finally:
        Env._coverage_enabled = saved_coverage
        os.unlink(vy_path)


@contextlib.contextmanager
def _reporter_for(vyper_source):
    fd, vy_path = tempfile.mkstemp(suffix=".vy")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(vyper_source)
        yield TitanoboaReporter(vy_path)
    finally:
        os.unlink(vy_path)
