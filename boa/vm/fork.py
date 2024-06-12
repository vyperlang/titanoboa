import os
import sys
from typing import Any, Type

import rlp
from eth.db.account import AccountDB, keccak
from eth.db.backends.memory import MemoryDB
from eth.db.cache import CacheDB
from eth.db.journal import JournalDB
from eth.rlp.accounts import Account
from eth.vm.interrupt import MissingBytecode
from eth.vm.message import Message
from eth_utils import int_to_big_endian, to_canonical_address, to_checksum_address
from requests import HTTPError

from boa.rpc import RPC, RPCError, fixup_dict, json, to_bytes, to_hex, to_int
from boa.util.lrudict import lrudict

TIMEOUT = 60  # default timeout for http requests in seconds


DEFAULT_CACHE_DIR = "~/.cache/titanoboa/fork.db"
_PREDEFINED_BLOCKS = {"safe", "latest", "finalized", "pending", "earliest"}


_EMPTY = b""  # empty rlp stuff
_HAS_KEY = b"\x01"  # could be anything


class CachingRPC(RPC):
    def __init__(self, rpc: RPC, cache_file: str = DEFAULT_CACHE_DIR):
        # (default to memory db plyvel not found or cache_file is None)
        self._rpc = rpc

        self._cache_file = cache_file
        self._init_db()

    # _loaded is a cache for the constructor.
    # reduces fork time after the first fork.
    _loaded: dict[tuple[str, str], "CachingRPC"] = {}
    _pid: int = os.getpid()  # so we can detect if our fds are bad

    def _init_db(self):
        if self._cache_file is not None:
            try:
                from boa.util.leveldb import LevelDB

                print("(using leveldb)", file=sys.stderr)

                cache_file = os.path.expanduser(self._cache_file)
                # use CacheDB as an additional layer over disk
                # (ideally would use leveldb lru cache but it's not configurable
                # via LevelDB API).
                leveldb = LevelDB.create(cache_file)
                self._db = CacheDB(leveldb, cache_size=1024 * 1024)  # type: ignore
                return
            except ImportError:
                # plyvel not found
                pass

        self._db = MemoryDB(lrudict(1024 * 1024))

    @property
    def identifier(self) -> str:
        return self._rpc.identifier

    @property
    def name(self):
        return self._rpc.name

    def __new__(cls, rpc, cache_file=DEFAULT_CACHE_DIR):
        if isinstance(rpc, cls):
            return rpc

        if os.getpid() != cls._pid:
            # we are in a fork. reload everything so that fds are not corrupted
            cls._loaded = {}
            cls._pid = os.getpid()

        if (rpc.identifier, cache_file) in cls._loaded:
            return cls._loaded[(rpc.identifier, cache_file)]

        ret = super().__new__(cls)
        ret.__init__(rpc, cache_file)
        cls._loaded[(rpc.identifier, cache_file)] = ret
        return ret

    # a stupid key for the kv store
    def _mk_key(self, method: str, params: Any) -> Any:
        return json.dumps({"method": method, "params": params}).encode("utf-8")

    def fetch(self, method, params):
        # cannot dispatch into fetch_multi, doesn't work for debug_traceCall.
        key = self._mk_key(method, params)
        if key in self._db:
            return json.loads(self._db[key])

        result = self._rpc.fetch(method, params)
        self._db[key] = json.dumps(result).encode("utf-8")
        return result

    def fetch_uncached(self, method, params):
        return self._rpc.fetch_uncached(method, params)

    # caching fetch of multiple payloads
    def fetch_multi(self, payload):
        ret = {}
        keys = []
        batch = []
        for item_ix, (method, params) in enumerate(payload):
            key = self._mk_key(method, params)
            try:
                ret[item_ix] = json.loads(self._db[key])
            except KeyError:
                keys.append((key, item_ix))
                batch.append((method, params))

        if len(batch) > 0:
            # fetch_multi is called only with the missing payloads
            # map the results back to the original indices
            for result_ix, rpc_result in enumerate(self._rpc.fetch_multi(batch)):
                key, item_ix = keys[result_ix]
                ret[item_ix] = rpc_result
                self._db[key] = json.dumps(rpc_result).encode("utf-8")

        return [ret[i] for i in range(len(ret))]


