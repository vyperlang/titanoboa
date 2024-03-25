import time
from typing import Any
from urllib.parse import urlparse

import requests

try:
    import ujson as json
except ImportError:  # pragma: no cover
    import json  # type: ignore

TIMEOUT = 60  # default timeout for http requests in seconds


# some utility functions


def trim_dict(kv):
    return {k: v for (k, v) in kv.items() if bool(v)}


def fixup_dict(kv):
    return {k: to_hex(v) for (k, v) in trim_dict(kv).items()}


def to_hex(s: int | bytes | str) -> str:
    if isinstance(s, int):
        return hex(s)
    if isinstance(s, bytes):
        return "0x" + s.hex()
    if isinstance(s, str):
        assert s.startswith("0x")
        return s
    raise TypeError(
        f"to_hex expects bytes, int or (hex) string, but got {type(s)}: {s}"
    )


def to_int(hex_str: str) -> int:
    if hex_str == "0x":
        return 0
    return int(hex_str, 16)


def to_bytes(hex_str: str) -> bytes:
    return bytes.fromhex(hex_str.removeprefix("0x"))


class RPCError(Exception):
    def __init__(self, message: str, code: int):
        super().__init__(f"{code}: {message}")
        self.code = code

    @classmethod
    def from_json(cls, data):
        return cls(message=data["message"], code=data["code"])


class RPC:
    """
    Base class for RPC implementations.
    This abstract class does not use ABC for performance reasons.
    """

    @property
    def identifier(self) -> str:  # pragma: no cover
        raise NotImplementedError

    @property
    def name(self) -> str:  # pragma: no cover
        raise NotImplementedError

    def fetch_uncached(self, method, params):
        return self.fetch(method, params)

    def fetch(self, method: str, params: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    def fetch_multi(
        self, payloads: list[tuple[str, Any]]
    ) -> list[Any]:  # pragma: no cover
        raise NotImplementedError

    def wait_for_tx_receipt(self, tx_hash, timeout: float, poll_latency=0.25):
        start = time.time()

        while True:
            receipt = self.fetch_uncached("eth_getTransactionReceipt", [tx_hash])
            if receipt is not None:
                return receipt
            if time.time() + poll_latency > start + timeout:
                raise ValueError(f"Timed out waiting for ({tx_hash})")
            time.sleep(poll_latency)


class EthereumRPC(RPC):
    def __init__(self, url: str):
        self._rpc_url = url
        self._session = requests.Session()

        # declare app name to frame.sh
        self._session.headers["Origin"] = "Titanoboa"

    @property
    def identifier(self):
        return self._rpc_url

    @property
    def name(self):
        # return a version of the URL which has everything past the "base"
        # url stripped out (content which you might not want to end up
        # in logs)
        parse_result = urlparse(self._rpc_url)
        return f"{parse_result.scheme}://{parse_result.netloc} (URL partially masked for privacy)"

    def fetch(self, method, params):
        # the obvious thing to do here is dispatch into fetch_multi.
        # but some providers (alchemy) can't handle batched requests
        # for certain endpoints (debug_traceTransaction).
        req = {"jsonrpc": "2.0", "method": method, "params": params, "id": 0}
        # print(req)
        res = self._session.post(self._rpc_url, json=req, timeout=TIMEOUT)
        res.raise_for_status()
        res = json.loads(res.text)
        # print(res)
        if "error" in res:
            raise RPCError.from_json(res["error"])
        return res["result"]

    def fetch_multi(self, payloads):
        request = [
            {"jsonrpc": "2.0", "method": method, "params": params, "id": i}
            for i, (method, params) in enumerate(payloads)
        ]
        response = self._session.post(self._rpc_url, json=request, timeout=TIMEOUT)
        response.raise_for_status()

        results = {}  # keep results in a dict to preserve order
        for item in json.loads(response.text):
            if "error" in item:
                raise RPCError.from_json(item["error"])
            results[item["id"]] = item["result"]

        return [results[i] for i in range(len(payloads))]
