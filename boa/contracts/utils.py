from typing import Any

from boa.environment import Address


def encode_addresses(values: list) -> list:
    """
    Converts any object with an 'address' field into the address itself.
    This is to allow `Address` objects to be used.
    :param values: A list of values
    :return: The same list of values, with addresses converted.
    """
    return [getattr(arg, "address", arg) for arg in values]


def decode_addresses(abi_type: list | str, decoded: Any) -> Any:
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
