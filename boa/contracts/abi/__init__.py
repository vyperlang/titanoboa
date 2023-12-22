from typing import Any, Union

from boa.environment import Address


def _encode_addresses(values: list) -> list:
    return [getattr(arg, "address", arg) for arg in values]


def _decode_addresses(abi_type: Union[list, str], decoded: Any) -> Any:
    if abi_type == "address":
        return Address(decoded)
    if isinstance(abi_type, str) and abi_type.startswith("address["):
        return [Address(i) for i in decoded]
    return decoded


def _parse_abi_type(abi: dict) -> list:
    if "components" in abi:
        return [_parse_abi_type(item) for item in abi["components"]]
    return abi["type"]


def _format_abi_type(types: list) -> str:
    return ",".join(
        item if isinstance(item, str) else f"({_format_abi_type(item)})"
        for item in types
    )
