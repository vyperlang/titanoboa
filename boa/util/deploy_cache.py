import json
from functools import cached_property
from hashlib import sha256
from sqlite3 import connect


class DeployCache:
    def __init__(self, path):
        self.path = path

    @cached_property
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = connect(self.path)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS deploy_cache (
            deploy_id TEXT PRIMARY KEY,
            hash TEXT,
            receipt TEXT,
            trace TEXT
            )
        """
        )
        return connection

    def get(self, source_code, bytecode, deploy_id, chain_id):
        receipt, trace = None, None
        if deploy_id and source_code:
            hashed = self._get_hash(bytecode, deploy_id, source_code, chain_id)
            row = self._get(deploy_id, hashed)
            if row:
                receipt = json.loads(row["receipt"])
                from boa.network import TraceObject

                trace = TraceObject(json.loads(row["trace"]))

        return receipt, trace

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

    def _get_hash(self, bytecode, deploy_id, source_code, chain_id):
        return (
            sha256(str((source_code, bytecode, deploy_id, chain_id)).encode())
            .digest()
            .hex()
        )

    def set(self, source_code, bytecode, deploy_id, chain_id, receipt, trace):
        if deploy_id and source_code:
            hashed = self._get_hash(bytecode, deploy_id, source_code, chain_id)
            self._insert(deploy_id, hashed, receipt, trace)

    def _insert(self, deploy_id, hashed, receipt, trace):
        cursor = self.connection.cursor()
        cursor.execute(
            "INSERT INTO deploy_cache VALUES (?, ?, ?, ?)",
            (deploy_id, hashed, json.dumps(receipt), json.dumps(trace.raw_trace)),
        )
        self.connection.commit()
