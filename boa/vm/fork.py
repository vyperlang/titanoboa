import os
from typing import Any

import eth.rlp.accounts as rlp
import orjson as json
import requests
from eth.db.account import AccountDB, keccak
from eth.db.backends.level import LevelDB
from eth.db.cache import CacheDB
from eth.vm.interrupt import EVMMissingData
from eth_utils import to_checksum_address

TIMEOUT = 60  # default timeout for http requests in seconds


DEFAULT_CACHE_DIR = "~/.cache/titanoboa/fork.db"


_EMPTY = b""  # empty rlp stuff


# a storage root which indicates that we need to fall back to RPC.
# it also cleanly makes storage lookups fail if we do not have the key
# in the VM already.
_SENTINEL_ROOT = b"titanoboa".rjust(32, b"\x00")


def _to_hex(s: int) -> str:
    return hex(s)


def _to_int(hex_str: str) -> int:
    return int(hex_str, 16)


def _to_bytes(hex_str: str) -> bytes:
    return bytes.fromhex(hex_str[2:])


class CachingRPC:
    def __init__(self, url: str, block_identifier="latest", cache_file=None):
        cache_file = cache_file or DEFAULT_CACHE_DIR

        cache_file = os.path.expanduser(cache_file)
        # use CacheDB as an additional layer over disk
        # ideally would use leveldb lru cache but it's not configurable
        # via eth.db.backends.level.LevelDB.
        self._db = CacheDB(LevelDB(cache_file), cache_size=1024 * 1024)

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
    def fetch(self, method, params):
        k = self._mk_key(method, params)

        try:
            return json.loads(self._db[k])
        except KeyError:
            ret = self._raw_fetch(method, params)
            self._db[k] = json.dumps(ret)
            return ret

    # a stupid key for the kv store
    def _mk_key(self, method: str, params: Any) -> bytes:
        t = {"block": self._block_id, "method": method, "params": params}
        return json.dumps(t)

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
        address = to_checksum_address(address)
        balance = _to_int(self._rpc.fetch("eth_getBalance", [address]))
        nonce = _to_int(self._rpc.fetch("eth_getTransactionCount", [address]))
        code = _to_bytes(self._rpc.fetch("eth_getCode", [address]))
        code_hash = keccak(code)

        return rlp.Account(
            nonce=nonce,
            balance=balance,
            code_hash=code_hash,
            storage_root=_SENTINEL_ROOT,
        )
        # return rlp.Account(nonce=nonce, balance=balance, code_hash=code_hash)

    def get_code(self, address):
        # call super for gas/touched semantics
        if self._get_storage_root(address) == _SENTINEL_ROOT:
            # get_code_hash(address) != keccak(_EMPTY) and not super().get_code(address):
            address = to_checksum_address(address)
            code = _to_bytes(self._rpc.fetch("eth_getCode", [address]))
            return code

        return super().get_code(address)

    def get_storage(self, address, slot, from_journal=True):
        try:
            return super().get_storage(address, slot, from_journal)
        # this happens because the storage_root does not match the empty trie,
        # causing MissingTrieNode to be thrown
        except EVMMissingData:
            # fallback to rpc
            addr = to_checksum_address(address)
            return _to_int(self._rpc.fetch("eth_getStorageAt", [addr, _to_hex(slot)]))

    def account_exists(self, address):
        if super().account_exists(address):
            return True

        return self.get_balance(address) > 0 or self.get_nonce(address) > 0