# AccountDB which dispatches to an RPC when we don't have the
# data locally
class AccountDBFork(AccountDB):
    @classmethod
    def class_from_rpc(
        cls, rpc: RPC, block_identifier: str, **kwargs
    ) -> Type["AccountDBFork"]:
        class _ConfiguredAccountDB(AccountDBFork):
            def __init__(self, *args, **kwargs2):
                caching_rpc = CachingRPC(rpc, **kwargs)
                super().__init__(caching_rpc, block_identifier, *args, **kwargs2)

        return _ConfiguredAccountDB

    def __init__(self, rpc: CachingRPC, block_identifier: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._dontfetch = JournalDB(MemoryDB())

        self._rpc = rpc

        if block_identifier not in _PREDEFINED_BLOCKS:
            block_identifier = to_hex(block_identifier)

        self._block_info = self._rpc.fetch_uncached(
            "eth_getBlockByNumber", [block_identifier, False]
        )
        self._block_number = to_int(self._block_info["number"])

    @property
    def _block_id(self):
        return to_hex(self._block_number)

    def _has_account(self, address, from_journal=True):
        return super()._get_encoded_account(address, from_journal) != _EMPTY

    def _get_account_helper(self, address, from_journal=True):
        # cf. super impl of _get_account
        if from_journal and address in self._account_cache:
            return self._account_cache[address]

        rlp_account = self._get_encoded_account(address, from_journal)

        if rlp_account:
            return rlp.decode(rlp_account, sedes=Account)
        else:
            return None

    def _get_account(self, address, from_journal=True):
        # we need to override this in order so that internal uses of
        # _set_account() work correctly
        account = self._get_account_helper(address, from_journal)

        if account is None:
            account = self._get_account_rpc(address)

        if from_journal:
            self._account_cache[address] = account

        return account

    def _get_account_rpc(self, address):
        addr = to_checksum_address(address)
        reqs = [
            ("eth_getBalance", [addr, self._block_id]),
            ("eth_getTransactionCount", [addr, self._block_id]),
            ("eth_getCode", [addr, self._block_id]),
        ]
        res = self._rpc.fetch_multi(reqs)
        balance = to_int(res[0])
        nonce = to_int(res[1])
        code = to_bytes(res[2])
        code_hash = keccak(code)

        return Account(nonce=nonce, balance=balance, code_hash=code_hash)

    # try call debug_traceCall to get the ostensible prestate for this call
    def try_prefetch_state(self, msg: Message):
        args = fixup_dict(
            {
                "from": msg.sender,
                "to": msg.to,
                "gas": msg.gas,
                "value": msg.value,
                "data": msg.data,
            }
        )
        try:
            trace_args = [args, self._block_id, {"tracer": "prestateTracer"}]
            trace = self._rpc.fetch("debug_traceCall", trace_args)
        except (RPCError, HTTPError):
            return

        snapshot = self.record()

        for address, account_dict in trace.items():
            try:
                address = to_canonical_address(address)
            except ValueError:
                # the trace we have been given is invalid, roll back changes
                self.discard(snapshot)
                return

            # set account if we don't already have it
            if self._get_account_helper(address) is None:
                balance = to_int(account_dict.get("balance", "0x"))
                code = to_bytes(account_dict.get("code", "0x"))
                nonce = account_dict.get("nonce", 0)  # already an int
                self._set_account(address, Account(nonce=nonce, balance=balance))
                self.set_code(address, code)

            storage = account_dict.get("storage", {})
            for hexslot, hexvalue in storage.items():
                slot = to_int(hexslot)
                value = to_int(hexvalue)
                # set storage if we don't already have it.
                # see AccountStorageDB.get()
                # note we explicitly write 0s, so that they appear
                # in the journal later when called by get_storage
                if not self._helper_have_storage(address, slot):
                    self.set_storage(address, slot, value)

        # the prefetch is lost on later reverts, however the RPC calls are cached
        self.commit(snapshot)

    def get_code(self, address):
        try:
            return super().get_code(address)
        except MissingBytecode:  # will get thrown if code_hash != hash(empty)
            pass

        code_args = [to_checksum_address(address), self._block_id]
        code = to_bytes(self._rpc.fetch("eth_getCode", code_args))
        self.set_code(address, code)
        return code

    def discard(self, checkpoint):
        super().discard(checkpoint)
        self._dontfetch.discard(checkpoint)

    def commit(self, checkpoint):
        super().commit(checkpoint)
        self._dontfetch.commit(checkpoint)

    def record(self):
        checkpoint = super().record()
        self._dontfetch.record(checkpoint)
        return checkpoint

    # helper to determine if something is in the storage db
    # or we need to get from RPC
    def _helper_have_storage(self, address, slot, from_journal=True):
        if not from_journal:
            db = super()._get_address_store(address)._locked_changes
            key = int_to_big_endian(slot)
            return db.get(key, _EMPTY) != _EMPTY

        key = self._get_storage_tracker_key(address, slot)
        return self._dontfetch.get(key) == _HAS_KEY

    def get_storage(self, address, slot, from_journal=True):
        # call super for address warming semantics
        val = super().get_storage(address, slot, from_journal)
        if self._helper_have_storage(address, slot, from_journal=from_journal):
            return val

        fetch_args = [to_checksum_address(address), to_hex(slot), self._block_id]
        val = to_int(self._rpc.fetch("eth_getStorageAt", fetch_args))
        if from_journal:
            # when not from journal, don't override changes
            self.set_storage(address, slot, val)
        return val

    def set_storage(self, address, slot, value):
        super().set_storage(address, slot, value)
        # mark don't fetch
        key = self._get_storage_tracker_key(address, slot)
        self._dontfetch[key] = _HAS_KEY

    def account_exists(self, address):
        if super().account_exists(address):
            return True
        return self.get_balance(address) > 0 or self.get_nonce(address) > 0
