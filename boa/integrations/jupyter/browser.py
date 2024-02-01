"""
This module implements the BrowserSigner class, which is used to sign transactions
in IPython/JupyterLab/Google Colab.
"""
import json
import logging
from asyncio import get_running_loop, sleep
from itertools import chain
from multiprocessing.shared_memory import SharedMemory
from os import urandom
from typing import Any, Awaitable

import nest_asyncio
from IPython.display import Javascript, display

from ...rpc import RPC, RPCError
from .constants import (
    ADDRESS_TIMEOUT_MESSAGE,
    CALLBACK_TOKEN_BYTES,
    CALLBACK_TOKEN_TIMEOUT,
    NUL,
    PLUGIN_NAME,
    RPC_TIMEOUT_MESSAGE,
    SHARED_MEMORY_LENGTH,
    TRANSACTION_TIMEOUT_MESSAGE,
)
from .utils import convert_frontend_dict, install_jupyter_javascript_triggers

nest_asyncio.apply()


class BrowserSigner:
    """
    A BrowserSigner is a class that can be used to sign transactions in IPython/JupyterLab.
    """

    def __init__(self, address=None):
        """
        Create a BrowserSigner instance.
        :param address: The account address. If not provided, it will be requested from the browser.
        """
        if address:
            self.address = address
        else:
            self.address = _javascript_call(
                "loadSigner", timeout_message=ADDRESS_TIMEOUT_MESSAGE
            )

    def send_transaction(self, tx_data: dict) -> dict:
        """
        Implements the Account class' send_transaction method.
        It executes a Javascript snippet that requests the user's signature for the transaction.
        Then, it waits for the signature to be received via the API.
        :param tx_data: The transaction data to sign.
        :return: The signed transaction data.
        """
        sign_data = _javascript_call(
            "signTransaction", tx_data, timeout_message=TRANSACTION_TIMEOUT_MESSAGE
        )
        return convert_frontend_dict(sign_data)


class BrowserRpc(RPC):
    """
    An RPC object that sends requests to the browser via Javascript.
    """

    @property
    def name(self):
        return type(self).__name__

    def fetch(self, method: str, params: Any) -> Any:
        return _javascript_call(
            "rpc", method, params, timeout_message=RPC_TIMEOUT_MESSAGE
        )

    def fetch_multi(self, payloads: list[tuple[str, Any]]) -> list[Any]:
        return _javascript_call(
            "multiRpc", payloads, timeout_message=RPC_TIMEOUT_MESSAGE
        )


def _javascript_call(js_func: str, *args, timeout_message: str) -> Any:
    """
    This function attempts to call a Javascript function in the browser and then
    wait for the result to be sent back to the API.
    - Inside Google Colab, it uses the eval_js function to call the Javascript function.
    - Outside, it uses a SharedMemory object and polls until the frontend called our API.
    A custom timeout message is useful for user feedback.
    :param snippet: A function that given a token and some kwargs, returns a Javascript snippet.
    :param kwargs: The arguments to pass to the Javascript snippet.
    :return: The result of the Javascript snippet sent to the API.
    """
    install_jupyter_javascript_triggers()

    token = _generate_token()
    args_str = ", ".join(json.dumps(p) for p in chain([token], args))
    js_code = f"window._titanoboa.{js_func}({args_str}).catch(console.trace)"
    # logging.warning(f"Calling {js_func} with {args_str}")

    try:
        from google.colab.output import eval_js

        result = eval_js(js_code)
        return _parse_js_result(json.loads(result))
    except ImportError:
        pass  # not in Google Colab, use SharedMemory instead

    memory = SharedMemory(name=token, create=True, size=SHARED_MEMORY_LENGTH)
    logging.info(f"Waiting for {token}")
    try:
        memory.buf[:1] = NUL
        display(Javascript(js_code))
        return _wait_buffer_set(memory.buf, timeout_message)
    finally:
        memory.unlink()  # get rid of the SharedMemory object after it's been used


def _generate_token():
    """Generate a secure unique token to identify the SharedMemory object."""
    return f"{PLUGIN_NAME}_{urandom(CALLBACK_TOKEN_BYTES).hex()}"


def _wait_buffer_set(buffer: memoryview, timeout_message: str) -> Any:
    """
    Wait for the SharedMemory object to be filled with data.
    :param buffer: The buffer to wait for.
    :param timeout_message: The message to show if the timeout is reached.
    :return: The contents of the buffer.
    """

    async def _wait_buffer_set(deadline: float) -> Awaitable[dict[str, Any]]:
        """
        Wait until the SharedMemory object is not empty.
        :param deadline: The deadline to wait for.
        :return: The result of the Javascript snippet sent to the API.
        """
        inner_loop = get_running_loop()
        while buffer.tobytes().startswith(NUL):
            if inner_loop.time() > deadline:
                raise TimeoutError(timeout_message)
            await sleep(0.01)

        message_bytes = buffer.tobytes().split(NUL)[0]
        return json.loads(message_bytes.decode())

    loop = get_running_loop()
    future = _wait_buffer_set(
        deadline=loop.time() + CALLBACK_TOKEN_TIMEOUT.total_seconds()
    )
    task = loop.create_task(future)
    loop.run_until_complete(task)
    return _parse_js_result(task.result())


def _parse_js_result(result: dict) -> Any:
    if "data" in result:
        return result["data"]

    # raise the error in the Jupyter cell so that the user can see it
    error = result["error"]
    error = error.get("info", error).get("error", error)
    raise RPCError(
        message=error.get("message", error), code=error.get("code", "CALLBACK_ERROR")
    )
