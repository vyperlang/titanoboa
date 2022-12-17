from typing import Generator

import hypothesis
import pytest

import boa
from boa.profiling import print_call_profile

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


def pytest_sessionfinish(session, exitstatus):

    print_call_profile(boa.env)
