import os
import pickle
import sys
from pathlib import Path
from typing import Any, Optional, Type

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

from boa.rpc import RPC, RPCError, fixup_dict, to_bytes, to_hex, to_int
from boa.util.lrudict import lrudict
from boa.util.sqlitedb import SqliteCache

TIMEOUT = 60  # default timeout for http requests in seconds


DEFAULT_CACHE_DIR = "~/.cache/titanoboa/fork/"
_PREDEFINED_BLOCKS = {"safe", "latest", "finalized", "pending", "earliest"}


_EMPTY = b""  # empty rlp stuff
_HAS_KEY = b"\x01"  # could be anything


class CachingRPC(RPC):
    # _loaded is a cache for the constructor.
    # reduces fork time after the first fork.
    _loaded: dict[tuple[str, int, str], "CachingRPC"] = {}
    _pid: int = os.getpid()  # so we can detect if our fds are bad

    def __new__(cls, rpc, chain_id, debug, cache_dir=DEFAULT_CACHE_DIR):
        if isinstance(rpc, cls):
            if rpc._chain_id == chain_id:
                return rpc
            else:
                # unwrap
                rpc = rpc._rpc

        if os.getpid() != cls._pid:
            # we are in a fork. reload everything so that fds are not corrupted
            cls._loaded = {}
            cls._pid = os.getpid()

        if (rpc.identifier, chain_id, cache_dir) in cls._loaded:
            return cls._loaded[(rpc.identifier, chain_id, cache_dir)]

        ret = super().__new__(cls)
        ret.__init__(rpc, chain_id, debug, cache_dir)
        cls._loaded[(rpc.identifier, chain_id, cache_dir)] = ret
        return ret

    def __init__(
        self,
        rpc: RPC,
        chain_id: int,
        debug: bool = False,
        cache_dir: Optional[str] = DEFAULT_CACHE_DIR,
    ):
        self._rpc = rpc
        self._debug = debug

        self._chain_id = chain_id  # TODO: check if this is needed
        self._cache_dir = cache_dir

        self._init_db()

    @classmethod
    def _cache_filepath(cls, cache_dir, chain_id):
        return Path(cache_dir) / f"chainid_{hex(chain_id)}-sqlite.db"

    def _init_db(self):
        if self._cache_dir is not None:
            cache_file = self._cache_filepath(self._cache_dir, self._chain_id)
            cache_file = os.path.expanduser(cache_file)
            sqlitedb = SqliteCache.create(cache_file)
            # use CacheDB as an additional layer over disk
            self._db = CacheDB(sqlitedb, cache_size=1024 * 1024)  # type: ignore

        # use memory db if cache_file is None
        else:
            self._db = MemoryDB(lrudict(1024 * 1024))

    @property
    def identifier(self) -> str:
        return self._rpc.identifier

    @property
    def name(self):
        return self._rpc.name

    # a stupid key for the kv store
    def _mk_key(self, method: str, params: Any) -> Any:
        return pickle.dumps((method, params))

    _col_limit = 97

    def _debug_dump(self, item):
        str_item = str(item)
        # TODO: make this configurable
        if len(str_item) > self._col_limit:
            return str_item[: self._col_limit] + "..."
        return str_item

    def fetch(self, method, params):
        # cannot dispatch into fetch_multi, doesn't work for debug_traceCall.
        key = self._mk_key(method, params)
        if self._debug:
            print(method, self._debug_dump(params), file=sys.stderr)
        if key in self._db:
            ret = pickle.loads(self._db[key])
            if self._debug:
                print("(hit)", self._debug_dump(ret), file=sys.stderr)
            return ret

        result = self._rpc.fetch(method, params)
        if self._debug:
            print("(miss)", self._debug_dump(result), file=sys.stderr)
        self._db[key] = pickle.dumps(result)
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
                ret[item_ix] = pickle.loads(self._db[key])
                if self._debug:
                    print(method, self._debug_dump(params), file=sys.stderr)
                    print("(hit)", self._debug_dump(ret[item_ix]), file=sys.stderr)
            except KeyError:
                keys.append((key, item_ix))
                batch.append((method, params))

        if len(batch) > 0:
            # fetch_multi is called only with the missing payloads
            # map the results back to the original indices
            for result_ix, rpc_result in enumerate(self._rpc.fetch_multi(batch)):
                key, item_ix = keys[result_ix]
                ret[item_ix] = rpc_result
                if self._debug:
                    params = batch[item_ix][1]
                    print(method, self._debug_dump(params), file=sys.stderr)
                    print("(miss)", self._debug_dump(rpc_result), file=sys.stderr)
                self._db[key] = pickle.dumps(rpc_result)

        return [ret[i] for i in range(len(ret))]


# AccountDB which dispatches to an RPC when we don't have the
# data locally
class AccountDBFork(AccountDB):
    @classmethod
    def class_from_rpc(
        cls, rpc: RPC, block_identifier: str, debug: bool, **kwargs
    ) -> Type["AccountDBFork"]:
        class _ConfiguredAccountDB(AccountDBFork):
            def __init__(self, *args, **kwargs2):
                chain_id = int(rpc.fetch_uncached("eth_chainId", []), 16)
                caching_rpc = CachingRPC(rpc, chain_id, debug, **kwargs)
                super().__init__(
                    caching_rpc, chain_id, block_identifier, *args, **kwargs2
                )

        return _ConfiguredAccountDB

    def __init__(
        self, rpc: CachingRPC, chain_id: int, block_identifier: str, *args, **kwargs
    ) -> None:
        super().__init__(*args, **kwargs)

        self._dontfetch = JournalDB(MemoryDB())

        self._rpc = rpc

        if block_identifier not in _PREDEFINED_BLOCKS:
            block_identifier = to_hex(block_identifier)

        self._chain_id = chain_id

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
