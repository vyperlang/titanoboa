"""
This module implements the BrowserSigner class, which is used to sign transactions
in IPython/JupyterLab/Google Colab.
"""
import json
import logging
import os
from asyncio import get_event_loop, sleep
from itertools import chain
from multiprocessing.shared_memory import SharedMemory
from os import urandom
from os.path import dirname, join, realpath
from typing import Any

import nest_asyncio
from IPython.display import Javascript, display

from boa.integrations.jupyter.constants import (
    ADDRESS_TIMEOUT_MESSAGE,
    CALLBACK_TOKEN_CHARS,
    CALLBACK_TOKEN_TIMEOUT,
    NUL,
    RPC_TIMEOUT_MESSAGE,
    SHARED_MEMORY_LENGTH,
    TRANSACTION_TIMEOUT_MESSAGE,
)
from boa.network import NetworkEnv
from boa.rpc import RPC, RPCError
from boa.util.abi import Address

try:
    from google.colab.output import eval_js as colab_eval_js
except ImportError:
    colab_eval_js = None  # not in Google Colab, use SharedMemory instead


nest_asyncio.apply()


def _install_javascript_triggers():
    """Run the ethers and titanoboa_jupyterlab Javascript snippets in the browser."""
    cur_dir = dirname(realpath(__file__))
    with open(join(cur_dir, "jupyter.js")) as f:
        js = f.read()

    prefix = os.getenv("JUPYTERHUB_SERVICE_PREFIX", "..")
    js = js.replace("$$JUPYTERHUB_SERVICE_PREFIX", prefix)
    js = js.replace("$$BOA_DEBUG_MODE", json.dumps(BrowserRPC._debug_mode))

    display(Javascript(js))


class BrowserRPC(RPC):
    """
    An RPC object that sends requests to the browser via Javascript.
    """

    _debug_mode = False

    def __init__(self):
        if not colab_eval_js:
            # colab creates a new iframe for every call, we need to re-inject it every time
            # for jupyterlab we only need to do it once
            _install_javascript_triggers()

    @property
    def identifier(self) -> str:
        return type(self).__name__  # every instance does the same

    @property
    def name(self):
        return self.identifier

    def fetch(
        self, method: str, params: Any, timeout_message=RPC_TIMEOUT_MESSAGE
    ) -> Any:
        return _javascript_call("rpc", method, params, timeout_message=timeout_message)

    def fetch_multi(
        self, payloads: list[tuple[str, Any]], timeout_message=RPC_TIMEOUT_MESSAGE
    ) -> list[Any]:
        return _javascript_call("multiRpc", payloads, timeout_message=timeout_message)

    def wait_for_tx_receipt(self, tx_hash, timeout: float, poll_latency=1):
        # we do the polling in the browser to avoid too many callbacks
        # each callback generates currently 10px empty space in the frontend
        timeout_ms, pool_latency_ms = timeout * 1000, poll_latency * 1000
        return _javascript_call(
            "waitForTransactionReceipt",
            tx_hash,
            timeout_ms,
            pool_latency_ms,
            timeout_message=RPC_TIMEOUT_MESSAGE,
        )


class BrowserSigner:
    """
    A BrowserSigner is a class that can be used to sign transactions in IPython/JupyterLab.
    """

    def __init__(self, address=None, rpc=None):
        """
        Create a BrowserSigner instance.
        :param address: The account address. If not provided, it will be requested from the browser.
        """
        if rpc is None:
            rpc = BrowserRPC()  # note: the browser window is global anyway
        self._rpc = rpc
        address = getattr(address, "address", address)
        accounts = self._rpc.fetch("eth_requestAccounts", [], ADDRESS_TIMEOUT_MESSAGE)

        if address is None and len(accounts) > 0:
            address = accounts[0]

        if address not in accounts:
            raise ValueError(f"Address {address} is not available in the browser")

        self.address = Address(address)

    def send_transaction(self, tx_data: dict) -> dict:
        """
        Implements the Account class' send_transaction method.
        It executes a Javascript snippet that requests the user's signature for the transaction.
        Then, it waits for the signature to be received via the API.
        :param tx_data: The transaction data to sign.
        :return: The signed transaction data.
        """
        hash = self._rpc.fetch(
            "eth_sendTransaction", [tx_data], TRANSACTION_TIMEOUT_MESSAGE
        )
        return {"hash": hash}

    def sign_typed_data(self, full_message: dict[str, Any]) -> str:
        """
        Sign typed data value with types data structure for domain using the EIP-712 specification.
        :param full_message: The full message to sign.
        :return: The signature.
        """
        return self._rpc.fetch(
            "eth_signTypedData_v4",
            [self.address, full_message],
            TRANSACTION_TIMEOUT_MESSAGE,
        )


