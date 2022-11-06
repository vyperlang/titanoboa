#!/usr/bin/python3

from decimal import Decimal, getcontext
from typing import Any, TypeVar, Union

try:
    from vyper.exceptions import DecimalOverrideException
except ImportError:
    DecimalOverrideException = BaseException  # regular catch blocks shouldn't catch

import eth_utils
from hexbytes import HexBytes

UNITS = {
    "wei": 0,
    "kwei": 3,
    "babbage": 3,
    "mwei": 6,
    "lovelace": 6,
    "gwei": 9,
    "shannon": 9,
    "microether": 12,
    "szabo": 12,
    "milliether": 15,
    "finney": 15,
    "ether": 18,
}

WeiInputTypes = TypeVar("WeiInputTypes", str, float, int, None)


class Wei(int):

    """Integer subclass that converts a value to wei and allows comparison against
    similarly formatted values.

    Useful for the following formats:
        * a string specifying the unit: "10 ether", "300 gwei", "0.25 shannon"
        * a large float in scientific notation, where direct conversion to int
          would cause inaccuracy: 8.3e32
        * bytes: b'\xff\xff'
        * hex strings: "0x330124\" """

    # Known typing error: https://github.com/python/mypy/issues/4290
    def __new__(cls, value: Any) -> Any:  # type: ignore
        return super().__new__(cls, _to_wei(value))  # type: ignore

    def __hash__(self) -> int:
        return super().__hash__()

    def __lt__(self, other: Any) -> bool:
        return super().__lt__(_to_wei(other))

    def __le__(self, other: Any) -> bool:
        return super().__le__(_to_wei(other))

    def __eq__(self, other: Any) -> bool:
        try:
            return super().__eq__(_to_wei(other))
        except TypeError:
            return False

    def __ne__(self, other: Any) -> bool:
        try:
            return super().__ne__(_to_wei(other))
        except TypeError:
            return True

    def __ge__(self, other: Any) -> bool:
        return super().__ge__(_to_wei(other))

    def __gt__(self, other: Any) -> bool:
        return super().__gt__(_to_wei(other))

    def __add__(self, other: Any) -> "Wei":
        return Wei(super().__add__(_to_wei(other)))

    def __sub__(self, other: Any) -> "Wei":
        return Wei(super().__sub__(_to_wei(other)))

    def to(self, unit: str) -> "Fixed":
        """
        Returns a converted denomination of the stored wei value.
        Accepts any valid ether unit denomination as string, like:
        "gwei", "milliether", "finney", "ether".

        :param unit: An ether denomination like "ether" or "gwei"
        :return: A 'Fixed' type number in the specified denomination
        """
        try:
            return Fixed(self * Fixed(10) ** -UNITS[unit])
        except KeyError:
            raise TypeError(f'Cannot convert wei to unknown unit: "{unit}". ') from None


def _to_wei(value: WeiInputTypes) -> int:
    original = value
    if isinstance(value, bytes):
        value = HexBytes(value).hex()
    if value is None or value == "0x":
        return 0
    if isinstance(value, float) and "e+" in str(value):
        num_str, dec = str(value).split("e+")
        num = num_str.split(".") if "." in num_str else [num_str, ""]
        return int(num[0] + num[1][: int(dec)] + "0" * (int(dec) - len(num[1])))
    if not isinstance(value, str):
        return _return_int(original, value)
    if value[:2] == "0x":
        return int(value, 16)
    for unit, dec in UNITS.items():
        if " " + unit not in value:
            continue
        num_str = value.split(" ")[0]
        num = num_str.split(".") if "." in num_str else [num_str, ""]
        return int(num[0] + num[1][: int(dec)] + "0" * (int(dec) - len(num[1])))
    return _return_int(original, value)


def _return_int(original: Any, value: Any) -> int:
    try:
        return int(value)
    except ValueError:
        raise TypeError(f"Cannot convert {type(original).__name__} '{original}' to wei.")


class Fixed(Decimal):

    """
    Decimal subclass that allows comparison against strings, integers and Wei.

    Raises TypeError when operations are attempted against floats.
    """

    # Known typing error: https://github.com/python/mypy/issues/4290
    def __new__(cls, value: Any) -> Any:  # type: ignore
        return super().__new__(cls, _to_fixed(value))  # type: ignore

    def __repr__(self) -> str:
        return f"Fixed('{str(self)}')"

    def __hash__(self) -> int:
        return super().__hash__()

    def __lt__(self, other: Any) -> bool:  # type: ignore
        return super().__lt__(_to_fixed(other))

    def __le__(self, other: Any) -> bool:  # type: ignore
        return super().__le__(_to_fixed(other))

    def __eq__(self, other: Any) -> bool:  # type: ignore
        if isinstance(other, float):
            raise TypeError("Cannot compare to floating point - use a string instead")
        try:
            return super().__eq__(_to_fixed(other))
        except TypeError:
            return False

    def __ne__(self, other: Any) -> bool:
        if isinstance(other, float):
            raise TypeError("Cannot compare to floating point - use a string instead")
        try:
            return super().__ne__(_to_fixed(other))
        except TypeError:
            return True

    def __ge__(self, other: Any) -> bool:  # type: ignore
        return super().__ge__(_to_fixed(other))

    def __gt__(self, other: Any) -> bool:  # type: ignore
        return super().__gt__(_to_fixed(other))

    def __add__(self, other: Any) -> "Fixed":  # type: ignore
        return Fixed(super().__add__(_to_fixed(other)))

    def __sub__(self, other: Any) -> "Fixed":  # type: ignore
        return Fixed(super().__sub__(_to_fixed(other)))


def _to_fixed(value: Any) -> Decimal:
    if isinstance(value, float):
        raise TypeError("Cannot convert float to decimal - use a string instead")

    if isinstance(value, (str, bytes)):
        try:
            value = Wei(value)
        except TypeError:
            pass
    try:
        try:
            # until vyper v0.3.1 we can mess with the precision
            ctx = getcontext()
            ctx.prec = 78
        except DecimalOverrideException:
            pass  # vyper set the precision, do nothing.
        return Decimal(value)
    except Exception as e:
        raise TypeError(f"Cannot convert {type(value).__name__} '{value}' to decimal.") from e


class EthAddress(str):

    """String subclass that raises TypeError when compared to a non-address."""

    def __new__(cls, value: Union[bytes, str]) -> str:
        converted_value = value
        if isinstance(value, bytes):
            converted_value = HexBytes(value).hex()
        converted_value = eth_utils.add_0x_prefix(str(converted_value))  # type: ignore
        try:
            converted_value = eth_utils.to_checksum_address(converted_value)
        except ValueError:
            raise ValueError(f"'{value}' is not a valid ETH address") from None
        return super().__new__(cls, converted_value)  # type: ignore

    def __hash__(self) -> int:
        return super().__hash__()

    def __eq__(self, other: Any) -> bool:
        return _address_compare(str(self), other)

    def __ne__(self, other: Any) -> bool:
        return not _address_compare(str(self), other)


def _address_compare(a: Any, b: Any) -> bool:
    b = str(b)
    if not b.startswith("0x") or not eth_utils.is_hex(b) or len(b) != 42:
        raise TypeError(f"Invalid type for comparison: '{b}' is not a valid address")
    return a.lower() == b.lower()
