from collections import defaultdict
from functools import cached_property
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
from boa.util.abi import ABIError, Address, abi_decode, abi_encode, is_abi_encodable


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
    def name(self) -> str | None:
        if self.is_constructor:
            return None
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
        assert self.name is not None, "Constructor does not have a name."
        return f"{self.name}{self.signature}"

    @property
    def pretty_signature(self) -> str:
        return f"{self.pretty_name}{self.signature} -> {self.return_type}"

    @cached_property
    def pretty_name(self):
        if self.is_constructor:
            return "constructor"
        return self.name

    @cached_property
    def method_id(self) -> bytes:
        assert self.name, "Constructor does not have a method id."
        return method_id(self.name + self.signature)

    @cached_property
    def is_constructor(self):
        return self._abi["type"] == "constructor"

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

    def prepare_calldata(self, *args, **kwargs) -> bytes:
        """Prepare the call data for the function call."""
        abi_args = self._merge_kwargs(*args, **kwargs)
        encoded_args = abi_encode(self.signature, abi_args)
        if self.is_constructor:
            return encoded_args
        return self.method_id + encoded_args

    def _merge_kwargs(self, *args, **kwargs) -> list:
        """Merge positional and keyword arguments into a single list."""
        if len(kwargs) + len(args) != self.argument_count:
            raise TypeError(
                f"Bad args to `{repr(self)}` (expected {self.argument_count} "
                f"arguments, got {len(args)} args and {len(kwargs)} kwargs)"
            )
        try:
            kwarg_inputs = self._abi["inputs"][len(args) :]
            return list(args) + [kwargs.pop(i["name"]) for i in kwarg_inputs]
        except KeyError as e:
            error = f"Missing keyword argument {e} for `{self.signature}`. Passed {args} {kwargs}"
            raise TypeError(error)

    def __call__(self, *args, value=0, gas=None, sender=None, **kwargs):
        """Calls the function with the given arguments based on the ABI contract."""
        if not self.contract or not self.contract.env:
            raise Exception(f"Cannot call {self} without deploying contract.")

        computation = self.contract.env.execute_code(
            to_address=self.contract.address,
            sender=sender,
            data=self.prepare_calldata(*args, **kwargs),
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
    def name(self) -> str | None:
        return self.functions[0].name

    def prepare_calldata(self, *args, disambiguate_signature=None, **kwargs) -> bytes:
        """Prepare the calldata for the function that matches the given arguments."""
        function = self._pick_overload(
            *args, disambiguate_signature=disambiguate_signature, **kwargs
        )
        return function.prepare_calldata(*args, **kwargs)

    def __call__(
        self,
        *args,
        value=0,
        gas=None,
        sender=None,
        disambiguate_signature=None,
        **kwargs,
    ):
        """
        Call the function that matches the given arguments.
        :raises Exception: if a single function is not found
        """
        function = self._pick_overload(
            *args, disambiguate_signature=disambiguate_signature, **kwargs
        )
        return function(*args, value=value, gas=gas, sender=sender, **kwargs)

    def _pick_overload(
        self, *args, disambiguate_signature=None, **kwargs
    ) -> ABIFunction:
        """Pick the function that matches the given arguments."""
        if disambiguate_signature is None:
            matches = [f for f in self.functions if f.is_encodable(*args, **kwargs)]
        else:
            matches = [
                f for f in self.functions if disambiguate_signature == f.full_signature
            ]
            assert len(matches) <= 1, "ABI signature must be unique"

        assert self.name, "Constructor does not have a name."
        match matches:
            case [function]:
                return function
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
    """A deployed contract loaded via an ABI."""

    def __init__(
        self,
        name: str,
        abi: list[dict],
        functions: list[ABIFunction],
        address: Address,
        filename: Optional[str] = None,
        env=None,
    ):
        super().__init__(env, filename=filename, address=address)
        self._name = name
        self._abi = abi
        self._functions = functions

        self._bytecode = self.env.get_code(address)
        if not self._bytecode:
            warn(
                f"Requested {self} but there is no bytecode at that address!",
                stacklevel=2,
            )

        overloads = defaultdict(list)
        for f in self._functions:
            overloads[f.name].append(f)

        for fn_name, group in overloads.items():
            if fn_name is not None:  # constructors have no name
                setattr(self, fn_name, ABIOverload.create(group, self))

        self._address = Address(address)
        self._computation: Optional[ComputationAPI] = None

    @property
    def abi(self):
        return self._abi

    @cached_property
    def method_id_map(self):
        """
        Returns a mapping from method id to function object.
        This is used to create the stack trace when an error occurs.
        """
        return {
            function.method_id: function
            for function in self._functions
            if not function.is_constructor
        }

    def marshal_to_python(self, computation, abi_type: list[str]) -> tuple[Any, ...]:
        """
        Convert the output of a contract call to a Python object.
        :param computation: the computation object returned by `execute_code`
        :param abi_type: the ABI type of the return value.
        """
        self._computation = computation
        # when there's no contract in the address, the computation output is empty
        if computation.is_error:
            return self.handle_error(computation)

        schema = f"({_format_abi_type(abi_type)})"
        try:
            return abi_decode(schema, computation.output)
        except ABIError as e:
            raise BoaError(self.stack_trace(computation)) from e

    def stack_trace(self, computation: ComputationAPI) -> StackTrace:
        """
        Create a stack trace for a failed contract call.
        """
        reason = ""
        if computation.is_error:
            reason = " ".join(str(arg) for arg in computation.error.args if arg != b"")

        calldata_method_id = bytes(computation.msg.data[:4])
        if calldata_method_id in self.method_id_map:
            function = self.method_id_map[calldata_method_id]
            msg = f"  {reason}({self}.{function.pretty_signature})"
        else:
            # Method might not be specified in the ABI
            msg = f"  {reason}(unknown method id {self}.0x{calldata_method_id.hex()})"

        return_trace = StackTrace([msg])
        return _handle_child_trace(computation, self.env, return_trace)

    @property
    def deployer(self) -> "ABIContractFactory":
        """
        Returns a factory that can be used to retrieve another deployed contract.
        """
        return ABIContractFactory(self._name, self._abi, filename=self.filename)

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

    def __init__(self, name: str, abi: list[dict], filename: Optional[str] = None):
        self._name = name
        self._abi = abi
        self.filename = filename

    @cached_property
    def abi(self):
        return self._abi

    @cached_property
    def functions(self):
        return [
            ABIFunction(item, self._name)
            for item in self.abi
            if item.get("type") == "function"
        ]

    @classmethod
    def from_abi_dict(cls, abi, name="<anonymous contract>", filename=None):
        return cls(name, abi, filename)

    def at(self, address: Address | str) -> ABIContract:
        """
        Create an ABI contract object for a deployed contract at `address`.
        """
        address = Address(address)
        contract = ABIContract(
            self._name, self._abi, self.functions, address, self.filename
        )
        contract.env.register_contract(address, contract)
        return contract


def _abi_from_json(abi: dict) -> str:
    """
    Parses an ABI type into its schema string.
    :param abi: The ABI type to parse.
    :return: The schema string for the given abi type.
    """
    if "components" in abi:
        components = ",".join([_abi_from_json(item) for item in abi["components"]])
        if abi["type"] == "tuple":
            return f"({components})"
        if abi["type"] == "tuple[]":
            return f"({components})[]"
        raise ValueError("Components found in non-tuple type " + abi["type"])

    return abi["type"]


def _format_abi_type(types: list) -> str:
    """
    Converts a list of ABI types into a comma-separated string.
    """
    return ",".join(
        item if isinstance(item, str) else f"({_format_abi_type(item)})"
        for item in types
    )