class BrowserEnv(NetworkEnv):
    """
    A NetworkEnv object that uses the BrowserSigner and BrowserRPC classes.
    """

    _rpc = BrowserRPC()  # Browser is always global anyway, we can make it static

    def __init__(self, address=None, **kwargs):
        super().__init__(self._rpc, **kwargs)
        self.signer = BrowserSigner(address, self._rpc)
        self.set_eoa(self.signer)

    def set_chain_id(self, chain_id: int | str):
        self._rpc.fetch(
            "wallet_switchEthereumChain",
            [{"chainId": chain_id if isinstance(chain_id, str) else hex(chain_id)}],
        )
        self._reset_fork()


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
    token = _generate_token()
    args_str = ", ".join(json.dumps(p, cls=_BytesEncoder) for p in chain([token], args))
    js_code = f"window._titanoboa.{js_func}({args_str});"
    if BrowserRPC._debug_mode:
        logging.warning(f"Calling {js_func} with {args_str}")

    if colab_eval_js:
        _install_javascript_triggers()
        result = colab_eval_js(js_code)
        return _parse_js_result(json.loads(result))

    memory = SharedMemory(name=token, create=True, size=SHARED_MEMORY_LENGTH)
    logging.info(f"Waiting for {token}")
    try:
        memory.buf[:1] = NUL
        hide_output_element = "element.style.display = 'none';"
        display(Javascript(js_code + hide_output_element))
        message_bytes = _wait_buffer_set(memory.buf, timeout_message)
        return _parse_js_result(json.loads(message_bytes.decode()))
    finally:
        memory.unlink()  # get rid of the SharedMemory object after it's been used


def _generate_token():
    """Generate a secure unique token to identify the SharedMemory object."""
    return urandom(CALLBACK_TOKEN_CHARS // 2).hex()


def _wait_buffer_set(buffer: memoryview, timeout_message: str) -> bytes:
    """
    Wait for the SharedMemory object to be filled with data.
    :param buffer: The buffer to wait for.
    :param timeout_message: The message to show if the timeout is reached.
    :return: The contents of the buffer.
    """

    async def _async_wait(deadline: float) -> bytes:
        inner_loop = get_event_loop()
        while buffer.tobytes().startswith(NUL):
            if inner_loop.time() > deadline:
                raise TimeoutError(timeout_message)
            await sleep(0.01)

        return buffer.tobytes().split(NUL)[0]

    loop = get_event_loop()
    future = _async_wait(deadline=loop.time() + CALLBACK_TOKEN_TIMEOUT.total_seconds())
    task = loop.create_task(future)
    loop.run_until_complete(task)
    return task.result()


def _parse_js_result(result: dict) -> Any:
    if "data" in result:
        return result["data"]

    def _find_key(input_dict, target_key, typ) -> Any:
        for key, value in input_dict.items():
            if isinstance(value, dict):
                found = _find_key(value, target_key, typ)
                if found is not None:
                    return found
            if key == target_key and isinstance(value, typ) and value != "error":
                return value
        return None

    # raise the error in the Jupyter cell so that the user can see it
    error = result["error"]
    error = error.get("data", error)
    raise RPCError(
        message=_find_key(error, "message", str) or _find_key(error, "error", str),
        code=_find_key(error, "code", int) or -1,
    )


class _BytesEncoder(json.JSONEncoder):
    """
    A JSONEncoder that converts bytes to hex strings to be passed to JavaScript.
    """

    def default(self, o):
        if isinstance(o, bytes):
            return "0x" + o.hex()
        return super().default(o)
