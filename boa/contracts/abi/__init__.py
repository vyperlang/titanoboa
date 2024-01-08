from collections import defaultdict
from typing import Any, Callable, Iterable, TypeVar, Union

from boa.environment import Address

T = TypeVar("T")
K = TypeVar("K")


def _encode_addresses(values: list) -> list:
    """
    Converts any object with an 'address' field into the address itself.
    This is to allow `Address` objects to be used.
    :param values: A list of values
    :return: The same list of values, with addresses converted.
    """
    return [getattr(arg, "address", arg) for arg in values]


def _decode_addresses(abi_type: Union[list, str], decoded: Any) -> Any:
    """
    Converts addresses received from the EVM into `Address` objects, recursively.
    :param abi_type: ABI type name. This should be a list if `decoded` is also a list.
    :param decoded: The decoded value(s) from the EVM.
    :return: The same value(s), with addresses converted.
    """
    if abi_type == "address":
        return Address(decoded)
    if isinstance(abi_type, str) and abi_type.startswith("address["):
        return [Address(i) for i in decoded]
    return decoded


def _parse_abi_type(abi: dict) -> Union[list, str]:
    """
    Parses an ABI type into a list of types.
    :param abi: The ABI type to parse.
    :return: A list of types or a single type.
    """
    if "components" in abi:
        assert abi["type"] == "tuple"  # sanity check
        return [_parse_abi_type(item) for item in abi["components"]]
    return abi["type"]


def _format_abi_type(types: list) -> str:
    """
    Converts a list of ABI types into a comma-separated string.
    """
    return ",".join(
        item if isinstance(item, str) else f"({_format_abi_type(item)})"
        for item in types
    )


def group_by(sequence: Iterable[T], key: Callable[[T], K]) -> dict[K, list[T]]:
    """
    Groups a sequence of items by a key function.
    :param sequence: The sequence to group.
    :param key: The key function.
    :return: A dictionary mapping keys to a list of items with that key.
    """
    result = defaultdict(list)
    for item in sequence:
        result[key(item)].append(item)
    return result
