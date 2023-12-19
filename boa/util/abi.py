# wrapper module around whatever encoder we are using
from typing import Any

from eth.codecs.abi.decoder import Decoder
from eth.codecs.abi.encoder import Encoder
from eth.codecs.abi.nodes import ABITypeNode
from eth.codecs.abi.parser import Parser
from eth_abi import is_encodable

_parsers: dict[str, ABITypeNode] = {}


def _get_parser(schema: str):
    try:
        return _parsers[schema]
    except KeyError:
        _parsers[schema] = (ret := Parser.parse(schema))
        return ret


def abi_encode(schema: str, data: Any) -> bytes:
    return Encoder.encode(_get_parser(schema), data)


def abi_decode(schema: str, data: bytes) -> Any:
    return Decoder.decode(_get_parser(schema), data)


# todo: eth.codecs.abi does not have such a function, which one do we use?
def is_abi_encodable(abi_type: str, data: Any) -> bool:
    return is_encodable(abi_type, data)
