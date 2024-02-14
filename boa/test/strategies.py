import random
import string
from typing import Any, Callable, Iterable, Optional, Union

from eth_abi.grammar import BasicType, TupleType, parse
from eth_utils import to_checksum_address
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.strategies import SearchStrategy
from hypothesis.strategies._internal.deferred import DeferredStrategy

from boa.contracts.vyper.vyper_contract import VyperFunction

# hypothesis fuzzing strategies, adapted from brownie 0.19.2 (86258c7bd)
# in the future these may be superseded by eth-stdlib.

TYPE_STR_TRANSLATIONS = {"byte": "bytes1", "decimal": "fixed168x10"}

ArrayLengthType = Union[int, list, None]
NumberType = Union[float, int, None]


# note: there are also utils in the vyper codebase we could use for
# this. also, in the future we may want to replace these with strategies
# that use vyper types instead of abi types.
def get_int_bounds(type_str: str) -> tuple[int, int]:
    """Returns the lower and upper bound for an integer type."""
    size = int(type_str.strip("uint") or 256)
    if size < 8 or size > 256 or size % 8:
        raise ValueError(f"Invalid type: {type_str}")
    if type_str.startswith("u"):
        return 0, 2**size - 1
    return -(2 ** (size - 1)), 2 ** (size - 1) - 1


class _DeferredStrategyRepr(DeferredStrategy):
    def __init__(self, fn: Callable, repr_target: str) -> None:
        super().__init__(fn)
        self._repr_target = repr_target

    def __repr__(self):
        return f"sampled_from({self._repr_target})"


def _exclude_filter(fn: Callable) -> Callable:
    def wrapper(*args: tuple, exclude: Any = None, **kwargs: int) -> SearchStrategy:
        strat = fn(*args, **kwargs)
        if exclude is None:
            return strat
        if callable(exclude):
            return strat.filter(exclude)
        if not isinstance(exclude, Iterable) or isinstance(exclude, str):
            exclude = (exclude,)
        strat = strat.filter(lambda k: k not in exclude)
        # make the filter repr more readable
        repr_ = strat.__repr__().rsplit(").filter", maxsplit=1)[0]
        strat._LazyStrategy__representation = f"{repr_}, exclude={exclude})"
        return strat

    return wrapper


def _check_numeric_bounds(
    type_str: str, min_value: NumberType, max_value: NumberType
) -> tuple[NumberType, NumberType]:
    lower, upper = get_int_bounds(type_str)
    min_final = lower if min_value is None else min_value
    max_final = upper if max_value is None else max_value
    if min_final < lower or max_final > upper or min_final > max_final:
        raise ValueError
    return min_final, max_final


@_exclude_filter
def _integer_strategy(
    type_str: str, min_value: Optional[int] = None, max_value: Optional[int] = None
) -> SearchStrategy:
    min_val, max_val = _check_numeric_bounds(type_str, min_value, max_value)
    return st.integers(min_val, max_val)


@_exclude_filter
def _decimal_strategy(
    min_value: NumberType = None, max_value: NumberType = None, places: int = 10
) -> SearchStrategy:
    min_value, max_value = _check_numeric_bounds("int128", min_value, max_value)
    return st.decimals(min_value=min_value, max_value=max_value, places=places)


def format_addr(t):
    if isinstance(t, str):
        t = t.encode("utf-8")
    return to_checksum_address(t.rjust(20, b"\x00"))


def generate_random_string(n):
    return ["".join(random.choices(string.ascii_lowercase, k=5)) for i in range(n)]


@_exclude_filter
def _address_strategy(length: Optional[int] = 100) -> SearchStrategy:
    random_strings = generate_random_string(length)
    # TODO: add addresses from the environment. probably everything in
    # boa.env._contracts, boa.env._blueprints and boa.env.eoa.
    accounts = [format_addr(i) for i in random_strings]
    return _DeferredStrategyRepr(
        lambda: st.sampled_from(list(accounts)[:length]), "accounts"
    )


