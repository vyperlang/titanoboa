import requests

try:
    import ujson as json
except ImportError:
    import json  # type: ignore

TIMEOUT = 60  # default timeout for http requests in seconds


# some utility functions


def to_hex(s: int) -> str:
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


class EthereumRPC:
    def __init__(self, url: str):
        self._rpc_url = url
        self._session = requests.Session()

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
