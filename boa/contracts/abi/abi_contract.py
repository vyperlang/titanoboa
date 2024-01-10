from collections import defaultdict
from functools import cached_property
from os.path import basename
from typing import Any, Optional
from warnings import warn

from eth.abc import ComputationAPI

from boa.contracts.abi import _decode_addresses, _format_abi_type
from boa.contracts.abi.function import ABIFunction, ABIOverload
from boa.contracts.evm_contract import BaseEVMContract
from boa.contracts.stack_trace import StackTrace, _handle_child_trace
from boa.environment import Address
from boa.util.abi import abi_decode


class ABIContract(BaseEVMContract):
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
        is_missing_output = bool(abi_type and not computation.output)
        if computation.is_error or is_missing_output:
            return self.handle_error(computation)

        schema = f"({_format_abi_type(abi_type)})"
        decoded = abi_decode(schema, computation.output)
        return tuple(_decode_addresses(typ, val) for typ, val in zip(abi_type, decoded))

    def stack_trace(self, computation: ComputationAPI) -> StackTrace:
        """
        Create a stack trace for a failed contract call.
        """
        calldata_method_id = bytes(computation.msg.data[:4])
        if calldata_method_id in self.method_id_map:
            function = self.method_id_map[calldata_method_id]
            msg = f"  ({self}.{function.full_signature})"
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
