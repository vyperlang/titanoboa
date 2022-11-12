import pytest
import boa


def pytest_configure(config):
    config.addinivalue_line("markers", "ignore_isolation")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    if not item.get_closest_marker("ignore_isolation"):
        with boa.env.anchor():
            item.runtest()
    else:
        item.runtest()
