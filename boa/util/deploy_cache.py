import json
from functools import cached_property
from hashlib import sha256
from pathlib import Path
from sqlite3 import connect
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from boa.network import TraceObject


class DeployCache:
    """
    A cache for storing deploy information.
    """

    def __init__(self, path: Path):
        self.path = path

    @cached_property
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = connect(self.path)
        # return results as dictionaries
        connection.row_factory = lambda cursor, row: {
            column[0]: row[index] for index, column in enumerate(cursor.description)
        }
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS deploy_cache (
                deploy_id TEXT, hash TEXT, -- cache key
                receipt TEXT, trace TEXT, -- cache value
                PRIMARY KEY(deploy_id, hash)
            )
        """
        )
        return connection

    def get(
        self, source_code: str, bytecode: bytes, deploy_id: str, chain_id: int
    ) -> tuple[dict, "TraceObject"] | tuple[None, None]:
        if not deploy_id or not source_code:
            return None, None

        hash_str = self._hash_str(bytecode, source_code, chain_id)
        if (row := self._get(deploy_id, hash_str)) is None:
            print(bytecode.hex())
            return None, None

        from boa.network import TraceObject

        return json.loads(row["receipt"]), TraceObject(json.loads(row["trace"]))

    def set(self, source_code, bytecode, deploy_id, chain_id, receipt, trace):
        if deploy_id and source_code:
            hash_str = self._hash_str(bytecode, source_code, chain_id)
            print(bytecode.hex())
            self._insert(deploy_id, hash_str, receipt, trace)

    def _get(self, deploy_id, hashed):
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT receipt, trace
            FROM deploy_cache
            WHERE deploy_id = ? AND hash = ?
        """,
            (deploy_id, hashed),
        )
        return cursor.fetchone()

    def _hash_str(self, bytecode: bytes, source_code: str, chain_id: int) -> str:
        key = source_code, bytecode, chain_id
        return sha256(str(key).encode()).digest().hex()

    def _insert(self, deploy_id, hashed, receipt, trace):
        cursor = self.connection.cursor()
        cursor.execute(
            "INSERT INTO deploy_cache VALUES (?, ?, ?, ?)",
            (deploy_id, hashed, json.dumps(receipt), json.dumps(trace.raw_trace)),
        )
        self.connection.commit()
