"""
This module implements the BrowserSigner class, which is used to sign transactions
in IPython/JupyterLab/Google Colab.
"""
import json
from asyncio import get_running_loop, sleep
from importlib import util
from multiprocessing.shared_memory import SharedMemory
from os import urandom
from typing import Any

import nest_asyncio
from IPython.display import Javascript, display

from .constants import (
    ADDRESS_JSON_LENGTH,
    CALLBACK_TOKEN_BYTES,
    CALLBACK_TOKEN_TIMEOUT,
    NUL,
    PLUGIN_NAME,
    TRANSACTION_JSON_LENGTH,
)
from .handlers import start_server
from .utils import convert_frontend_dict, install_jupyter_javascript_triggers

nest_asyncio.apply()
if util.find_spec("google.colab"):
    start_server()


class BrowserSigner:
    """
    A BrowserSigner is a class that can be used to sign transactions in IPython/JupyterLab.
    """

    def __init__(self, address=None):
        """
        Create a BrowserSigner instance.
        :param address: The account address. If not provided, it will be requested from the browser.
        """
        install_jupyter_javascript_triggers()
        if address:
            self.address = address
        else:
            # wait for the address to be set via the API, otherwise boa crashes
            memory_size = (
                ADDRESS_JSON_LENGTH + 3
            )  # address + quotes from json encode + \0
            self.address = _create_and_wait(_load_signer_snippet, size=memory_size)

    def send_transaction(self, tx_data: dict) -> dict:
        """
        Implements the Account class' send_transaction method.
        It executes a Javascript snippet that requests the user's signature for the transaction.
        Then, it waits for the signature to be received via the API.
        :param tx_data: The transaction data to sign.
        :return: The signed transaction data.
        """
        sign_data = _create_and_wait(
            _sign_transaction_snippet, size=TRANSACTION_JSON_LENGTH, tx_data=tx_data
        )
        return convert_frontend_dict(sign_data)


def _create_and_wait(snippet: callable, size: int, **kwargs) -> dict:
    """
    Create a SharedMemory object and wait for it to be filled with data.
    :param snippet: A function that given a token and some kwargs, returns a Javascript snippet.
    :param size: The size of the SharedMemory object to create.
    :param kwargs: The arguments to pass to the Javascript snippet.
    :return: The result of the Javascript snippet sent to the API.
    """
    token = _generate_token()
    memory = SharedMemory(name=token, create=True, size=size)
    try:
        memory.buf[:1] = NUL
        javascript = snippet(token, **kwargs)
        display(javascript)
        return _wait_buffer_set(memory.buf)
    finally:
        memory.unlink()  # get rid of the SharedMemory object after it's been used


def _generate_token():
    """Generate a secure unique token to identify the SharedMemory object."""
    return f"{PLUGIN_NAME}_{urandom(CALLBACK_TOKEN_BYTES).hex()}"


def _wait_buffer_set(buffer: memoryview):
    """
    Wait for the SharedMemory object to be filled with data.
    :param buffer: The buffer to wait for.
    :return: The contents of the buffer.
    """

    async def _wait_value(deadline: float) -> Any:
        """
        Wait until the SharedMemory object is not empty.
        :param deadline: The deadline to wait for.
        :return: The result of the Javascript snippet sent to the API.
        """
        inner_loop = get_running_loop()
        while buffer.tobytes().startswith(NUL):
            if inner_loop.time() > deadline:
                raise TimeoutError(
                    "Timeout while waiting for user to confirm transaction in the browser."
                )
            await sleep(0.01)
        return json.loads(buffer.tobytes().decode().split("\0")[0])

    loop = get_running_loop()
    future = _wait_value(deadline=loop.time() + CALLBACK_TOKEN_TIMEOUT.total_seconds())
    task = loop.create_task(future)
    loop.run_until_complete(task)
    result = task.result()
    if "data" in result:
        return result["data"]
    raise Exception(result["error"])


def _load_signer_snippet(token: str) -> Javascript:
    """Run loadSigner in the browser."""
    return Javascript(f"window._titanoboa.loadSigner('{token}');")


def _sign_transaction_snippet(token: str, tx_data):
    """Run signTransaction in the browser."""
    return Javascript(
        f"window._titanoboa.signTransaction('{token}', {json.dumps(tx_data)});"
    )
