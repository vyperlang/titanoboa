from functools import cached_property
from typing import TYPE_CHECKING, Optional, Union

from vyper.semantics.analysis.base import FunctionVisibility, StateMutability
from vyper.utils import method_id

from boa.contracts.abi import _encode_addresses, _format_abi_type, _parse_abi_type
from boa.util.abi import abi_decode, abi_encode, is_abi_encodable

if TYPE_CHECKING:
    from boa.contracts.abi.contract import ABIContract


class ABIFunction:
    """A single function in an ABI. It does not include overloads."""

    def __init__(self, abi: dict, contract_name: str):
        """
        :param abi: the ABI entry for this function
        :param contract_name: the name of the contract this function belongs to
        """
        self._abi = abi
        self._contract_name = contract_name
        self._function_visibility = FunctionVisibility.EXTERNAL
        self._mutability = StateMutability.from_abi(abi)
        self.contract: Optional["ABIContract"] = None

    @property
    def name(self) -> str:
        return self._abi["name"]

    @cached_property
    def argument_types(self) -> list:
        return [_parse_abi_type(i) for i in self._abi["inputs"]]

    @property
    def argument_count(self) -> int:
        return len(self.argument_types)

    @property
    def signature(self) -> str:
        return f"({_format_abi_type(self.argument_types)})"

    @cached_property
    def return_type(self) -> list:
        return [_parse_abi_type(o) for o in self._abi["outputs"]]

    @property
    def full_signature(self) -> str:
        return f"{self.name}{self.signature} -> {self.return_type}"

    @cached_property
    def method_id(self) -> bytes:
        return method_id(self.name + self.signature)

    def __repr__(self) -> str:
        return f"ABI {self._contract_name}.{self.full_signature}"

    def __str__(self) -> str:
        return repr(self)

    @property
    def is_mutable(self) -> bool:
        return self._mutability > StateMutability.VIEW

    def is_encodable(self, *args, **kwargs) -> bool:
        """Check whether this function accepts the given arguments after eventual encoding."""
        if len(kwargs) + len(args) != self.argument_count:
            return False
        parsed_args = self._merge_kwargs(*args, **kwargs)
        return all(
            is_abi_encodable(abi_type, arg)
            for abi_type, arg in zip(self.argument_types, parsed_args)
        )

    def matches(self, *args, **kwargs) -> bool:
        """Check whether this function matches the given arguments exactly."""
        parsed_args = self._merge_kwargs(*args, **kwargs)
        encoded_args = abi_encode(self.signature, args)
        decoded_args = abi_decode(self.signature, encoded_args)
        return map(type, parsed_args) == map(type, decoded_args)

    def _merge_kwargs(self, *args, **kwargs) -> list:
        """Merge positional and keyword arguments into a single list."""
        if len(kwargs) + len(args) != self.argument_count:
            raise TypeError(
                f"Bad args to `{repr(self)}` "
                f"(expected {self.argument_count} arguments, got {len(args)})"
            )
        try:
            kwarg_inputs = self._abi["inputs"][len(args) :]
            merged = list(args) + [kwargs.pop(i["name"]) for i in kwarg_inputs]
        except KeyError as e:
            error = f"Missing keyword argument {e} for `{self.signature}`. Passed {args} {kwargs}"
            raise TypeError(error)

        # allow address objects to be passed in place of addresses
        return _encode_addresses(merged)

    def __call__(self, *args, value=0, gas=None, sender=None, **kwargs):
        """Calls the function with the given arguments based on the ABI contract."""
        if not self.contract or not self.contract.env:
            raise Exception(f"Cannot call {self} without deploying contract.")

        args = self._merge_kwargs(*args, **kwargs)
        computation = self.contract.env.execute_code(
            to_address=self.contract.address,
            sender=sender,
            data=self.method_id + abi_encode(self.signature, args),
            value=value,
            gas=gas,
            is_modifying=self.is_mutable,
            contract=self.contract,
        )

        match self.contract.marshal_to_python(computation, self.return_type):
            case ():
                return None
            case (single,):
                return single
            case multiple:
                return tuple(multiple)


class ABIOverload:
    """
    Represents a set of functions that have the same name but different
    argument types. This is used to implement function overloading.
    """

    @staticmethod
    def create(
        functions: list[ABIFunction], contract: "ABIContract"
    ) -> Union["ABIOverload", ABIFunction]:
        """
        Create an ABIOverload if there are multiple functions, otherwise
        return the single function.
        :param functions: a list of functions with the same name
        :param contract: the ABIContract that these functions belong to
        """
        for f in functions:
            f.contract = contract
        if len(functions) == 1:
            return functions[0]
        return ABIOverload(functions)

    def __init__(self, functions: list[ABIFunction]):
        self.functions = functions

    @cached_property
    def name(self):
        return self.functions[0].name

    def __call__(self, *args, **kwargs):
        """
        Call the function that matches the given arguments.
        :raises Exception: if not a single function is found
        """
        match [f for f in self.functions if f.is_encodable(*args, **kwargs)]:
            case [function]:
                return function(*args, **kwargs)
            case []:
                raise Exception(
                    f"Could not find matching {self.name} function for given arguments."
                )
            case multiple:
                raise Exception(
                    f"Ambiguous call to {self.name}. "
                    f"Arguments can be encoded to multiple overloads: "
                    f"{', '.join(f.signature for f in multiple)}."
                )
