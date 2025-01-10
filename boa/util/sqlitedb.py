import contextlib
import sqlite3
import time
from pathlib import Path

from eth.db.backends.base import BaseDB

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

    _CREATE_CMDS = [
        """
    pragma journal_mode=wal
    """,
        """
    CREATE TABLE IF NOT EXISTS kv_store (
        key TEXT PRIMARY KEY, value BLOB, expires_at float
    )
    """,
        """
    CREATE INDEX IF NOT EXISTS expires_at_index ON kv_store(expires_at)
    """,
    ]

    # flush at least once per second
    _MAX_FLUSH_TIME = 1.0

    def __init__(self, db_path: Path | str, ttl: float = _ONE_MONTH) -> None:
        if db_path != ":memory:":  # sqlite magic path
            db_path = Path(db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)

        self.db: sqlite3.Connection = sqlite3.connect(
            db_path, timeout=0.0, isolation_level=None
        )
        with self.acquire_write_lock():
            for cmd in self.__class__._CREATE_CMDS:
                self.db.execute(cmd)

        # ttl of cache entries in seconds
        # ttl = 100
        self.ttl: float = float(ttl)

        self.gc()

        self._last_flush = get_current_time()
        self._expiry_updates: list[tuple[float, bytes]] = []

    def gc(self):
        with self.acquire_write_lock():
            current_time = get_current_time()
            self.db.execute(
                "DELETE FROM kv_store WHERE expires_at < ?", (current_time,)
            )

    def __del__(self):
        self._flush()

    def _flush_condition(self):
        if len(self._expiry_updates) == 0:
            return False

        next_flush = self._last_flush + self._MAX_FLUSH_TIME
        return len(self._expiry_updates) > 1000 or get_current_time() > next_flush

    def _flush(self):
        with self.acquire_write_lock():
            query_string = """
            UPDATE kv_store
                SET expires_at=?
                WHERE key=?
            """
            self.db.executemany(query_string, self._expiry_updates)
            self._expiry_updates = []

    @contextlib.contextmanager
    def acquire_write_lock(self):
        while True:
            try:
                self.db.execute("BEGIN IMMEDIATE")
                break
            except sqlite3.OperationalError:
                # sleep 10 micros
                time.sleep(1e-4)
                continue
        try:
            yield
            self.db.commit()
        except Exception:
            self.db.rollback()

    @classmethod
    # Creates db as a singleton class variable
    def create(cls, *args, **kwargs):
        if cls._GLOBAL is None:
            cls._GLOBAL = cls(*args, **kwargs)
        return cls._GLOBAL

    def get_expiry_ts(self) -> float:
        current_time = get_current_time()
        return current_time + self.ttl

    def __getitem__(self, key: bytes) -> bytes:
        query_string = """
        SELECT value, expires_at FROM kv_store
            WHERE key=?
        """
        res = self.db.execute(query_string, (key,)).fetchone()
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

    def __setitem__(self, key: bytes, value: bytes) -> None:
        query_string = """
        INSERT INTO kv_store(key, value, expires_at) VALUES (?,?,?)
          ON CONFLICT
          SET value=excluded.value,
              expires_at=excluded.expires_at
        """
        with self.acquire_write_lock():
            expiry_ts = self.get_expiry_ts()
            self.db.execute(query_string, (key, value, expiry_ts))

    def _exists(self, key: bytes) -> bool:
        query_string = "SELECT count(*) FROM kv_store WHERE key=?"
        (res,) = self.db.execute(query_string, (key,)).fetchone()
        return bool(res)

    def __delitem__(self, key: bytes) -> None:
        with self.acquire_write_lock():
            res = self.db.execute("DELETE FROM kv_store WHERE key=?", (key,))
        if res.rowcount == 0:
            raise KeyError(key)
