from dataclasses import dataclass
from functools import cached_property
from itertools import chain
from typing import Optional

from boa.contracts.vyper.ast_utils import reason_at
from boa.util.abi import abi_decode


class TraceSource:
    def format(self, input: bytes, output: bytes):
        return f"{self}{self._format_input(input)}{self._format_output(output)}"

    def _format_input(self, input: bytes):
        return f"{abi_decode(self._input_schema, input)}"

    def _format_output(self, output: bytes):
        if output == b"":
            return " => None"
        decoded = abi_decode(self._output_schema, output)
        return f" => {decoded}"

    @cached_property
    def dev_reason(self) -> Optional["DevReason"]:
        return None

    @property
    def _input_schema(self) -> str:  # must be implemented by subclasses
        raise NotImplementedError  # pragma: no cover

    @property
    def _output_schema(self) -> str:  # must be implemented by subclasses
        raise NotImplementedError  # pragma: no cover

    def __str__(self):  # must be implemented by subclasses
        raise NotImplementedError  # pragma: no cover


@dataclass
class TraceFrame:
    depth: int
    gas_used: int
    source: TraceSource
    input: bytes
    output: bytes
    children: list["TraceFrame"]

    def __str__(self):
        my_str = (
            f"{' ' * self.depth * 4}[{self.gas_used}] "
            f"{self.source.format(self.input, self.output)}"
        )
        return "\n".join(chain((my_str,), (str(child) for child in self.children)))


@dataclass
class DevReason:
    reason_type: str
    reason_str: str

    @classmethod
    def at_source_location(
        cls, source_code: str, lineno: int, end_lineno: int
    ) -> Optional["DevReason"]:
        s = reason_at(source_code, lineno, end_lineno)
        if s is None:
            return None
        reason_type, reason_str = s
        return cls(reason_type, reason_str)

    def __str__(self):
        return f"<{self.reason_type}: {self.reason_str}>"
