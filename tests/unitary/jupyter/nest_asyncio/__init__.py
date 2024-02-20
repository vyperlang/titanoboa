"""
Fake nest_asyncio module for testing without Jupyter server installed.
"""
from unittest.mock import MagicMock

apply = MagicMock()
