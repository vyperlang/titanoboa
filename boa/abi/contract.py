import warnings
from collections import Counter
from functools import cached_property
from itertools import groupby
from os.path import basename
from typing import Optional

from _operator import attrgetter
from eth.abc import ComputationAPI
from vyper.codegen.core import calculate_type_for_external_return
from vyper.semantics.types import EventT, TupleT

from boa.abi.errors import BoaError, StackTrace, _handle_child_trace
from boa.abi.event import ABIEvent
from boa.abi.function import ABIFunction, ABIOverload
from boa.environment import Address, Env
from boa.profiling import cache_gas_used_for_computation
from boa.util.abi import abi_decode
from boa.util.exceptions import strip_internal_frames
from boa.vm.gas_meters import ProfilingGasMeter


class _EvmContract:
    """
    Base class for ABI and Vyper contracts.
    """

    def __init__(
        self,
        env: Optional[Env] = None,
        filename: Optional[str] = None,
        address: Optional[Address] = None,
    ):
        self.env = env or Env.get_singleton()
        self._address = address  # this is overridden by subclasses
        self.filename = filename
        self._computation: Optional[ComputationAPI] = None

    def stack_trace(self, computation: ComputationAPI):
        raise NotImplementedError

    def marshal_to_python(self, computation, vyper_typ):
        self._computation = computation  # for further inspection

        if computation.is_error:
            self.handle_error(computation)

        # cache gas used for call if profiling is enabled
        gas_meter = self.env.vm.state.computation_class._gas_meter_class
        if gas_meter == ProfilingGasMeter:
            cache_gas_used_for_computation(self, computation)

        if vyper_typ is None:
            return None

        return_typ = calculate_type_for_external_return(vyper_typ)
        ret = abi_decode(return_typ.abi_type.selector_name(), computation.output)

        # unwrap the tuple if needed
        if not isinstance(vyper_typ, TupleT):
            (ret,) = ret

        # todo: is this really specific to vyper?
        from boa.vyper.contract import vyper_object

        return vyper_object(ret, vyper_typ)

    def handle_error(self, computation) -> None:
        try:
            raise BoaError(self.stack_trace(computation))
        except BoaError as b:
            # modify the error so the traceback starts in userland.
            # inspired by answers in https://stackoverflow.com/q/1603940/
            raise strip_internal_frames(b) from None

    @property
    def address(self) -> Address:
        return self._address


class ABIContract(_EvmContract):
    """
    A contract that has been deployed to the blockchain.
    We do not have the Vyper source code for this contract.
    """

    def __init__(
        self,
        name: str,
        functions: list["ABIFunction"],
        events: list["EventT"],
        address: Address,
        filename: Optional[str] = None,
        env=None,
    ):
        super().__init__(env, filename=filename, address=address)
        self._name = name
        self._events = events
        self._functions = functions

        for name, functions in groupby(self._functions, key=attrgetter("name")):
            functions = list(functions)
            fn = functions[0] if len(functions) == 1 else ABIOverload(functions)
            fn.contract = self
            setattr(self, name, fn)

        self._address = Address(address)

    @cached_property
    def method_id_map(self):
        ret = {}
        for function in self._functions:
            for abi_sig, method_id_int in function.method_ids.items():
                method_id_bytes = method_id_int.to_bytes(4, "big")
                assert method_id_bytes not in ret  # vyper guarantees unique method ids
                ret[method_id_bytes] = abi_sig
        return ret

    def stack_trace(self, computation: ComputationAPI):
        calldata_method_id = bytes(computation.msg.data[:4])
        if calldata_method_id in self.method_id_map:
            msg = f"  (unknown location in {self}.{self.method_id_map[calldata_method_id]})"
        else:
            # Method might not be specified in the ABI
            msg = f"  (unknown method id {self}.0x{calldata_method_id.hex()})"

        return_trace = StackTrace([msg])
        return _handle_child_trace(computation, self.env, return_trace)

    @property
    def deployer(self):
        return ABIContractFactory(self._name, self._functions, self._events)

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
        self,
        name: str,
        functions: list["ABIFunction"],
        events: list["EventT"],
        filename: Optional[str] = None,
    ):
        self._name = name
        self._functions = functions
        self._events = events
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

        events = [ABIEvent.from_abi(i) for i in abi if i.get("type") == "event"]

        return cls(basename(name), functions, events, filename=name)

    def at(self, address) -> ABIContract:
        """
        Create an ABI contract object for a deployed contract at `address`.
        """
        address = Address(address)

        ret = ABIContract(
            self._name, self._functions, self._events, address, self._filename
        )

        bytecode = ret.env.vm.state.get_code(address.canonical_address)
        if not bytecode:
            raise ValueError(
                f"Requested {ret} but there is no bytecode at that address!"
            )

        ret.env.register_contract(address, ret)

        return ret
