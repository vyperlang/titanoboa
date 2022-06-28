from typing import Any, List
from vyper.codegen.types.types import BaseType, is_integer_type, ByteArrayType, StringType, DArrayType, SArrayType
from dataclasses import dataclass

@dataclass
class VyperObject:
    value: Any
    typ: BaseType

    @classmethod
    def empty(cls, typ):
        if is_integer_type(typ):
            return cls(0, typ)
        if isinstance(typ, ByteArrayType):
            return cls(b"", typ)
        if isinstance(typ, StringType):
            return cls("", typ)
        if isinstance(typ, DArrayType):
            return cls([], typ)
        if isinstance(typ, SArrayType):
            return cls([cls.empty(typ.subtype)] * typ.count, typ)

        raise Exception("unreachable")

@dataclass
class LogItem:
    topics: List[VyperObject]
    data: List[VyperObject]
