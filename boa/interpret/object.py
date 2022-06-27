from typing import Any, List
from vyper.codegen.types.types import BaseType
from dataclasses import dataclass

@dataclass
class VyperObject:
    value: Any
    typ: BaseType

@dataclass
class LogItem:
    topics: List[VyperObject]
    data: List[VyperObject]
