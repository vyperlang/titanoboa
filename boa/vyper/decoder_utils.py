from eth_utils import to_checksum_address
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


def ceil32(n):
    return floor32(n + 31)


def floor32(n):
    return n & ~31


# wrap storage in something which looks like memory
class ByteAddressableStorage:
    def __init__(self, db, address, key):
        self.db = db
        self.address = address
        self.key = key

    def __getitem__(self, subscript):
        if isinstance(subscript, slice):
            ret = b""
            start = subscript.start or 0
            stop = subscript.stop
            i = self.key + start // 32
            while i < self.key + ceil32(stop) // 32:
                ret += self.db.get_storage(self.address, i).to_bytes(32, "big")
                i += 1

            start -= floor32(start)
            stop -= floor32(start)
            return memoryview(ret[start:stop])
        else:
            raise Exception("Must slice {self}")


def decode_vyper_object(mem, typ):
    if is_bytes_m_type(typ):
        # TODO tag return value like `vyper_object` does
        return mem[: typ._bytes_info.m].tobytes()
    if is_base_type(typ, "address"):
        return to_checksum_address(mem[12:32].tobytes())
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
