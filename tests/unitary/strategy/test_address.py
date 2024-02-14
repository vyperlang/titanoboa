from hypothesis import HealthCheck, given, settings
from hypothesis.strategies import SearchStrategy

from boa.test import strategy
from boa.util.abi import Address


def test_strategy():
    assert isinstance(strategy("address"), SearchStrategy)


@given(value=strategy("address"))
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_given(value):
    assert isinstance(value, Address)
