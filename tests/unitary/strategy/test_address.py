from hypothesis import HealthCheck, given, settings
from hypothesis.strategies._internal.deferred import DeferredStrategy

from boa.test import strategy


def test_strategy():
    assert isinstance(strategy("address"), DeferredStrategy)


@given(value=strategy("address"))
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_given(value):
    assert isinstance(value, str)


def test_repr():
    assert repr(strategy("address")) == "sampled_from(accounts)"
