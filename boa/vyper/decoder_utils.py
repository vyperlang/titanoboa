from vyper.codegen.types.types import (
    ByteArrayType,
    DArrayType,
    SArrayType,
    StringType,
    is_base_type,
    is_bytes_m_type,
    is_integer_type,
)
from vyper.utils import unsigned_to_signed


def decode_vyper_object(mem, typ):
    if is_bytes_m_type(typ):
        # TODO tag return value like `vyper_object` does
        return mem[: typ._bytes_info.m].tobytes()
    if is_base_type(typ, "address"):
        return mem[12:32].tobytes()
    if is_base_type(typ, "bool"):
        return bool.from_bytes(mem[31:32], "big")
    if is_integer_type(typ):
        ret = int.from_bytes(mem[:32], "big")
        if typ._int_info.is_signed:
            return unsigned_to_signed(ret, 256)
        return ret
    if isinstance(typ, ByteArrayType):
        length = int.from_bytes(mem[:32], "big")
        return mem[32 : 32 + length].tobytes()
    if isinstance(typ, StringType):
        length = int.from_bytes(mem[:32], "big")
        return mem[32 : 32 + length].tobytes().decode("utf-8")
    if isinstance(typ, SArrayType):
        length = typ.count
        n = typ.subtype.memory_bytes_required
        return [
            decode_vyper_object(mem[i * n : i * n + n], typ.subtype)
            for i in range(length)
        ]
    if isinstance(typ, DArrayType):
        length = int.from_bytes(mem[:32], "big")
        n = typ.subtype.memory_bytes_required
        ofst = 32
        ret = []
        for _ in range(length):
            ret.append(decode_vyper_object(mem[ofst : ofst + n], typ.subtype))
            ofst += n
        return ret

    return "unimplemented decoder for `{typ}`"
