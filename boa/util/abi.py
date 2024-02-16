# wrapper module around whatever encoder we are using
from typing import Any

from eth.codecs.abi import nodes
from eth.codecs.abi.decoder import Decoder
from eth.codecs.abi.encoder import Encoder
from eth.codecs.abi.exceptions import ABIError
from eth.codecs.abi.nodes import ABITypeNode
from eth.codecs.abi.parser import Parser
from eth_utils import to_canonical_address, to_checksum_address

from boa.util.lrudict import lrudict

_parsers: dict[str, ABITypeNode] = {}


# inherit from bytes so we don't need conversion when interacting with pyevm
class Address(bytes):
    # converting between checksum and canonical addresses is a hotspot;
    # this class contains both and caches recently seen conversions
    # TODO: maybe this class belongs in its own module
    _cache = lrudict(1024)

    checksum_address: str

    def __new__(cls, address):
        if isinstance(address, Address):
            return address

        try:
            return cls._cache[address]
        except KeyError:
            pass

        canonical_address = to_canonical_address(address)
        self = super().__new__(cls, canonical_address)
        self.checksum_address = to_checksum_address(address)
        cls._cache[address] = self
        return self

    def __repr__(self):
        return f"_Address({self.checksum_address})"


class _ABIEncoder(Encoder):
    """
    Custom encoder that extracts the address from an `Address` object
    and passes the result to the base encoder.
    """

    @classmethod
    def visit_AddressNode(cls, node: nodes.AddressNode, value) -> bytes:
        value = getattr(value, "address", value)

        if isinstance(value, Address):
            assert len(value) == 20  # guaranteed by to_canonical_address
            # for performance, inline the implementation
            # return the bytes value, left-pad with zeros
            return value.rjust(32, b"\x00")

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
