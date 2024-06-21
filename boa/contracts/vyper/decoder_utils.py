from eth_utils import to_checksum_address
from vyper.semantics.types import (
    AddressT,
    BoolT,
    BytesM_T,
    BytesT,
    DArrayT,
    IntegerT,
    InterfaceT,
    SArrayT,
    StringT,
    StructT,
    TupleT,
)
from vyper.utils import unsigned_to_signed

from boa.util.abi import Address
from boa.vm.utils import ceil32, floor32


# wrap storage in something which looks like memory
class ByteAddressableStorage:
    def __init__(self, evm, address: Address, key: int):
        self.evm = evm
        self.address = address
        self.key = key

    def __getitem__(self, subscript):
        if isinstance(subscript, slice):
            ret = b""
            start = subscript.start or 0
            stop = subscript.stop
            i = self.key + start // 32
            while i < self.key + ceil32(stop) // 32:
                ret += self.evm.get_storage_slot(self.address, i)
                i += 1

            start_ofst = floor32(start)
            start -= start_ofst
            stop -= start_ofst
            return memoryview(ret[start:stop])
        else:  # pragma: no cover
            raise Exception("Must slice {self}")


class _Struct(dict):
    def __init__(self, name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.struct_name = name

    def __repr__(self):
        return f"{self.struct_name}({super().__repr__()})"


def _get_length(mem, bound):
    ret = int.from_bytes(mem[:32], "big")
    if ret > bound:
        # perf -- this is an uninitialized variable; length and data are
        # both garbage. truncate length to the bound of the container of
        # this type. the data will still be garbage, but we avoid OOM.
        return bound
    return ret


def decode_vyper_object(mem, typ):
    if isinstance(typ, BytesM_T):
        # TODO tag return value like `vyper_object` does
        return mem[: typ.m].tobytes()
    if isinstance(typ, (AddressT, InterfaceT)):
        return to_checksum_address(mem[12:32].tobytes())
    if isinstance(typ, BoolT):
        return bool.from_bytes(mem[31:32], "big")
    if isinstance(typ, IntegerT):
        ret = int.from_bytes(mem[:32], "big")
        if typ.is_signed:
            return unsigned_to_signed(ret, 256)
        return ret
    if isinstance(typ, BytesT):
        length = _get_length(mem[:32], typ.length)
        return mem[32 : 32 + length].tobytes()
    if isinstance(typ, StringT):
        length = _get_length(mem[:32], typ.length)
        return mem[32 : 32 + length].tobytes().decode("utf-8")
    if isinstance(typ, SArrayT):
        length = typ.count
        n = typ.subtype.memory_bytes_required
        return [
            decode_vyper_object(mem[i * n : i * n + n], typ.subtype)
            for i in range(length)
        ]
    if isinstance(typ, DArrayT):
        length = _get_length(mem[:32], typ.length)
        n = typ.subtype.memory_bytes_required
        ofst = 32
        ret = []
        for _ in range(length):
            ret.append(decode_vyper_object(mem[ofst : ofst + n], typ.subtype))
            ofst += n
        return ret
    if isinstance(typ, StructT):
        ret = _Struct(typ.name)
        ofst = 0
        for k, subtype in typ.tuple_items():
            n = subtype.memory_bytes_required
            ret[k] = decode_vyper_object(mem[ofst : ofst + n], subtype)
            ofst += n
        return ret
    if isinstance(typ, TupleT):
        ret = []
        ofst = 0
        for _, subtype in typ.tuple_items():
            n = subtype.memory_bytes_required
            ret.append(decode_vyper_object(mem[ofst : ofst + n], subtype))
            ofst += n
        return tuple(ret)

    return f"unimplemented decoder for `{typ}`"  # pragma: no cover
