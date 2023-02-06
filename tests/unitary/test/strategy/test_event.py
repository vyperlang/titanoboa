import itertools

import pytest
from hypothesis import given
from hypothesis.strategies import SearchStrategy

from boa.test import strategy
from boa.vyper.event import Event

BASE_TYPES = ["address", "bool", "bytes32", "decimal", "int", "string", "uint"]


@pytest.mark.parametrize("base1,base2", itertools.product(BASE_TYPES, BASE_TYPES))
def test_strategy(base1, base2):
    # ensure we can test on tuples
    # tuple generates strategies for underlying types
    assert isinstance(strategy(f"({base1},({base2},{base1}))"), SearchStrategy)
    assert isinstance(strategy(f"({base1})"), SearchStrategy)
    assert isinstance(strategy(f"({base2},{base2})"), SearchStrategy)
    assert isinstance(strategy(f"(({base1},{base2}))"), SearchStrategy)


@pytest.mark.parametrize(
    "param1,param2,param3,param4",
    itertools.product(BASE_TYPES, BASE_TYPES, BASE_TYPES, BASE_TYPES),
)
def test_topics_saved_to_event(param1, param2, param3, param4):
    topics = [param1, param2, param3, param4]
    event = Event("0x0", "0x0", "", topics, [], {})
    assert event.topics == topics
    assert event.args == []
    assert len(event.ordered_args()) == len(
        topics
    )  # need event_type for ordered_args to work


@pytest.mark.parametrize(
    "param1,param2,param3,param4",
    itertools.product(BASE_TYPES, BASE_TYPES, BASE_TYPES, BASE_TYPES),
)
def test_args_saved_to_event(param1, param2, param3, param4):
    args = [param1, param2, param3, param4]
    event = Event("0x0", "0x0", "", [], args, {})
    assert event.args == args
    assert event.topics == []
    assert len(event.ordered_args()) == len(
        args
    )  # need event_type for ordered_args to work


@pytest.mark.parametrize(
    "param1,param2,param3,param4",
    itertools.product(BASE_TYPES, BASE_TYPES, BASE_TYPES, BASE_TYPES),
)
def test_args_and_topics_saved_to_event(param1, param2, param3, param4):
    args = [param3, param4]
    topics = [param1, param2]
    event = Event("0x0", "0x0", "", topics, args, {})
    assert len(event.args) == len(args)
    assert len(event.topics) == len(topics)
    assert event.args == args
    assert event.topics == topics


@pytest.mark.parametrize(
    "param1,param2,param3,param4",
    itertools.product(BASE_TYPES, BASE_TYPES, BASE_TYPES, BASE_TYPES),
)
def test_args_ordered_to_event_param_sequence(param1, param2, param3, param4):
    topics = [param2, param3]
    args = [param1, param4]

    # need to generate Event.event_type to say which params are indexed
    # which determines their order in ordered_args()
    ordered_params = [param1, param2, param3, param4]
    event_type = {
        "indexed": [False, True, True, False],
        "arguments": {
            "keys": [
                "param1",
                "param2",
                "param3",
                "param4",
            ]  # order params in ordered_args according to actual params
        },
    }

    event = Event("0x0", "0x0", event_type, topics, args, {})
    assert event.args == args
    assert event.topics == topics
    assert len(event.ordered_args()) == len(topics) + len(args)

    for idx, key, value in enumerate(event.ordered_args()):
        assert key == event_type.values[idx]
        assert value == ordered_params[idx]


@pytest.mark.parametrize(
    "param1,param2,param3,param4",
    itertools.product(BASE_TYPES, BASE_TYPES, BASE_TYPES, BASE_TYPES),
)
def test_args_map_values_match_ordered_args(param1, param2, param3, param4):
    args = [param3, param4, param2, param1]
    event_type = {
        "indexed": [False, True, True, False],
        "arguments": {
            "keys": [
                "param3",
                "param4",
                "param2",
                "param1",
            ]  # order params in ordered_args according to actual params
        },
    }
    event = Event("0x0", "0x0", event_type, [], args, {})
    assert event.args == args
    for idx, k in enumerate(event_type.arguments.keys()):
        assert (
            event.args_map[k] == args[idx]
        )  # keys must be in same order as event params


@pytest.mark.parametrize(
    "param1,param2,param3,param4",
    itertools.product(BASE_TYPES, BASE_TYPES, BASE_TYPES, BASE_TYPES),
)
def test_repr_is_ordered_args(param1, param2, param3, param4):
    # assumes repr format is "event EventName(key=value,key1=value1)
    args = [param3, param4, param2, param1]
    event_type = {
        "indexed": [False, True, True, False],
        "arguments": {
            "keys": [
                "param3",
                "param4",
                "param2",
                "param1",
            ]  # order params in ordered_args according to actual params
        },
    }
    event = Event("0x0", "0x0", event_type, [], args, {})
    print("get event __repr__", event.__repr__())
    # expected_repr = f"event "
    # assert event.__repr__() ==


@given(value=strategy("(uint8,(bool,bytes4),decimal[3])"))
def test_event_is_emitted(value):
    assert len(value) == 3
    # mock erc20 transfer
    # erc20.get_logs
    # event[0].topics ===
    # event[0].args ===
    # event[0].ordered_args ===
