from collections import namedtuple
from dataclasses import dataclass
from typing import Any, NamedTuple

from boa.util.abi import Address, abi_decode


@dataclass
class RawLogEntry:
    log_id: int  # internal py-evm log id, for ordering purposes
    address: str  # canonical address
    topics: list[int]  # list of topics
    data: bytes  # list of encoded args


def decode_log(
    addr: Address, event_abi_for: dict[int, dict], log_entry: RawLogEntry
) -> NamedTuple:
    # decode a log given (json) event abi. constructs a fresh namedtuple
    # type to put the data into, with a schema like
    # namedtuple(event_name, ["address", *event_fields])
    # TODO: resolve these cyclic imports. probably, `_parse_complex` and
    # `_abi_from_json` belong in an abi utility module of some sort
    from boa.contracts.abi.abi_contract import (
        _abi_from_json,
        _format_abi_type,
        _parse_complex,
    )

    assert addr.canonical_address == log_entry.address
    event_hash = log_entry.topics[0]

    # map from event id to event abi for the topic
    if event_hash not in event_abi_for:
        # our abi is wrong, we can't decode it. fail loudly.
        msg = f"can't find event with hash {hex(event_hash)} in abi"
        msg += f" (possible events: {event_abi_for})"
        raise ValueError(msg)

    event_abi = event_abi_for[event_hash]

    topic_abis = []
    arg_abis = []

    # add `address` to the tuple. this is prevented from being an
    # actual fieldname in vyper and solidity since it is a reserved keyword
    # in both languages. if for some reason some abi actually has a field
    # named `address`, it will be renamed by namedtuple(rename=True).
    tuple_names = ["address"]

    for item_abi in event_abi["inputs"]:
        is_topic = item_abi["indexed"]
        assert isinstance(is_topic, bool)
        if not is_topic:
            arg_abis.append(item_abi)
        else:
            topic_abis.append(item_abi)

        tuple_names.append(item_abi["name"])

    # to investigate: is this a hotspot?
    tuple_typ = namedtuple(event_abi["name"], tuple_names, rename=True)  # type: ignore[misc]

    decoded_topics = []
    for topic_abi, topic_int in zip(topic_abis, log_entry.topics[1:]):
        # convert to bytes for abi decoder
        encoded_topic = topic_int.to_bytes(32, "big")
        decoded_topics.append(abi_decode(_abi_from_json(topic_abi), encoded_topic))
    args_selector = _format_abi_type([_abi_from_json(arg_abi) for arg_abi in arg_abis])

    decoded_args = abi_decode(args_selector, log_entry.data)

    topics_ix = 0
    args_ix = 0

    xs: list[Any] = [Address(log_entry.address)]

    # re-align the evm topic + args lists with the way they appear in the
    # abi ex. Transfer(indexed address, address, indexed address)
    for item_abi in event_abi["inputs"]:
        is_topic = item_abi["indexed"]
        if is_topic:
            abi = topic_abis[topics_ix]
            topic = decoded_topics[topics_ix]
            # topic abi is currently never complex, but use _parse_complex
            # as future-proofing mechanism
            xs.append(_parse_complex(abi, topic))
            topics_ix += 1
        else:
            abi = arg_abis[args_ix]
            arg = decoded_args[args_ix]
            xs.append(_parse_complex(abi, arg))
            args_ix += 1

    return tuple_typ(*xs)
