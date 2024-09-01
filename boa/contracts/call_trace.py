from dataclasses import dataclass
from functools import cached_property
from itertools import chain
from pathlib import Path
from typing import Optional

from eth.abc import ComputationAPI

from boa.rpc import json
from boa.util.abi import Address, abi_decode


class TraceSource:
    def format(self, input_: bytes, is_error: bool, output: bytes):
        in_ = self._format_input(input_)
        out = self.format_output(is_error, output)

        if is_error:
            return f"{self}{in_} <{out}>"

        return f"{self}{in_} => {out}"

    def _format_input(self, input_: bytes):
        decoded = abi_decode(self.args_abi_type, input_)
        args = [
            f"{name} = {_to_str(d)}" for d, name in zip(decoded, self._argument_names)
        ]
        return f"({', '.join(args)})"

    def format_output(self, is_error: bool, output: bytes):
        if is_error:
            # b"\x08\xc3y\xa0" == method_id("Error(string)")
            if output.startswith(b"\x08\xc3y\xa0"):
                (ret,) = abi_decode("(string)", output[4:])
                return ret

            # TODO: handle other error types
            return "0x" + output.hex()

        if output == b"":
            return "0x"

        decoded = abi_decode(self.return_abi_type, output)
        return _to_str(decoded)

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
    computation: "ComputationAPI"
    source: Optional[TraceSource]
    depth: int
    children: list["TraceFrame"]

    @cached_property
    def address(self) -> Address:
        if self.computation.msg.is_create:
            return Address(self.computation.msg.storage_address)
        return Address(self.computation.msg.code_address)

    @cached_property
    def gas_used(self) -> int:
        return self.computation.net_gas_used

    @cached_property
    def input_data(self) -> bytes:
        return self.computation.msg.data[4:]

    @cached_property
    def selector(self) -> bytes:
        return self.computation.msg.data[:4]

    @cached_property
    def output(self) -> bytes:
        return self.computation.output

    @cached_property
    def is_error(self) -> bool:
        return self.computation.is_error

    def __str__(self):
        text = f"{' ' * self.depth * 4}{self.text}"
        return "\n".join(chain((text,), (str(child) for child in self.children)))

    @property
    def text(self):
        if self.source:
            text = self.source.format(self.input_data, self.is_error, self.output)
        else:
            text = f"Unknown contract {self.address}"
            if self.computation.msg.data != b"":
                text += ".0x" + self.selector.hex()

        ret = f"[{self.gas_used}] {text}"
        if self.is_error:
            ret = f"[E] {ret}"
        return ret

    def to_dict(self) -> dict:
        return {
            "address": str(self.address),
            "depth": self.depth,
            "gas_used": self.gas_used,
            "source": str(self.source),
            "input": "0x" + self.input_data.hex(),
            "output": "0x" + self.output.hex(),
            "children": [child.to_dict() for child in self.children],
            "is_error": self.is_error,
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
    if isinstance(d, list):
        return f"[{', '.join(_to_str(x) for x in d)}]"
    if isinstance(d, tuple):
        return f"({', '.join(_to_str(x) for x in d)})"
    if isinstance(d, str):
        return f'"{d}"'
    return str(d)
