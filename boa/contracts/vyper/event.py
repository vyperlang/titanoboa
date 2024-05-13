from dataclasses import dataclass
from typing import Any


@dataclass
class Event:
    log_id: int  # internal py-evm log id, for ordering purposes
    address: str  # checksum address
    event_type: Any  # vyper.semantics.types.user.EventT
    topics: list[Any]  # list of decoded topics
    args: list[Any]  # list of decoded args

    def __repr__(self):
        t_i = 0
        a_i = 0
        b = []
        # align the evm topic + args lists with the way they appear in the source
        # ex. Transfer(indexed address, address, indexed address)
        for is_topic, k in zip(
            self.event_type.indexed, self.event_type.arguments.keys()
        ):
            if is_topic:
                b.append((k, self.topics[t_i]))
                t_i += 1
            else:
                b.append((k, self.args[a_i]))
                a_i += 1

        args = ", ".join(f"{k}={v}" for k, v in b)
        return f"{self.event_type.name}({args})"


@dataclass
class RawEvent:
    event_data: Any
