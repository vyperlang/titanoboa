import pytest
import boa
import hypothesis


def pytest_configure(config):
    config.addinivalue_line("markers", "ignore_isolation")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item: pytest.Item) -> None:

    if not item.get_closest_marker("ignore_isolation"):
        with boa.env.anchor():
            yield
    else:
        yield
