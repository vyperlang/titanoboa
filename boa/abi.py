import warnings
from collections import Counter
from functools import cached_property
from itertools import groupby
from os.path import basename
from typing import Any, Optional, Union

from _operator import attrgetter
from eth.abc import ComputationAPI
from vyper.semantics.analysis.base import FunctionVisibility, StateMutability
from vyper.utils import method_id

from boa.environment import Address
from boa.util.abi import abi_decode, abi_encode, is_abi_encodable
from boa.util.evm import _EvmContract
from boa.util.exceptions import StackTrace, _handle_child_trace


class ABIFunction:
    def __init__(self, abi: dict, contract_name: str):
        self._abi = abi
        self._contract_name = contract_name
        self._function_visibility = FunctionVisibility.EXTERNAL
        self._mutability = StateMutability.from_abi(abi)
        self.contract: Optional["ABIContract"] = None

    @property
    def name(self):
        return self._abi["name"]

    @cached_property
    def argument_types(self) -> list[str]:
        return [i["type"] for i in self._abi["inputs"]]

    @property
    def argument_count(self) -> int:
        return len(self.argument_types)

    @property
    def signature(self) -> str:
        return f"({','.join(self.argument_types)})"

    @cached_property
    def return_type(self) -> list[str]:
        return [o["type"] for o in self._abi["outputs"]]

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
        parsed_args = self._merge_kwargs(*args, **kwargs)
        assert len(parsed_args) == len(self.argument_types)  # sanity check
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
    @staticmethod
    def create(
        functions: list[ABIFunction], contract: "ABIContract"
    ) -> Union["ABIOverload", ABIFunction]:
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
        arg_count = len(kwargs) + len(args)
        candidates = [
            f
            for f in self.functions
            if f.argument_count == arg_count and f.is_encodable(*args, **kwargs)
        ]

        match candidates:
            case [single_match]:
                return single_match(*args, **kwargs)
            case []:
                error = (
                    f"Could not find matching {self.name} function for given arguments."
                )
                raise Exception(error)
            case multiple:
                raise Exception(
                    f"Ambiguous call to {self.name}. "
                    f"Arguments can be encoded to multiple overloads: "
                    f"{', '.join(f.signature for f in multiple)}."
                )


class ABIContract(_EvmContract):
    """
    A contract that has been deployed to the blockchain.
    We do not have the Vyper source code for this contract.
    """

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

        for name, group in groupby(self._functions, key=attrgetter("name")):
            functions = list(group)
            setattr(self, name, ABIOverload.create(functions, self))

        self._address = Address(address)

    @cached_property
    def method_id_map(self):
        return {function.method_id: function for function in self._functions}

    def marshal_to_python(self, computation, abi_type: list[str]) -> tuple[Any, ...]:
        """
        Convert the output of a contract call to a Python object.
        :param computation: the computation object returned by `execute_code`
        :param abi_type: the ABI type of the return value.
        """
        if computation.is_error:
            return self.handle_error(computation)

        schema = f"({','.join(abi_type)})"
        decoded = abi_decode(schema, computation.output)
        return tuple(_decode_addresses(typ, val) for typ, val in zip(abi_type, decoded))

    def stack_trace(self, computation: ComputationAPI):
        calldata_method_id = bytes(computation.msg.data[:4])
        if calldata_method_id in self.method_id_map:
            function = self.method_id_map[calldata_method_id]
            msg = f"  (unknown location in {self}.{function.full_signature})"
        else:
            # Method might not be specified in the ABI
            msg = f"  (unknown method id {self}.0x{calldata_method_id.hex()})"

        return_trace = StackTrace([msg])
        return _handle_child_trace(computation, self.env, return_trace)

    @property
    def deployer(self):
        return ABIContractFactory(self._name, self._functions)

    def __repr__(self):
        file_str = f" (file {self.filename})" if self.filename else ""
        return f"<{self._name} interface at {self.address}>{file_str}"


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
    def from_abi_dict(cls, abi, name: Optional[str] = None):
        if name is None:
            name = "<anonymous contract>"

        functions = [
            ABIFunction(item, name) for item in abi if item.get("type") == "function"
        ]

        # warn on functions with same name
        for function_name, count in Counter(f.name for f in functions).items():
            if count > 1:
                warnings.warn(
                    f"{name} overloads {function_name}! overloaded methods "
                    "might not work correctly at this time",
                    stacklevel=1,
                )

        return cls(basename(name), functions, filename=name)

    def at(self, address) -> ABIContract:
        """
        Create an ABI contract object for a deployed contract at `address`.
        """
        address = Address(address)

        ret = ABIContract(self._name, self._functions, address, self._filename)

        bytecode = ret.env.vm.state.get_code(address.canonical_address)
        if not bytecode:
            raise ValueError(
                f"Requested {ret} but there is no bytecode at that address!"
            )

        ret.env.register_contract(address, ret)

        return ret


def _decode_addresses(abi_type: str, decoded: Any) -> Any:
    if abi_type == "address":
        return Address(decoded)
    if abi_type == "address[]":
        return [Address(i) for i in decoded]
    return decoded


def _encode_addresses(values: list) -> list:
    return [getattr(arg, "address", arg) for arg in values]
