from typing import Generator

import hypothesis
import pytest

import boa

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


def pytest_configure(config):
    config.addinivalue_line("markers", "ignore_isolation")
    config.addinivalue_line("markers", "profile_calls")

    pytest.call_profile = {}


def _items_to_profile(item):

    profile_test = item.get_closest_marker("profile_calls") is not None
    if not profile_test:
        return False
    return True


def _enable_call_profiling(item):

    if not _items_to_profile(item):
        return

    boa.env.profile_calls = True


def _profile_calls():

    combined_calls = pytest.call_profile
    for d in (pytest.call_profile, boa.env.profiled_calls):

        for key, value in d.items():

            if key not in combined_calls.keys():
                combined_calls[key] = value
            else:
                combined_calls[key].extend(value)

    pytest.call_profile = combined_calls


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator:

    ignore_isolation = item.get_closest_marker("ignore_isolation") is not None
    call_profiling_enabled = item.get_closest_marker("profile_calls") is not None

    with boa.env.store_call_profile(call_profiling_enabled):

        if not ignore_isolation:
            with boa.env.anchor():
                yield
        else:
            yield

        _profile_calls()


def pytest_sessionfinish(session, exitstatus):

    if not pytest.call_profile:
        return

    import statistics
    import sys

    from rich.console import Console
    from rich.table import Table

    # generate means, stds for each
    call_profiles = {}
    for key, gas_used in pytest.call_profile.items():
        call_profile = {}

        call_profile["mean"] = statistics.mean(gas_used)
        call_profile["median"] = statistics.median(gas_used)
        call_profile["min"] = min(gas_used)
        call_profile["max"] = max(gas_used)
        if len(gas_used) == 1:
            call_profile["stdev"] = 0
        else:
            call_profile["stdev"] = int(round(statistics.stdev(gas_used), 2))

        call_profiles[key] = call_profile

    # print rich table
    table = Table(title="\nCall Profile")
    table.add_column("Method", justify="right", style="cyan", no_wrap=True)
    table.add_column("Mean", style="magenta")
    table.add_column("Median", style="magenta")
    table.add_column("Stdev", style="magenta")
    table.add_column("Min", style="magenta")
    table.add_column("Max", style="magenta")

    for key in call_profiles.keys():
        profile = call_profiles[key]
        table.add_row(
            key,
            str(profile["mean"]),
            str(profile["median"]),
            str(profile["stdev"]),
            str(profile["min"]),
            str(profile["max"]),
        )

    console = Console(file=sys.stdout)
    console.print(table)
