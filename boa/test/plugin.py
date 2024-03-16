import contextlib
import warnings
from typing import Generator

import hypothesis
import pytest

import boa
from boa.profiling import get_call_profile_table, get_line_profile_table
from boa.vm.gas_meters import ProfilingGasMeter

# monkey patch HypothesisHandle. this fixes underlying isolation for
# hypothesis.given() and also hypothesis stateful functionality.
_old_init = hypothesis.core.HypothesisHandle.__init__


def _HypothesisHandle__init__(self, *args, **kwargs):
    _old_init(self, *args, **kwargs)

    t = self.inner_test

    def f(*args, **kwargs):
        with boa.env.anchor():
            t(*args, **kwargs)

    self.inner_test = f


hypothesis.core.HypothesisHandle.__init__ = _HypothesisHandle__init__  # type: ignore


def pytest_addoption(parser):
    parser.addoption(
        "--gas-profile",
        action="store_true",
        help="Profile gas used by contracts called in tests",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "ignore_isolation: ignore test isolation")
    config.addinivalue_line("markers", "ignore_gas_profiling: do not report on gas")
    config.addinivalue_line("markers", "gas_profile: report on gas")


def pytest_collection_modifyitems(config, items):
    if config.getoption("gas_profile"):
        for item in items:
            ignore_gas_profiling = item.get_closest_marker("ignore_gas_profiling")
            if not ignore_gas_profiling:
                item.add_marker("gas_profile")


_fixture_map = {}
_task_list = set()


def pytest_fixture_setup(fixturedef, request):
    ctx = boa.env.anchor()
    assert id(fixturedef) not in _fixture_map, "bad invariant"
    _fixture_map[id(fixturedef)] = ctx
    ctx.__enter__()


def pytest_fixture_post_finalizer(fixturedef, request):
    fid = id(fixturedef)

    if fid not in _fixture_map:
        warnings.warn("possible bug in titanoboa! bad fixture tracking", stacklevel=1)
        return

    # there are outstanding bugs in pytest where the finalizers get
    # run out of order, so we need to maintain a task list and defer
    # execution of out-of-order finalizers until all the finalizers
    # that should have come before them get run.
    _task_list.add(fid)

    while (fid := next(reversed(_fixture_map.keys()), None)) in _task_list:
        ctx = _fixture_map.pop(fid)
        _task_list.remove(fid)
        ctx.__exit__(None, None, None)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator:
    ignore_isolation = item.get_closest_marker("ignore_isolation") is not None
    profiling_ignored = item.get_closest_marker("ignore_profiling") is not None
    profiling_enabled = item.get_closest_marker("gas_profile") is not None

    if profiling_enabled and profiling_ignored:
        raise ValueError("Cannot ignore profiling and profile at the same time")

    @contextlib.contextmanager
    def _toggle_profiling(enabled: bool = False) -> Generator:
        if enabled:
            with boa.env.gas_meter_class(ProfilingGasMeter):
                yield
        else:
            yield

    with _toggle_profiling(profiling_enabled):
        if not ignore_isolation:
            with boa.env.anchor():
                yield
        else:
            yield


def pytest_sessionfinish(session, exitstatus):
    if boa.env._cached_call_profiles:
        import sys

        from rich.console import Console

        console = Console(file=sys.stdout)
        console.print(get_call_profile_table(boa.env))
        console.print(get_line_profile_table(boa.env))
