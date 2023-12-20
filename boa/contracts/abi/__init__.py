from typing import Any

from boa.environment import Address


def _encode_addresses(values: list) -> list:
    return [getattr(arg, "address", arg) for arg in values]


def _decode_addresses(abi_type: str, decoded: Any) -> Any:
    if abi_type == "address":
        return Address(decoded)
    if abi_type.startswith("address["):
        return [Address(i) for i in decoded]
    return decoded