@_exclude_filter
def _bytes_strategy(
    abi_type: BasicType, min_size: Optional[int] = None, max_size: Optional[int] = None
) -> SearchStrategy:
    size = abi_type.sub
    if not size:
        return st.binary(min_size=min_size or 1, max_size=max_size or 64)
    if size < 1 or size > 32:
        raise ValueError(f"Invalid type: {abi_type.to_type_str()}")
    if min_size is not None or max_size is not None:
        raise TypeError("Cannot specify size for fixed length bytes strategy")
    return st.binary(min_size=size, max_size=size)


@_exclude_filter
def _string_strategy(min_size: int = 0, max_size: int = 64) -> SearchStrategy:
    return st.text(min_size=min_size, max_size=max_size)


def _get_array_length(var_str: str, length: ArrayLengthType, dynamic_len: int) -> int:
    if not isinstance(length, (list, int)):
        raise TypeError(
            f"{var_str} must be of type int or list, not '{type(length).__name__}''"
        )
    if not isinstance(length, list):
        return length
    if len(length) != dynamic_len:
        raise ValueError(
            f"Length of '{var_str}' must equal the number of dynamic "
            f"dimensions for the given array ({dynamic_len})"
        )
    return length.pop()


def _array_strategy(
    abi_type: BasicType,
    min_length: ArrayLengthType = 1,
    max_length: ArrayLengthType = 8,
    unique: bool = False,
    **kwargs: Any,
) -> SearchStrategy:
    if abi_type.arrlist[-1]:
        min_len = max_len = abi_type.arrlist[-1][0]
    else:
        dynamic_len = len([i for i in abi_type.arrlist if not i])
        min_len = _get_array_length("min_length", min_length, dynamic_len)
        max_len = _get_array_length("max_length", max_length, dynamic_len)
    if abi_type.item_type.is_array:
        kwargs.update(min_length=min_length, max_length=max_length, unique=unique)
    base_strategy = strategy(abi_type.item_type.to_type_str(), **kwargs)
    strat = st.lists(base_strategy, min_size=min_len, max_size=max_len, unique=unique)
    # swap 'size' for 'length' in the repr
    repr_ = "length".join(strat.__repr__().rsplit("size", maxsplit=2))
    strat._LazyStrategy__representation = repr_  # type: ignore
    return strat


def _tuple_strategy(abi_type: TupleType) -> SearchStrategy:
    strategies = [strategy(i.to_type_str()) for i in abi_type.components]
    return st.tuples(*strategies)


# XXX: maybe rename to `abi`
def strategy(type_str: str, **kwargs: Any) -> SearchStrategy:
    type_str = TYPE_STR_TRANSLATIONS.get(type_str, type_str)
    if type_str == "fixed168x10":
        return _decimal_strategy(**kwargs)
    if type_str == "address":
        return _address_strategy(**kwargs)
    if type_str == "bool":
        return st.booleans(**kwargs)  # type: ignore
    if type_str == "string":
        return _string_strategy(**kwargs)

    abi_type = parse(type_str)
    if abi_type.is_array:
        return _array_strategy(abi_type, **kwargs)
    if isinstance(abi_type, TupleType):
        return _tuple_strategy(abi_type, **kwargs)  # type: ignore

    base = abi_type.base
    if base in ("int", "uint"):
        return _integer_strategy(type_str, **kwargs)
    if base == "bytes":
        return _bytes_strategy(abi_type, **kwargs)

    raise ValueError(f"No strategy available for type: {type_str}")


# XXX: is this the right module for me?
def fuzz(fn: VyperFunction):
    # usage:
    # @boa.fuzz(contract.function)
    # def f(arg_a, arg_b, arg_c):
    #     ...
    # f()
    # TODO how to test default values for overloaded functions?
    # or maybe just leave that to the user.
    strategies = {
        arg.name: strategy(arg.typ.canonical_abi_type) for arg in fn.func_t.arguments
    }

    return given(**strategies)
