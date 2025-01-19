from collections import defaultdict, namedtuple
from functools import cached_property
from typing import Any, Optional, Union
from warnings import warn

from eth.abc import ComputationAPI
from vyper.semantics.analysis.base import FunctionVisibility, StateMutability
from vyper.utils import keccak256, method_id

from boa.contracts.base_evm_contract import (
    BoaError,
    StackTrace,
    _BaseEVMContract,
    _handle_child_trace,
)
from boa.contracts.call_trace import TraceSource
from boa.contracts.event_decoder import decode_log
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
        return _format_abi_type(self.argument_types)

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

        val = self.contract.marshal_to_python(computation, self.return_type)

        # this property should be guaranteed by abi_decode inside marshal_to_python,
        # assert it again just for clarity
        # note that val should be a tuple.
        assert len(self._abi["outputs"]) == len(val)

        match val:
            case ():
                return None
            case (single,):
                return _parse_complex(self._abi["outputs"][0], single, name=self.name)
            case multiple:
                item_abis = self._abi["outputs"]
                cls = type(multiple)  # should be tuple
                return cls(
                    _parse_complex(abi, item, name=self.name)
                    for (abi, item) in zip(item_abis, multiple)
                )


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
        events: list[dict],
        address: Address,
        filename: Optional[str] = None,
        env=None,
        nowarn=False,
    ):
        super().__init__(name, env, filename=filename, address=address)
        self._abi = abi
        self._functions = functions
        self._events = events

        self._bytecode = self.env.get_code(address)
        if not self._bytecode and not nowarn:
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

    @cached_property
    def event_for(self):
        # [{"name": "Bar", "inputs":
        #   [{"name": "x", "type": "uint256", "indexed": false},
        #   {"name": "y", "type": "tuple", "components":
        #     [{"name": "x", "type": "uint256"}], "indexed": false}],
        # "anonymous": false, "type": "event"},
        # }]
        ret = {}
        for event_abi in self._events:
            event_signature = ",".join(
                _abi_from_json(item) for item in event_abi["inputs"]
            )
            event_name = event_abi["name"]
            event_signature = f"{event_name}({event_signature})"
            event_id = int(keccak256(event_signature.encode()).hex(), 16)
            ret[event_id] = event_abi
        return ret

    def decode_log(self, log_entry):
        return decode_log(self._address, self.event_for, log_entry)

    def marshal_to_python(self, computation, abi_type: list[str]) -> tuple[Any, ...]:
        """
        Convert the output of a contract call to a Python object.
        :param computation: the computation object returned by `execute_code`
        :param abi_type: the ABI type of the return value.
        """
        self._computation = computation
        if computation.is_error:
            return self.handle_error(computation)

        schema = _format_abi_type(abi_type)
        try:
            return abi_decode(schema, computation.output)
        except ABIError as e:
            # TODO: the likely error here is that no code exists at the address,
            # it might be better to just let the raw ABIError float up
            raise BoaError.create(computation, self) from e

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

    def trace_source(self, computation) -> Optional["ABITraceSource"]:
        """
        Find the source of the error in the contract.
        :param computation: the computation object returned by `execute_code`
        """
        method_id_ = computation.msg.data[:4]
        if method_id_ not in self.method_id_map:
            return None
        return ABITraceSource(self, self.method_id_map[method_id_])

    @property
    def deployer(self) -> "ABIContractFactory":
        """
        Returns a factory that can be used to retrieve another deployed contract.
        """
        return ABIContractFactory(self.contract_name, self._abi, filename=self.filename)

    def __repr__(self):
        file_str = f" (file {self.filename})" if self.filename else ""
        warn_str = "" if self._bytecode else " (WARNING: no bytecode at this address!)"
        return f"<{self.contract_name} interface at {self.address}{warn_str}>{file_str}"


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

    @property
    def functions(self):
        return [
            ABIFunction(item, self._name)
            for item in self.abi
            if item.get("type") == "function"
        ]

    @property
    def events(self):
        return [item for item in self.abi if item.get("type") == "event"]

    @classmethod
    def from_abi_dict(cls, abi, name="<anonymous contract>", filename=None):
        return cls(name, abi, filename)

    def at(self, address: Address | str, nowarn=False) -> ABIContract:
        """
        Create an ABI contract object for a deployed contract at `address`.
        """
        address = Address(address)
        contract = ABIContract(
            self._name,
            self._abi,
            self.functions,
            self.events,
            address,
            self.filename,
            nowarn=nowarn,
        )

        contract.env.register_contract(address, contract)
        return contract


class ABITraceSource(TraceSource):
    def __init__(self, contract: ABIContract, function: ABIFunction):
        self.contract = contract
        self.function = function

    def __str__(self):
        return f"{self.contract.contract_name}.{self.function.pretty_name}"

    def __repr__(self):
        return repr(self.function)

    @cached_property
    def args_abi_type(self):
        return _format_abi_type(self.function.argument_types)

    @cached_property
    def _argument_names(self) -> list[str]:
        return [arg["name"] for arg in self.function._abi["inputs"]]

    @cached_property
    def return_abi_type(self):
        return _format_abi_type(self.function.return_type)


def _abi_from_json(abi: dict) -> str:
    """
    Parses an ABI type into its schema string.
    :param abi: The ABI type to parse.
    :return: The schema string for the given abi type.
    """
    # {"stateMutability": "view", "type": "function", "name": "foo",
    # "inputs": [],
    # "outputs": [{"name": "", "type": "tuple",
    #    "components": [{"name": "x", "type": "uint256"}]}]
    # }

    if "components" in abi:
        components = ",".join([_abi_from_json(item) for item in abi["components"]])
        if abi["type"].startswith("tuple"):
            return f"({components}){abi['type'][5:]}"
        raise ValueError("Components found in non-tuple type " + abi["type"])

    return abi["type"]


def _parse_complex(abi: dict, value: Any, name=None) -> str:
    """
    Parses an ABI type into its schema string.
    :param abi: The ABI type to parse.
    :return: The schema string for the given abi type.
    """
    # simple case
    if "components" not in abi:
        return value

    # https://docs.soliditylang.org/en/latest/abi-spec.html#handling-tuple-types
    type_ = abi["type"]
    assert type_.startswith("tuple")
    # number of nested arrays (we don't care if dynamic or static)
    depth = type_.count("[")

    # complex case
    # construct a namedtuple type on the fly
    components = abi["components"]
    typname = name or abi["name"] or "user_struct"
    component_names = [item["name"] for item in components]

    typ = namedtuple(typname, component_names, rename=True)  # type: ignore[misc]

    def _leaf(tuple_vals):
        components_parsed = [
            _parse_complex(item_abi, item)
            for (item_abi, item) in zip(components, tuple_vals)
        ]

        return typ(*components_parsed)

    def _go(val, depth):
        if depth == 0:
            return _leaf(val)
        return [_go(val, depth - 1) for val in val]

    return _go(value, depth)


def _format_abi_type(types: list) -> str:
    """
    Converts a list of ABI types into a comma-separated string.
    """
    ret = ",".join(
        item if isinstance(item, str) else _format_abi_type(item) for item in types
    )
    return f"({ret})"
