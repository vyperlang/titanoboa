import sqlite3
import time
from pathlib import Path

from eth.db.backends.base import BaseDB

# poor man's constant
_ONE_MONTH = 30 * 24 * 3600


def get_current_time() -> int:
    return int(time.time())


class SqliteCache(BaseDB):
    """
    Cache which uses sqlite as its backing store which conforms to the
    interface of BaseDB.
    """

    _GLOBAL = None

    _CREATE_CMDS = """
    CREATE TABLE IF NOT EXISTS kv_store (
        key TEXT PRIMARY KEY, value BLOB, expires_at NUM
    );
    CREATE INDEX IF NOT EXISTS expires_at_index ON kv_store(expires_at)
    """.split(
        ";"
    )

    def __init__(self, db_path: Path | str, ttl: int = _ONE_MONTH) -> None:
        if db_path != ":memory:":  # sqlite magic path
            db_path = Path(db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)

        # once 3.12 is min version, use autocommit=True
        self.db: sqlite3.Connection = sqlite3.connect(db_path)
        for cmd in self.__class__._CREATE_CMDS:
            self.db.execute(cmd)

        # ttl of cache entries in seconds
        self.ttl: int = ttl

        self.gc()

    def gc(self):
        current_time = get_current_time()
        self.db.execute("DELETE FROM kv_store WHERE expires_at < ?", (current_time,))

    @classmethod
    # Creates db as a class variable to avoid level db lock error
    # create the singleton db object
    def create(cls, *args, **kwargs):
        if cls._GLOBAL is None:
            cls._GLOBAL = cls(*args, **kwargs)
        return cls._GLOBAL

    def get_expiry_ts(self):
        current_time = get_current_time()
        return current_time + self.ttl

    def __getitem__(self, key: bytes) -> bytes:
        query_string = """
        UPDATE kv_store
            SET expires_at=?
            WHERE key=?
            RETURNING value
        """
        expiry_ts = self.get_expiry_ts()
        res = self.db.execute(query_string, (expiry_ts, key)).fetchone()
        if res is None:
            raise KeyError(key)
        (val,) = res
        self.db.commit()
        return val

    def __setitem__(self, key: bytes, value: bytes) -> None:
        query_string = """
        INSERT INTO kv_store(key, value, expires_at) VALUES (?,?,?)
          ON CONFLICT DO UPDATE
          SET key=excluded.key,
              value=excluded.value,
              expires_at=excluded.expires_at
        """
        expiry_ts = self.get_expiry_ts()
        self.db.execute(query_string, (key, value, expiry_ts))
        self.db.commit()

    def _exists(self, key: bytes) -> bool:
        res = self.db.execute(
            "SELECT count(*) FROM kv_store WHERE key=?", (key,)
        ).fetchone()
        return bool(res)

    def __delitem__(self, key: bytes) -> None:
        res = self.db.execute("DELETE FROM kv_store WHERE key=?", (key,))
        if res.rowcount == 0:
            raise KeyError(key)
        self.db.commit()
