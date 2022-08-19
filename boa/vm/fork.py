import json
from typing import Any

import requests
from eth.db.account import AccountDB
from eth.db.backends.level import LevelDB
from eth.db.backends.memory import MemoryDB
from eth.db.cache import CacheDB
from eth_utils import int_to_big_endian, to_checksum_address

TIMEOUT = 60  # default timeout for http requests in seconds


_EMPTY = b""  # empty rlp stuff


def _to_hex(s: int) -> str:
    return hex(s)


def _to_int(hex_str: str) -> int:
    return int(hex_str, 16)


def _to_bytes(hex_str: str) -> bytes:
    return bytes.fromhex(hex_str[2:])


class CachingRPC:
    def __init__(self, url: str, block_identifier="latest", cache_file=None):
        if cache_file is not None:
            # use CacheDB as an additional layer over disk
            # ideally would use leveldb lru cache but it's not configurable
            # via eth.db.backends.level.LevelDB.
            self._db = CacheDB(LevelDB(cache_file), cache_size = 1024*1024)
        else:
            self._db = MemoryDB()

        self._rpc_url = url

        if block_identifier == "latest":
            blknum = self._raw_fetch("eth_blockNumber", [], add_blk_id=False)
            # fork 15 blocks back to avoid reorg shenanigans
            self._block_number = _to_int(blknum) - 15
        else:
            self._block_number = block_identifier

    @property
    def _block_id(self):
        return _to_hex(self._block_number)

    # caching fetch
    def fetch(self, *args):
        k = self._mk_key(*args)

        try:
            return self._db[k]
        except KeyError:
            ret = self._raw_fetch(*args)
            self._db[k] = ret
            return ret

    # a stupid key for the kv store
    def _mk_key(self, method: str, params: Any) -> bytes:
        t = {"block": self._block_id, "method": method, "params": params}
        return json.dumps(t).encode("utf-8")

    # raw fetch - dispatch the args via http request
    # TODO: maybe use async for all of this
    def _raw_fetch(self, method, params, add_blk_id=True):
        if add_blk_id:
            params = params + [self._block_id]

        # TODO: batch requests
        req = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
        res = requests.post(self._rpc_url, json=req, timeout=TIMEOUT)
        res.raise_for_status()
        res = res.json()
        if "error" in res:
            raise ValueError(res)

        return res["result"]


# AccountDB which dispatches to an RPC when we don't have the
# data locally
class AccountDBFork(AccountDB):
    _rpc_init_kwargs = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._rpc = CachingRPC(**self._rpc_init_kwargs)

    def _has_account(self, address, from_journal=True):
        return super()._get_encoded_account(address, from_journal) != _EMPTY

    def get_balance(self, address):
        # call super for gas/touched semantics
        s = super().get_balance(address)
        if self._has_account(address):
            return s

        return _to_int(self._rpc.fetch("eth_getBalance", [to_checksum_address(address)]))

    def get_nonce(self, address):
        # call super for gas/touched semantics
        s = super().get_nonce(address)
        if self._has_account(address):
            return s

        return _to_int(self._rpc.fetch("eth_getTransactionCount", [to_checksum_address(address)]))

    def get_code(self, address):
        # call super for gas/touched semantics
        s = super().get_code(address)
        if self._has_account(address):
            return s

        return _to_bytes(self._rpc.fetch("eth_getCode", [to_checksum_address(address)]))

    def get_storage(self, address, slot, from_journal=True):
        # call super for gas/touched semantics
        s = super().get_storage(address, slot, from_journal)

        # if we have the thing, return it directly
        # (cf. AccountStorageDB impl of .get(slot))
        store = super()._get_address_store(address)
        key = int_to_big_endian(slot)
        db = store._journal_storage if from_journal else store._locked_changes
        try:
            if db[key] != _EMPTY:
                return s
        except KeyError:
            # (it was deleted in the journal.)
            return s

        # fallback to rpc
        return _to_int(self._rpc.fetch("eth_getStorageAt", [to_checksum_address(address), _to_hex(slot)]))

    def account_exists(self, address):
        if super().account_exists(address):
            return True

        return self.get_balance(address) > 0 or self.get_nonce(address) > 0
