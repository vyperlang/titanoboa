from functools import cached_property
from typing import TYPE_CHECKING, Optional

from eth_abi import decode, encode, is_encodable
from vyper.semantics.analysis.base import FunctionVisibility, StateMutability
from vyper.utils import method_id

if TYPE_CHECKING:
    from boa.abi.contract import ABIContract


class _EvmFunction:
    ...


class ABIFunction(_EvmFunction):
    def __init__(self, abi: dict, contract_name: str):
        super().__init__()
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

    def __eq__(self, other):
        return isinstance(other, ABIFunction) and self._abi == other._abi

    def __hash__(self):
        return hash(self._abi)

    def is_encodable(self, *args, **kwargs) -> bool:
        """Check whether this function accepts the given arguments after eventual encoding."""
        parsed_args = self._merge_kwargs(*args, **kwargs)
        return all(
            is_encodable(abi_type, arg)
            for abi_type, arg in zip(self.argument_types, parsed_args)
        )

    def matches(self, *args, **kwargs) -> bool:
        """Check whether this function matches the given arguments exactly."""
        parsed_args = self._merge_kwargs(*args, **kwargs)
        encoded_args = encode(self.argument_types, args)
        return map(type, parsed_args) == map(type, decode(self.signature, encoded_args))

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
        return [getattr(arg, "address", arg) for arg in merged]

    def __call__(self, *args, value=0, gas=None, sender=None, **kwargs):
        if not self.contract or not self.contract.env:
            raise Exception(f"Cannot call {self} without deploying contract.")

        args = self._merge_kwargs(*args, **kwargs)
        computation = self.contract.env.execute_code(
            to_address=self.contract.address,
            sender=sender,
            data=self.method_id + encode(self.argument_types, args),
            value=value,
            gas=gas,
            is_modifying=self.is_mutable,
            contract=self.contract,
        )

        result = self.contract.marshal_to_python(computation, self.return_type)
        return result[0] if len(result) == 1 else result


class ABIOverload(_EvmFunction):
    def __init__(self, functions: list[ABIFunction]):
        super().__init__()
        self.functions = functions

    @cached_property
    def name(self):
        return self.functions[0].name

    @property
    def contract(self):
        return self.functions[0].contract

    @contract.setter
    def contract(self, value):
        for f in self.functions:
            f.contract = value

    def __call__(self, *args, **kwargs):
        arg_count = len(kwargs) + len(args)
        candidates = [
            f
            for f in self.functions
            if f.argument_count == arg_count and f.is_encodable(*args, **kwargs)
        ]

        if not candidates:
            error = f"Could not find matching {self.name} function for given arguments."
            raise Exception(error)

        if len(candidates) == 1:
            return candidates[0](*args, **kwargs)

        matches = [f for f in candidates if f.matches(*args, **kwargs)]
        if len(matches) != 1:
            raise Exception(
                f"Ambiguous call to {self.name}. "
                f"Arguments can be encoded to multiple overloads: "
                f"{', '.join(f.signature for f in matches or candidates)}."
            )

        return matches[0]
