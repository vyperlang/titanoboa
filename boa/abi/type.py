from vyper.semantics.types import DArrayT, VyperType
from vyper.semantics.types.utils import type_from_abi


def parse_abi_type(abi: dict) -> VyperType:
    if abi["type"].endswith("[]"):
        items_type_name = abi["type"].removesuffix("[]")
        items_type = type_from_abi({"type": items_type_name})
        return DArrayT(items_type, 2**256 - 1)
    return type_from_abi(abi)
