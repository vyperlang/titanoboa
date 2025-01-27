# wrapper module around whatever encoder we are using
from collections import deque
from typing import Annotated, Any

from eth.codecs.abi import nodes
from eth.codecs.abi.decoder import DecodeError, Decoder
from eth.codecs.abi.encoder import Encoder
from eth.codecs.abi.exceptions import ABIError
from eth.codecs.abi.nodes import ABITypeNode
from eth.codecs.abi.parser import Parser
from eth_typing import Address as PYEVM_Address
from eth_utils import to_canonical_address, to_checksum_address

from boa.util.lrudict import lrudict

_parsers: dict[str, ABITypeNode] = {}


# inherit from `str` so that users can compare with regular hex string
# addresses
class Address(str):
    # converting between checksum and canonical addresses is a hotspot;
    # this class contains both and caches recently seen conversions
    __slots__ = ("canonical_address",)
    _cache = lrudict(1024)

    canonical_address: Annotated[PYEVM_Address, "canonical address"]

    def __new__(cls, address):
        if isinstance(address, Address):
            return address

        try:
            return cls._cache[address]
        except KeyError:
            pass

        checksum_address = to_checksum_address(address)
        self = super().__new__(cls, checksum_address)
        self.canonical_address = to_canonical_address(address)
        cls._cache[address] = self
        return self

    def __repr__(self):
        checksum_addr = super().__repr__()
        return f"Address({checksum_addr})"


class _ABIEncoder(Encoder):
    """
    Custom encoder that extracts the address from an `Address` object
    and passes the result to the base encoder.
    """

    @classmethod
    def visit_AddressNode(cls, node: nodes.AddressNode, value) -> bytes:
        value = getattr(value, "address", value)
        return super().visit_AddressNode(node, value)


class _ABIDecoder(Decoder):
    """
    Custom decoder that wraps address results into an `Address` object.
    """

    @classmethod
    def visit_AddressNode(
        cls, node: nodes.AddressNode, value: bytes, checksum: bool = True, **kwargs: Any
    ) -> "Address":
        ret = super().visit_AddressNode(node, value)
        return Address(ret)

    @classmethod
    def visit_TupleNode(cls, node: nodes.TupleNode, value: bytes, **kwargs) -> tuple:
        """
        Monkey patch to workaround upstream bug in visit_TupleNode.
        See https://github.com/skellet0r/eth-stdlib/pull/22
        """
        size = sum((elem.width for elem in node.ctypes))
        # value size should be >= the sum of the length of its components
        if len(value) < size:
            raise DecodeError(str(node), value, "Value length is less than expected")

        pos, raw_head = 0, []
        for ctyp in node.ctypes:
            raw_head.append(value[pos : pos + ctyp.width])
            pos += ctyp.width

        if not node.is_dynamic:
            # no tail section
            return tuple(
                (
                    cls.decode(ctyp, val, **kwargs)
                    for ctyp, val in zip(node.ctypes, raw_head)
                )
            )

        ctyps_and_vals = list(zip(node.ctypes, raw_head))

        # ptrs are in the head section, convert them to ints in a single list
        ptrs = [
            int.from_bytes(val, "big")
            for ctyp, val in ctyps_and_vals
            if ctyp.is_dynamic
        ]
        # for each pointer copy the data from the dynamic section similar to array decoding
        data = deque([value[a:b] for a, b in zip(ptrs, ptrs[1:])] + [value[ptrs[-1] :]])
        # replace each ptr with its data - generator
        head = [
            data.popleft() if ctyp.is_dynamic else val for ctyp, val in ctyps_and_vals
        ]

        # return the decoded elements
        return tuple(
            [cls.decode(typ, val, **kwargs) for typ, val in zip(node.ctypes, head)]
        )


def _get_parser(schema: str):
    try:
        return _parsers[schema]
    except KeyError:
        _parsers[schema] = (ret := Parser.parse(schema))
        return ret


def abi_encode(schema: str, data: Any) -> bytes:
    return _ABIEncoder.encode(_get_parser(schema), data)


def abi_decode(schema: str, data: bytes) -> Any:
    return _ABIDecoder.decode(_get_parser(schema), data)


def is_abi_encodable(abi_type: str, data: Any) -> bool:
    try:
        abi_encode(abi_type, data)
        return True
    except ABIError:
        return False
