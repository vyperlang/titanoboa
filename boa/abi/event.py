from vyper.semantics.types import EventT

from boa.abi.type import parse_abi_type


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
