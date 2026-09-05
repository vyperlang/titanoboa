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

from eth_account import Account
from eth_account.datastructures import SignedMessage
from eth_account.messages import encode_typed_data, _hash_eip191_message
from hexbytes import HexBytes

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
        self._given_address = address
        self.address = address

        self.update_address()

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

    def sign_typed_data_eip712(
        self,
        domain_data: dict[str, Any] | None = None,
        message_types: dict[str, Any] | None = None,
        message_data: dict[str, Any] | None = None,
        full_message: dict[str, Any] | None = None,
    ) -> SignedMessage:
        """
        Sign EIP-712 typed data and return eth-account compatible SignedMessage.

        This method provides full EIP-712 support compatible with eth-account library,
        enabling use cases like x402 payments that require SignedMessage objects.

        Supports both parameter styles:
        1. Individual components: domain_data, message_types, message_data
        2. Complete message: full_message

        The signature is verified by recovering the signer address and comparing
        it to the wallet address. If they don't match, a ValueError is raised.

        :param domain_data: EIP-712 domain separator (name, version, chainId, verifyingContract)
        :param message_types: Message type definitions (EIP712Domain is auto-injected)
        :param message_data: The message to sign
        :param full_message: Complete EIP-712 message (alternative to individual params)
        :return: SignedMessage(messageHash, r, s, v, signature)
        :raises TypeError: If neither full_message nor individual components are provided
        :raises ValueError: If signature verification fails (recovered address != wallet address)

        Example usage with individual components:
            >>> signer = BrowserSigner()
            >>> domain = {"name": "MyApp", "version": "1", "chainId": 1}
            >>> types = {"Message": [{"name": "content", "type": "string"}]}
            >>> message = {"content": "Hello, world!"}
            >>> signed = signer.sign_typed_data_eip712(domain, types, message)
            >>> signed.signature.hex()
            '0x...'

        Example usage with full_message:
            >>> full = {
            ...     "types": {"Message": [{"name": "content", "type": "string"}]},
            ...     "primaryType": "Message",
            ...     "domain": {"name": "MyApp", "version": "1", "chainId": 1},
            ...     "message": {"content": "Hello, world!"}
            ... }
            >>> signed = signer.sign_typed_data_eip712(full_message=full)
        """
        # Build full_message if individual components provided
        if full_message is None:
            if domain_data is None or message_types is None or message_data is None:
                raise TypeError(
                    "Either full_message or all of (domain_data, message_types, "
                    "message_data) must be provided"
                )

            # Use eth-account's encode_typed_data to build and validate the message
            # This handles EIP712Domain injection automatically
            signable = encode_typed_data(
                domain_data=domain_data,
                message_types=message_types,
                message_data=message_data,
            )

            # Extract the full_message for the wallet
            # Note: encode_typed_data returns a SignableMessage with the structured data
            full_message = signable.body
        else:
            # Validate and encode the provided full_message
            signable = encode_typed_data(full_message=full_message)

        # Prepare message for wallet: serialize bytes as hex strings
        # Some fields like nonce (bytes32) need to be hex strings for wallet compatibility
        wallet_message = self._prepare_message_for_wallet(full_message)

        # Request signature from browser wallet via eth_signTypedData_v4
        sig_hex = self._rpc.fetch(
            "eth_signTypedData_v4",
            [self.address, wallet_message],
            TRANSACTION_TIMEOUT_MESSAGE,
        )

        # Ensure signature is a hex string
        if not isinstance(sig_hex, str):
            raise TypeError(f"Wallet returned non-string signature: {type(sig_hex)}")
        if not sig_hex.startswith("0x"):
            sig_hex = "0x" + sig_hex

        # Parse signature into components
        sig_bytes = bytes.fromhex(sig_hex[2:])
        if len(sig_bytes) != 65:
            raise ValueError(
                f"Invalid signature length: expected 65 bytes, got {len(sig_bytes)}"
            )

        # Extract r, s, v from signature
        r = int.from_bytes(sig_bytes[0:32], "big")
        s = int.from_bytes(sig_bytes[32:64], "big")
        v = sig_bytes[64]

        # Normalize v: some wallets return 0/1 instead of 27/28
        if v in (0, 1):
            v = v + 27
            sig_bytes = sig_bytes[:64] + bytes([v])
            sig_hex = "0x" + sig_bytes.hex()

        # Verify signature by recovering signer address
        recovered = Account.recover_message(signable, signature=HexBytes(sig_hex))
        if recovered.lower() != self.address.lower():
            raise ValueError(
                f"Signature verification failed: recovered address {recovered} "
                f"does not match wallet address {self.address}"
            )

        # Compute message hash for SignedMessage
        message_hash = _hash_eip191_message(signable)

        # Return eth-account compatible SignedMessage
        return SignedMessage(message_hash, r, s, v, HexBytes(sig_bytes))

    def _prepare_message_for_wallet(self, message: dict[str, Any]) -> dict[str, Any]:
        """
        Prepare EIP-712 message for wallet by serializing bytes as hex strings.

        Wallets expect bytes32 and similar types as hex strings in JSON.
        This recursively converts bytes/bytearray to hex strings.

        :param message: The EIP-712 message structure
        :return: Message with bytes serialized as hex strings
        """
        if isinstance(message, dict):
            return {k: self._prepare_message_for_wallet(v) for k, v in message.items()}
        elif isinstance(message, list):
            return [self._prepare_message_for_wallet(item) for item in message]
        elif isinstance(message, (bytes, bytearray)):
            return "0x" + bytes(message).hex()
        else:
            return message

    def update_address(self):
        address = getattr(self._given_address, "address", self._given_address)
        accounts = self._rpc.fetch("eth_requestAccounts", [], ADDRESS_TIMEOUT_MESSAGE)

        if address is None and len(accounts) > 0:
            address = accounts[0]

        if address not in accounts:
            raise ValueError(f"Address {address} is not available in the browser")

        self.address = Address(address)


class BrowserEnv(NetworkEnv):
    """
    A NetworkEnv object that uses the BrowserSigner and BrowserRPC classes.
    """

    _rpc = BrowserRPC()  # Browser is always global anyway, we can make it static

    def __init__(self, address=None, **kwargs):
        super().__init__(self._rpc, **kwargs)
        self.signer = BrowserSigner(address, self._rpc)
        self._update_signer()

    def _update_signer(self):
        self.signer.update_address()
        self.add_account(self.signer, force_eoa=True)

    def execute_code(self, *args, **kwargs):
        self._update_signer()
        return super().execute_code(*args, **kwargs)

    def deploy(self, *args, **kwargs):
        self._update_signer()
        return super().deploy(*args, **kwargs)

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
