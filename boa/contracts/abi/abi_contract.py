from collections import defaultdict
from functools import cached_property
from os.path import basename
from typing import Any, Optional, Union
from warnings import warn

from eth.abc import ComputationAPI
from vyper.semantics.analysis.base import FunctionVisibility, StateMutability
from vyper.utils import method_id

from boa.contracts.base_evm_contract import (
    BoaError,
    StackTrace,
    _BaseEVMContract,
    _handle_child_trace,
)
from boa.contracts.utils import decode_addresses, encode_addresses
from boa.environment import Address
from boa.util.abi import ABIError, abi_decode, abi_encode, is_abi_encodable


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
        return [_abi_from_json(i) for i in self._abi["inputs"]]

    @property
    def argument_count(self) -> int:
        return len(self.argument_types)

    @property
    def signature(self) -> str:
        return f"({_format_abi_type(self.argument_types)})"

    @cached_property
    def return_type(self) -> list:
        return [_abi_from_json(o) for o in self._abi["outputs"]]

    @property
    def full_signature(self) -> str:
        return f"{self.name}{self.signature}"

    @property
    def pretty_signature(self) -> str:
        return f"{self.name}{self.signature} -> {self.return_type}"

    @cached_property
    def method_id(self) -> bytes:
        return method_id(self.name + self.signature)

    def __repr__(self) -> str:
        return f"ABI {self._contract_name}.{self.pretty_signature}"

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
        return encode_addresses(merged)

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
    def name(self) -> str:
        return self.functions[0].name

    def __call__(self, *args, disambiguate_signature=None, **kwargs):
        """
        Call the function that matches the given arguments.
        :raises Exception: if a single function is not found
        """
        if disambiguate_signature is None:
            matches = [f for f in self.functions if f.is_encodable(*args, **kwargs)]
        else:
            matches = [
                f for f in self.functions if disambiguate_signature == f.full_signature
            ]
            assert len(matches) <= 1, "ABI signature must be unique"

        match matches:
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
                    f"{', '.join(self.name + f.signature for f in multiple)}. "
                    f"(Hint: try using `disambiguate_signature=` to disambiguate)."
                )


class ABIContract(_BaseEVMContract):
    """A contract that has been deployed to the blockchain and created via an ABI."""

    def __init__(
        self,
        name: str,
        functions: list[ABIFunction],
        address: Address,
        filename: Optional[str] = None,
        env=None,
    ):
        super().__init__(env, filename=filename, address=address)
        self._name = name
        self._functions = functions
        self._bytecode = self.env.vm.state.get_code(address.canonical_address)
        if not self._bytecode:
            warn(
                f"Requested {self} but there is no bytecode at that address!",
                stacklevel=2,
            )

        overloads = defaultdict(list)
        for f in functions:
            overloads[f.name].append(f)

        for name, group in overloads.items():
            setattr(self, name, ABIOverload.create(group, self))

        self._address = Address(address)

    @cached_property
    def method_id_map(self):
        """
        Returns a mapping from method id to function object.
        This is used to create the stack trace when an error occurs.
        """
        return {function.method_id: function for function in self._functions}

    def marshal_to_python(self, computation, abi_type: list[str]) -> tuple[Any, ...]:
        """
        Convert the output of a contract call to a Python object.
        :param computation: the computation object returned by `execute_code`
        :param abi_type: the ABI type of the return value.
        """
        # when there's no contract in the address, the computation output is empty
        if computation.is_error:
            return self.handle_error(computation)

        schema = f"({_format_abi_type(abi_type)})"
        try:
            decoded = abi_decode(schema, computation.output)
        except ABIError as e:
            raise BoaError(self.stack_trace(computation)) from e

        return tuple(decode_addresses(typ, val) for typ, val in zip(abi_type, decoded))

    def stack_trace(self, computation: ComputationAPI) -> StackTrace:
        """
        Create a stack trace for a failed contract call.
        """
        calldata_method_id = bytes(computation.msg.data[:4])
        if calldata_method_id in self.method_id_map:
            function = self.method_id_map[calldata_method_id]
            msg = f"  ({self}.{function.pretty_signature})"
        else:
            # Method might not be specified in the ABI
            msg = f"  (unknown method id {self}.0x{calldata_method_id.hex()})"

        return_trace = StackTrace([msg])
        return _handle_child_trace(computation, self.env, return_trace)

    @property
    def deployer(self) -> "ABIContractFactory":
        """
        Returns a factory that can be used to retrieve another deployed contract.
        """
        return ABIContractFactory(self._name, self._functions)

    def __repr__(self):
        file_str = f" (file {self.filename})" if self.filename else ""
        warn_str = "" if self._bytecode else " (WARNING: no bytecode at this address!)"
        return f"<{self._name} interface at {self.address}{warn_str}>{file_str}"


class ABIContractFactory:
    """
    Represents an ABI contract that has not been coupled with an address yet.
    This is named `Factory` instead of `Deployer` because it doesn't actually
    do any contract deployment.
    """

    def __init__(
        self, name: str, functions: list["ABIFunction"], filename: Optional[str] = None
    ):
        self._name = name
        self._functions = functions
        self._filename = filename

    @classmethod
    def from_abi_dict(cls, abi, name="<anonymous contract>"):
        functions = [
            ABIFunction(item, name) for item in abi if item.get("type") == "function"
        ]
        return cls(basename(name), functions, filename=name)

    def at(self, address: Address | str) -> ABIContract:
        """
        Create an ABI contract object for a deployed contract at `address`.
        """
        address = Address(address)
        contract = ABIContract(self._name, self._functions, address, self._filename)
        contract.env.register_contract(address, contract)
        return contract


def _abi_from_json(abi: dict) -> list | str:
    """
    Parses an ABI type into a list of types.
    :param abi: The ABI type to parse.
    :return: A list of types or a single type.
    """
    if "components" in abi:
        assert abi["type"] == "tuple"  # sanity check
        return [_abi_from_json(item) for item in abi["components"]]
    return abi["type"]


def _format_abi_type(types: list) -> str:
    """
    Converts a list of ABI types into a comma-separated string.
    """
    return ",".join(
        item if isinstance(item, str) else f"({_format_abi_type(item)})"
        for item in types
    )
