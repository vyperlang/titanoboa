import contextlib
import sqlite3
import time
from pathlib import Path

from eth.db.backends.base import BaseDB

# from vyper.utils import timeit

# poor man's constant
_ONE_MONTH = 30 * 24 * 3600


def get_current_time() -> float:
    return time.time()


class SqliteCache(BaseDB):
    """
    Cache which uses sqlite as its backing store which conforms to the
    interface of BaseDB.
    """

    _GLOBAL = None

    _debug = False

    _PRAGMA_CMD = """
        -- tuning
        pragma journal_mode = wal;
        pragma temp_store = memory;

        -- it's ok to lose some of the wal, this is just a cache
        pragma synchronous = normal;

        -- https://sqlite.org/forum/forumpost/3ce1ee76242cfb29
        /* "I'm of the opinion that you should never use mmap"
           - Richard Hipp
        */
        -- pragma mmap_size = 30000000000;
        -- not sure if these help or hurt things:
        -- pragma auto_vacuum = incremental;
        -- pragma page_size = 512;
        pragma cache_size = 10000;
        """

    _CREATE_CMDS = [
        """
        -- initialize schema
        CREATE TABLE IF NOT EXISTS kv_store (
            key TEXT PRIMARY KEY, value BLOB, expires_at float
        );
        """,
        """
        CREATE INDEX IF NOT EXISTS expires_at_index ON kv_store(expires_at);
        """,
    ]

    # flush at least once every second
    _FLUSH_INTERVAL = 1.0

    def __init__(self, db_path: Path | str, ttl: float = _ONE_MONTH) -> None:
        if db_path != ":memory:":  # sqlite magic path
            db_path = Path(db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)

        # short timeout so that we don't get stuck waiting for
        # OperationalError on exit (e.g. in __del__()), but long enough
        # so that we don't spinlock in acquire lock. 10ms seems like
        # a good balance.
        # note that informal benchmarks performed on my machine(TM) had
        # the following results:
        # __getitem__: 45us
        # __getitem__ (from wal): 120us
        # __setitem__: 300us
        # gc: 40us
        # flush: 6000us
        TIMEOUT = 0.010  # 10ms

        self.db: sqlite3.Connection = sqlite3.connect(
            db_path, timeout=TIMEOUT, isolation_level=None
        )

        # cache the cursor
        self._cursor = self.db.cursor()

        # initialize other fields
        self._last_flush = get_current_time()
        self._expiry_updates: list[tuple[float, bytes]] = []

        # ttl of cache entries in seconds
        self.ttl: float = float(ttl)

        self._cursor.executescript(self._PRAGMA_CMD)
        with self.acquire_write_lock():
            for cmd in self._CREATE_CMDS:
                self._cursor.execute(cmd)

        self.gc()

    def gc(self):
        with self.acquire_write_lock():
            current_time = get_current_time()
            self._cursor.execute(
                "DELETE FROM kv_store WHERE expires_at < ?", (current_time,)
            )
            # batch writes in here
            self._flush(nolock=True)

    def __del__(self):
        # try to flush but if we fail, no worries. these are optional
        # operations.
        try:
            self._flush()
        except Exception:
            pass

    def _flush_condition(self):
        if len(self._expiry_updates) >= 1000:
            return True
        next_flush = self._last_flush + self._FLUSH_INTERVAL
        if get_current_time() > next_flush:
            return True
        return False

    # @timeit("FLUSH")
    def _flush(self, nolock=False):
        # set nolock=True if the caller has already acquired a lock.
        if len(self._expiry_updates) == 0:
            self._last_flush = get_current_time()
            return

        acquire_lock = contextlib.nullcontext if nolock else self.acquire_write_lock
        with acquire_lock():
            query_string = """
            UPDATE kv_store
                SET expires_at=?
                WHERE key=?
            """
            self._cursor.executemany(query_string, self._expiry_updates)

        self._expiry_updates = []
        self._last_flush = get_current_time()

    @contextlib.contextmanager
    def acquire_write_lock(self):
        count = 0
        while True:
            try:
                self._cursor.execute("BEGIN IMMEDIATE")
                break
            except sqlite3.OperationalError as e:
                count += 1
                # deadlock scenario, should not happen
                if count > 1000:
                    msg = "deadlock encountered! this means there is a bug in"
                    msg += " titanoboa. please report this on the titanoboa"
                    msg += " issue tracker on github. in the meantime as a"
                    msg += " workaround, try disabling the sqlite cache."
                    raise Exception(msg) from e
                # sleep 100 micros, roughly the time for a write query to
                # complete.
                # keep in mind that time.sleep takes 50us+:
                # https://github.com/python/cpython/issues/125997.
                time.sleep(1e-4)
                continue
        try:
            yield
            self._cursor.execute("COMMIT")
        except Exception as e:
            if self._debug:
                # if we are in tests, raise the exception
                raise Exception("fail") from e
            # this shouldn't really happen, but it could happen if there
            # is some concurrent, non-boa write to the database, so just
            # roll back (fail "gracefully") and move on.
            self._cursor.execute("ROLLBACK")

    @classmethod
    # Creates db as a singleton class variable
    def create(cls, *args, **kwargs):
        if cls._GLOBAL is None:
            cls._GLOBAL = cls(*args, **kwargs)
        return cls._GLOBAL

    def get_expiry_ts(self) -> float:
        current_time = get_current_time()
        return current_time + self.ttl

    # @timeit("CACHE HIT")
    def __getitem__(self, key: bytes) -> bytes:
        query_string = """
        SELECT value, expires_at FROM kv_store
            WHERE key=?
        """
        # with timeit("CACHE HIT"):
        res = self._cursor.execute(query_string, (key,)).fetchone()
        if res is None:
            raise KeyError(key)

        val, expires_at = res

        # to reduce contention, instead of updating the expiry every
        # time, batch the expiry updates.
        if expires_at - get_current_time() > self.ttl / 100:
            new_expiry_ts = self.get_expiry_ts()
            self._expiry_updates.append((new_expiry_ts, key))
            if self._flush_condition():
                self._flush()

        return val

    # @timeit("CACHE MISS")
    def __setitem__(self, key: bytes, value: bytes) -> None:
        # with timeit("CACHE MISS"):
        with self.acquire_write_lock():
            query_string = """
            INSERT INTO kv_store(key, value, expires_at) VALUES (?,?,?)
              ON CONFLICT DO UPDATE
              SET value=excluded.value,
                  expires_at=excluded.expires_at
            """
            expiry_ts = self.get_expiry_ts()
            self._cursor.execute(query_string, (key, value, expiry_ts))

            # we already have a lock, batch in some writes if needed
            if self._flush_condition():
                self._flush(nolock=True)

    def _exists(self, key: bytes) -> bool:
        query_string = "SELECT count(*) FROM kv_store WHERE key=?"
        (res,) = self._cursor.execute(query_string, (key,)).fetchone()
        return bool(res)

    def __delitem__(self, key: bytes) -> None:
        with self.acquire_write_lock():
            res = self._cursor.execute("DELETE FROM kv_store WHERE key=?", (key,))
        if res.rowcount == 0:
            raise KeyError(key)
