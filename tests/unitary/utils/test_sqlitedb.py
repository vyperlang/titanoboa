import sqlite3
from unittest.mock import Mock

import pytest

from boa.util import sqlitedb
from boa.util.sqlitedb import SqliteCache


@pytest.fixture
def locked_database(tmp_path):
    path = tmp_path / "cache.sqlite"
    with sqlite3.connect(path, isolation_level=None) as connection:
        connection.execute("CREATE TABLE sentinel (value)")
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield path, connection
        finally:
            connection.rollback()
    connection.close()


def test_initialization_retries_locked_journal_mode(locked_database, monkeypatch):
    path, connection = locked_database
    release = Mock(side_effect=lambda _: connection.rollback())
    monkeypatch.setattr(sqlitedb.time, "sleep", release)

    cache = SqliteCache(path)
    try:
        release.assert_called_once()
        assert cache.db.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        cache[b"key"] = b"value"
        assert cache[b"key"] == b"value"
    finally:
        cache._flush()
        cache.db.close()


def test_initialization_lock_timeout_is_not_silenced(locked_database, monkeypatch):
    path, _ = locked_database
    monkeypatch.setattr(sqlitedb.time, "monotonic", Mock(side_effect=[0, 11]))
    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        SqliteCache(path)


def test_initialization_does_not_retry_other_errors(monkeypatch):
    monkeypatch.setattr(SqliteCache, "_PRAGMA_CMDS", ["invalid SQL"])
    sleep = Mock()
    monkeypatch.setattr(sqlitedb.time, "sleep", sleep)
    with pytest.raises(sqlite3.OperationalError, match="syntax error"):
        SqliteCache(":memory:")
    sleep.assert_not_called()
