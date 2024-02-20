"""
Fake IPython.display module for testing without Jupyter server installed.
"""
from dataclasses import dataclass
from unittest.mock import MagicMock

display = MagicMock()


@dataclass
class Javascript:
    data: str
