# wrapper module around whatever encoder we are using
from typing import TYPE_CHECKING, Any

from eth.codecs.abi import nodes
from eth.codecs.abi.decoder import Decoder
from eth.codecs.abi.encoder import Encoder
from eth.codecs.abi.exceptions import ABIError
from eth.codecs.abi.nodes import ABITypeNode
from eth.codecs.abi.parser import Parser

if TYPE_CHECKING:
    from boa.environment import Address

_parsers: dict[str, ABITypeNode] = {}


class AbiEncoder(Encoder):
    @classmethod
    def visit_AddressNode(cls, node: nodes.AddressNode, value) -> bytes:
        value = getattr(value, "address", value)
        return super().visit_AddressNode(node, value)


class AbiDecoder(Decoder):
    @classmethod
    def visit_AddressNode(
        cls, node: nodes.AddressNode, value: bytes, checksum: bool = True, **kwargs: Any
    ) -> "Address":
        from boa.environment import (  # Maybe Address should be in a different file?
            Address,
        )

        ret = super().visit_AddressNode(node, value)
        return Address(ret)


def _get_parser(schema: str):
    try:
        return _parsers[schema]
    except KeyError:
        _parsers[schema] = (ret := Parser.parse(schema))
        return ret


def abi_encode(schema: str, data: Any) -> bytes:
    return AbiEncoder.encode(_get_parser(schema), data)


def abi_decode(schema: str, data: bytes) -> Any:
    return AbiDecoder.decode(_get_parser(schema), data)


def is_abi_encodable(abi_type: str, data: Any) -> bool:
    try:
        abi_encode(abi_type, data)
        return True
    except ABIError:
        return False
