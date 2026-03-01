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


@contextlib.contextmanager
def _coverage_session(vyper_source, calls_fn):
    """Set up coverage, load+exercise contract, yield analysis object."""
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
        yield cov._analyze(vy_path)
    finally:
        Env._coverage_enabled = saved_coverage
        os.unlink(vy_path)


@contextlib.contextmanager
def _coverage_session_multi(sources_dict, setup_fn):
    """Set up coverage with multiple .vy files, yield (cov, paths_dict).

    sources_dict: {name: vyper_source_string}
    setup_fn: callable(paths_dict) that loads/exercises contracts
    """
    saved_coverage = Env._coverage_enabled
    paths = {}
    created_paths = []
    try:
        for name, src in sources_dict.items():
            fd, path = tempfile.mkstemp(suffix=".vy")
            created_paths.append(path)
            with os.fdopen(fd, "w") as f:
                f.write(src)
            paths[name] = path
        cov = coverage.Coverage(branch=True, config_file=False, data_file=None)
        cov.set_option("run:plugins", ["boa.coverage"])
        cov.start()
        try:
            setup_fn(paths)
        finally:
            cov.stop()
        yield cov, paths
    finally:
        Env._coverage_enabled = saved_coverage
        for path in created_paths:
            os.unlink(path)


@contextlib.contextmanager
def _coverage_session_lines(vyper_source, calls_fn):
    """Set up statement-only coverage (branch=False), yield (cov, vy_path)."""
    saved_coverage = Env._coverage_enabled
    fd, vy_path = tempfile.mkstemp(suffix=".vy")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(vyper_source)
        cov = coverage.Coverage(branch=False, config_file=False, data_file=None)
        cov.set_option("run:plugins", ["boa.coverage"])
        cov.start()
        try:
            c = boa.load(vy_path)
            calls_fn(c)
        finally:
            cov.stop()
        yield cov, vy_path
    finally:
        Env._coverage_enabled = saved_coverage
        os.unlink(vy_path)


def _check_branch_coverage(vyper_source, calls_fn):
    """Run branch coverage in-process and return missing_branch_arcs."""
    with _coverage_session(vyper_source, calls_fn) as analysis:
        return dict(analysis.missing_branch_arcs())


def _check_full_branch_coverage(vyper_source, calls_fn):
    """Return (possible_arcs, executed_arcs, missing_arcs) for branch coverage."""
    with _coverage_session(vyper_source, calls_fn) as analysis:
        return (
            set(analysis.arc_possibilities()),
            dict(analysis.executed_branch_arcs()),
            dict(analysis.missing_branch_arcs()),
        )


@contextlib.contextmanager
def _reporter_for(vyper_source):
    fd, vy_path = tempfile.mkstemp(suffix=".vy")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(vyper_source)
        yield TitanoboaReporter(vy_path)
    finally:
        os.unlink(vy_path)
