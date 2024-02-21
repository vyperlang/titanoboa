from multiprocessing.shared_memory import SharedMemory

import pytest

from boa.integrations.jupyter.browser import _generate_token
from boa.integrations.jupyter.constants import SHARED_MEMORY_LENGTH


@pytest.fixture()
def token():
    return _generate_token()


@pytest.fixture()
def shared_memory(token):
    memory = SharedMemory(name=token, create=True, size=SHARED_MEMORY_LENGTH)
    try:
        yield memory
    finally:
        memory.unlink()
