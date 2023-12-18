from functools import cached_property
from typing import TYPE_CHECKING, Optional

from vyper.semantics.analysis.base import FunctionVisibility, StateMutability
from vyper.semantics.types import TupleT, VyperType
from vyper.semantics.types.function import PositionalArg, _generate_method_id
from vyper.semantics.types.utils import type_from_abi
from vyper.utils import method_id

from boa.abi.type import parse_abi_type
from boa.util.abi import abi_encode

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

    @cached_property
    def return_type(self) -> Optional[VyperType]:
        outputs = self._abi["outputs"].copy()
        if not outputs:
            return None
        types = [parse_abi_type(output) for output in outputs]
        return types[0] if len(types) == 1 else TupleT(tuple(types))

    @cached_property
    def name(self):
        return self._abi["name"]

    @cached_property
    def arguments(self) -> list[PositionalArg]:
        return [
            PositionalArg(item["name"], type_from_abi(item))
            for item in self._abi["inputs"]
        ]

    @cached_property
    def argument_types(self) -> list[VyperType]:
        return [arg.typ for arg in self.arguments]

    @cached_property
    def method_ids(self) -> dict[str, int]:
        """
        Dict of `{signature: four byte selector}` for this function.

        * For functions without default arguments the dict contains one item.
        * For functions with default arguments, there is one key for each
          function signature.
        """
        arg_types = [i.canonical_abi_type for i in self.argument_types]
        return _generate_method_id(self.name, arg_types)

    def __repr__(self) -> str:
        arg_types = ",".join(repr(a) for a in self.argument_types)
        return (
            f"ABI {self._contract_name}.{self.name}({arg_types}) -> {self.return_type}"
        )

    def __str__(self) -> str:
        return repr(self)

    @property
    def is_mutable(self) -> bool:
        return self._mutability > StateMutability.VIEW

    # OVERRIDE
    @property
    def func_t(self):  # TODO: Do we really need this?
        return self

    # OVERRIDE
    @cached_property
    def _source_map(self):
        return {"pc_pos_map": {}}

    def __eq__(self, other):
        return isinstance(other, ABIFunction) and self._abi == other._abi

    def __hash__(self):
        return hash(self._abi)

    def prepare_calldata(self, *args, **kwargs):
        if len(kwargs) + len(args) != len(self.arguments):
            raise Exception(
                f"Bad args to `{repr(self)}` "
                f"(expected {len(self.arguments)} arguments, got {len(args)})"
            )
        args = [getattr(arg, "address", arg) for arg in args]
        encoded_args = abi_encode(self.signature, args)
        return method_id(self.name + self.signature) + encoded_args

    @cached_property
    def signature(self) -> str:
        arg_types = [i.canonical_abi_type for i in self.argument_types]
        return f"({','.join(arg_types)})"

    def __call__(self, *args, value=0, gas=None, sender=None, **kwargs):
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

        return self.contract.marshal_to_python(computation, self.return_type)


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
        for function in self.functions:
            if arg_count == len(function.arguments):
                return function(*args, **kwargs)
        raise Exception(
            f"Could not find matching {self.name} function for given arguments {args} {kwargs}."
        )
