from abc import ABC, abstractmethod
from urllib.parse import urlparse

import requests

try:
    import ujson as json
except ImportError:
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
    def __init__(self, message, code):
        super().__init__(f"{code}: {message}")
        self.code: str = code

    @classmethod
    def from_json(cls, data):
        return cls(message=data["message"], code=data["code"])


class RPC(ABC):
    """Base interface for RPC implementations"""

    @property
    @abstractmethod
    def name(self):
        ...

    @abstractmethod
    def fetch(self, method, params):
        ...

    @abstractmethod
    def fetch_multi(self, payloads):
        ...


class EthereumRPC(RPC):
    def __init__(self, url: str):
        self._rpc_url = url
        self._session = requests.Session()

        # declare app name to frame.sh
        self._session.headers["Origin"] = "Titanoboa"

    @property
    def name(self):
        # return a version of the URL which has everything past the "base"
        # url stripped out (content which you might not want to end up
        # in logs)
        parse_result = urlparse(self._rpc_url)
        return f"{parse_result.scheme}://{parse_result.netloc}"

    def _raw_fetch_single(self, method, params):
        req = {"jsonrpc": "2.0", "method": method, "params": params, "id": 0}
        # print(req)
        res = self._session.post(self._rpc_url, json=req, timeout=TIMEOUT)
        res.raise_for_status()
        res = json.loads(res.text)
        # print(res)
        if "error" in res:
            raise RPCError.from_json(res["error"])
        return res["result"]

    def fetch(self, method, params):
        # the obvious thing to do here is dispatch into fetch_multi.
        # but some providers (alchemy) can't handle batched requests
        # for certain endpoints (debug_traceTransaction).
        return self._raw_fetch_single(method, params)

    def fetch_multi(self, payloads):
        reqs = [(i, m, p) for i, (m, p) in enumerate(payloads)]
        res = self._raw_fetch_multi(reqs)
        return [res[i] for i in range(len(res))]

    # raw fetch - dispatch the args via http request
    # TODO: maybe use async for all of this
    def _raw_fetch_multi(self, payloads):
        req = []
        # print(payloads)
        for i, method, params in payloads:
            req.append({"jsonrpc": "2.0", "method": method, "params": params, "id": i})
        res = self._session.post(self._rpc_url, json=req, timeout=TIMEOUT)
        res.raise_for_status()
        res = json.loads(res.text)

        ret = {}
        for t in res:
            if "error" in t:
                raise RPCError.from_json(t["error"])
            ret[t["id"]] = t["result"]

        # print(ret)

        return ret
