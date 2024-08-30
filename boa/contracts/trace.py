from dataclasses import dataclass
from itertools import chain
from pathlib import Path

from boa.rpc import json
from boa.util.abi import Address, abi_decode


class TraceSource:
    def format(self, input: bytes, output: bytes):
        return f"{self}{self._format_input(input)}{self.format_output(output)}"

    def _format_input(self, input: bytes):
        decoded = abi_decode(self.args_abi_type, input)
        args = [
            f"{name} = {_to_str(d)}" for d, name in zip(decoded, self._argument_names)
        ]
        return f"({', '.join(args)})"

    def format_output(self, output: bytes):
        if output == b"":
            return " => None"
        decoded = abi_decode(self.return_abi_type, output)
        return f" => ({', '.join(_to_str(d) for d in decoded)})"

    @property
    def args_abi_type(self) -> str:  # must be implemented by subclasses
        raise NotImplementedError  # pragma: no cover

    @property
    def _argument_names(self) -> list[str]:  # must be implemented by subclasses
        raise NotImplementedError  # pragma: no cover

    @property
    def return_abi_type(self) -> str:  # must be implemented by subclasses
        raise NotImplementedError  # pragma: no cover

    def __str__(self):  # must be implemented by subclasses
        raise NotImplementedError  # pragma: no cover


@dataclass
class TraceFrame:
    address: Address
    depth: int
    gas_used: int
    source: TraceSource | None
    input: bytes
    output: bytes
    children: list["TraceFrame"]

    def __str__(self):
        text = f"{' ' * self.depth * 4}{self.text}"
        return "\n".join(chain((text,), (str(child) for child in self.children)))

    @property
    def text(self):
        if self.source:
            text = self.source.format(self.input, self.output)
        else:
            text = f"Unknown contract {self.address}"
            if self.input != b"":
                text += ".0x" + self.input[:4].hex()

        return f"[{self.gas_used}] {text}"

    def to_dict(self) -> dict:
        return {
            "address": str(self.address),
            "depth": self.depth,
            "gas_used": self.gas_used,
            "source": str(self.source),
            "input": "0x" + self.input.hex(),
            "output": "0x" + self.output.hex(),
            "children": [child.to_dict() for child in self.children],
            "text": self.text,
        }

    def export_html(self, destination: str | Path):
        html = self.to_html()
        with open(destination, "w") as f:
            f.write(html)
        print(f"Trace written to file://{Path(destination).absolute()}")

    def to_html(self):
        with open(Path(__file__).parent / "trace-template.html") as f:
            template = f.read()
        trace_json = json.dumps(self.to_dict()).replace("\\", "\\\\")
        return template.replace("$$TRACE", trace_json)


def _to_str(d):
    if isinstance(d, bytes):
        return "0x" + d.hex()
    if isinstance(d, (list, tuple)):
        return f"[{', '.join(_to_str(x) for x in d)}]"
    if isinstance(d, str):
        return f'"{d}"'
    return str(d)
