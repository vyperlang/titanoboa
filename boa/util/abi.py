# wrapper module around whatever encoder we are using

from eth.codecs.abi.decoder import Decoder
from eth.codecs.abi.encoder import Encoder
from eth.codecs.abi.parser import Parser

_parsers: dict[str, Parser] = {}


def _get_parser(schema):
    try:
        return _parsers[schema]
    except KeyError:
        _parsers[schema] = (ret := Parser.parse(schema))
        return ret


def abi_encode(schema, data):
    return Encoder.encode(_get_parser(schema), data)


def abi_decode(schema, data):
    return Decoder.decode(_get_parser(schema), data)
