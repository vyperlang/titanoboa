import functools
from dataclasses import dataclass
from typing import Any, List, Dict



@dataclass
class Event:
    log_id: int  # internal py-evm log id, for ordering purposes
    address: str  # checksum address
    event_type: Any  # vyper.semantics.types.user.Event
    event_name: str # human readable output
    topics: List[Any]  # list of decoded topics
    args: List[Any]  # list of decoded args

    def __repr__(self):
        return self.event_name
    
    @functools.cached_property
    def args_map(self):
        event_values = self.event_name.split(', ')
        return dict([(topic.split('=')) for topic in event_values])

class RawEvent:
    event_data: Any