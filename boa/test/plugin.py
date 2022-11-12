import pytest
import boa


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    with boa.env.anchor():
        item.runtest()
