from vyper.semantics.types import DArrayT, EventT, VyperType
from vyper.semantics.types.utils import type_from_abi


class ABIEvent(EventT):
    @classmethod
    def from_abi(cls, abi: dict) -> "ABIEvent":
        """
        Generate an `Event` object from an ABI interface.

        Arguments
        ---------
        abi : dict
            An object from a JSON ABI interface, representing an event.

        Returns
        -------
        Event object.
        """
        return cls(
            name=abi["name"],
            arguments={items["name"]: parse_abi_type(items) for items in abi["inputs"]},
            indexed=[i["indexed"] for i in abi["inputs"]],
        )


def parse_abi_type(abi: dict) -> VyperType:
    if abi["type"].endswith("[]"):
        items_type_name = abi["type"].removesuffix("[]")
        items_type = type_from_abi({"type": items_type_name})
        return DArrayT(items_type, 2**256 - 1)
    return type_from_abi(abi)
