import os
import requests
from dataclasses import dataclass

TIMEOUT = 60  # default timeout for http requests in seconds


# some utility functions

def to_hex(s: int) -> str:
    return hex(s)


def to_int(hex_str: str) -> int:
    if hex_str == "0x":
        return 0
    return int(hex_str, 16)


def to_bytes(hex_str: str) -> bytes:
    return bytes.fromhex(hex_str[2:])


@dataclass(frozen=True)
class RPCError:
    code: int
    message: str

    @classmethod
    def from_json(cls, data):
        return cls(code=data["code"], message=data["message"])


class EthereumRPC:
    def __init__(self, url: str):
        self._rpc_url = url
        self._session = requests.Session()

    # caching fetch
    def fetch_single(self, method, params):
        (res,) = self.fetch_multi([(method, params)])
        return res

    # raw fetch - dispatch the args via http request
    # TODO: maybe use async for all of this
    def _raw_fetch_multi(self, payloads):
        # TODO: batch the requests
        req = []
        for i, method, params in payloads:
            req.append({"jsonrpc": "2.0", "method": method, "params": params, "id": i})
        res = self._session.post(self._rpc_url, json=req, timeout=TIMEOUT)
        res.raise_for_status()
        res = res.json()

        ret = {}
        for t in res:
            if "error" in t:
                raise RPCError.from_json(t["error"])
            ret[t["id"]] = t["result"]

        return ret

    def fetch_multi(self, payloads):
        res = self._raw_fetch_multi(payloads)
        return [res[i] for i in range(len(res))]
