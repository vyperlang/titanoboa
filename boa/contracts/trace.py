from dataclasses import dataclass
from functools import cached_property
from itertools import chain
from pathlib import Path
from typing import Optional

from boa.contracts.vyper.ast_utils import reason_at
from boa.rpc import json
from boa.util.abi import abi_decode


class TraceSource:
    def format(self, input: bytes, output: bytes):
        return f"{self}{self._format_input(input)}{self._format_output(output)}"

    def _format_input(self, input: bytes):
        decoded = abi_decode(self._input_schema, input)
        args = [f"{name} = {str(d)}" for d, name in zip(decoded, self._argument_names)]
        return f"({', '.join(args)})"

    def _format_output(self, output: bytes):
        if output == b"":
            return " => None"
        decoded = abi_decode(self._output_schema, output)
        return f" => ({', '.join(str(d) for d in decoded)})"

    @cached_property
    def dev_reason(self) -> Optional["DevReason"]:
        return None

    @property
    def _input_schema(self) -> str:  # must be implemented by subclasses
        raise NotImplementedError  # pragma: no cover

    @property
    def _argument_names(self) -> list[str]:  # must be implemented by subclasses
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
        text = f"{' ' * self.depth * 4}{self.text}"
        return "\n".join(chain((text,), (str(child) for child in self.children)))

    @property
    def text(self):
        return f"[{self.gas_used}] {self.source.format(self.input, self.output)}"

    def to_dict(self) -> dict:
        return {
            "depth": self.depth,
            "gas_used": self.gas_used,
            "source": str(self.source),
            "input": "0x" + self.input.hex(),
            "output": "0x" + self.output.hex(),
            "children": [child.to_dict() for child in self.children],
            "text": self.text,
        }

    def export_html(self, destination: str | Path):
        with open(destination, "w") as f:
            f.write(self.to_html())
        print(f"Trace written to file://{Path(destination).absolute()}")

    def to_html(self):
        with open(Path(__file__).parent / "trace-template.html") as f:
            template = f.read()
        trace_json = json.dumps(self.to_dict()).replace("\\", "\\\\")
        return template.replace("$$TRACE", trace_json)


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
