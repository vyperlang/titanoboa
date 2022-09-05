import os
from typing import Any

import requests

try:
    import ujson as json
except ImportError:
    import json

import eth.rlp.accounts as rlp
from eth.db.account import AccountDB, keccak
from eth.db.backends.level import LevelDB
from eth.db.backends.memory import MemoryDB
from eth.db.cache import CacheDB
from eth.vm.interrupt import MissingBytecode
from eth_utils import int_to_big_endian, to_checksum_address

from boa.util.lrudict import lrudict

TIMEOUT = 60  # default timeout for http requests in seconds


DEFAULT_CACHE_DIR = "~/.cache/titanoboa/fork.db"


_EMPTY = b""  # empty rlp stuff


def _to_hex(s: int) -> str:
    return hex(s)


def _to_int(hex_str: str) -> int:
    return int(hex_str, 16)


def _to_bytes(hex_str: str) -> bytes:
    return bytes.fromhex(hex_str[2:])


class CachingRPC:

    def __init__(
        self, url: str, block_identifier="latest", cache_file=DEFAULT_CACHE_DIR
    ):
        # (default to memory db plyvel not found or cache_file is None)
        self._db = MemoryDB(lrudict(1024*1024))
        self._session = requests.Session()
        if cache_file is not None:
            try:
                cache_file = os.path.expanduser(cache_file)
                # use CacheDB as an additional layer over disk
                # (ideally would use leveldb lru cache but it's not configurable
                # via LevelDB API).
                self._db = CacheDB(LevelDB(cache_file), cache_size=1024 * 1024)
            except ImportError:
                # plyvel not found
                pass

        self._rpc_url = url

        if block_identifier == "latest":
            ((_, blknum),) = self._raw_fetch_multi([(1, "eth_blockNumber", [])]).items()
            # fork 15 blocks back to avoid reorg shenanigans
            self._block_number = _to_int(blknum) - 15
        else:
            self._block_number = block_identifier

    @property
    def _block_id(self):
        return _to_hex(self._block_number)

    # caching fetch
    def fetch_single(self, method, params):
        return self.fetch([(method, params)])[0]

    # caching fetch of multiple payloads
    def fetch(self, payload):
        ret = {}
        ks = []
        batch = []
        for i, (method, params) in enumerate(payload):
            k = self._mk_key(method, params)
            try:
                ret[i] = json.loads(self._db[k])
            except KeyError:
                ks.append(k)
                batch.append((i, method, params))

        if len(batch) > 0:
            res = self._raw_fetch_multi(batch)
            for (i, s) in res.items():
                k = ks[i]
                ret[i] = s
                self._db[k] = json.dumps(s).encode("utf-8")

        return [ret[i] for i in range(len(ret))]

    # a stupid key for the kv store
    def _mk_key(self, method: str, params: Any) -> Any:
        return json.dumps({"method": method, "params": params}).encode("utf-8")

    # raw fetch - dispatch the args via http request
    # TODO: maybe use async for all of this
    def _raw_fetch_multi(self, payloads):
        # TODO: batch requests
        req = []
        for (i, method, params) in payloads:
            req.append({"jsonrpc": "2.0", "method": method, "params": params, "id": i})
        res = self._session.post(self._rpc_url, json=req, timeout=TIMEOUT)
        res.raise_for_status()
        res = res.json()

        ret = {}
        for t in res:
            if "error" in t:
                raise ValueError(res)
            i = t["id"]
            ret[i] = t["result"]

        return ret


# AccountDB which dispatches to an RPC when we don't have the
# data locally
class AccountDBFork(AccountDB):
    _rpc_init_kwargs = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._rpc = CachingRPC(**self._rpc_init_kwargs)

    def _has_account(self, address, from_journal=True):
        return super()._get_encoded_account(address, from_journal) != _EMPTY

    def _get_account(self, address, from_journal=True):
        # cf. super impl of _get_account
        # we need to override this in order so that internal uses of
        # _set_account() work correctly

        if from_journal and address in self._account_cache:
            return self._account_cache[address]

        rlp_account = self._get_encoded_account(address, from_journal)

        if rlp_account:
            account = rlp.decode(rlp_account, sedes=rlp.Account)
        else:
            account = self._get_account_rpc(address)
        if from_journal:
            self._account_cache[address] = account

        return account

    def _get_account_rpc(self, address):
        addr = to_checksum_address(address)
        reqs = [
            ("eth_getBalance", [addr, self._rpc._block_id]),
            ("eth_getTransactionCount", [addr, self._rpc._block_id]),
            ("eth_getCode", [addr, self._rpc._block_id]),
        ]
        res = self._rpc.fetch(reqs)
        balance = _to_int(res[0])
        nonce = _to_int(res[1])
        code = _to_bytes(res[2])
        code_hash = keccak(code)

        return rlp.Account(nonce=nonce, balance=balance, code_hash=code_hash)

    def _get_code_rpc(self, address):
        return _to_bytes(
            self._rpc.fetch_single(
                "eth_getCode", [to_checksum_address(address), self._rpc._block_id]
            )
        )

    def get_code(self, address):
        try:
            return super().get_code(address)
        except MissingBytecode:  # will get thrown if code_hash != hash(empty)
            return self._get_code_rpc(address)

    def get_storage(self, address, slot, from_journal=True):
        # call super to get address warming semantics
        s = super().get_storage(address, slot, from_journal)

        # cf. AccountStorageDB.get()
        store = super()._get_address_store(address)
        key = int_to_big_endian(slot)
        db = store._journal_storage if from_journal else store._locked_changes
        try:
            if db[key] != _EMPTY:
                return s
        except KeyError:
            # (it was deleted in the journal.)
            return s

        addr = to_checksum_address(address)
        return _to_int(
            self._rpc.fetch_single(
                "eth_getStorageAt", [addr, _to_hex(slot), self._rpc._block_id]
            )
        )

    def account_exists(self, address):
        if super().account_exists(address):
            return True

        return self.get_balance(address) > 0 or self.get_nonce(address) > 0
