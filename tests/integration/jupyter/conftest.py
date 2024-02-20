from multiprocessing.shared_memory import SharedMemory

import pytest

from boa.integrations.jupyter.browser import _generate_token


@pytest.fixture()
def shared_memory_length():
    from boa.integrations.jupyter.constants import SHARED_MEMORY_LENGTH

    return SHARED_MEMORY_LENGTH


@pytest.fixture()
def token():
    return _generate_token()


@pytest.fixture()
def shared_memory(token, shared_memory_length):
    memory = SharedMemory(name=token, create=True, size=shared_memory_length)
    yield memory
    memory.unlink()
