from dataclasses import dataclass, asdict, fields
from boa.util.open_ctx import Open
from pathlib import Path
from typing import Optional,Any
import json
import sqlite3
from boa.util.abi import Address

@dataclass(frozen=True)
class Deployment:
    contract_address: Address
    name: str
    rpc: str
    from_: Address
    tx_hash: str
    broadcast_ts: float
    tx_dict: dict  # raw tx fields
    receipt_dict: dict  # raw receipt fields
    source_code: Optional[Any]  # optional source code or bundle

    def sql_values(self):
        ret = asdict(self)
        ret["contract_address"] = str(ret["contract_address"])
        ret["from_"] = str(ret["from_"])
        ret["tx_dict"] = json.dumps(ret["tx_dict"])
        ret["receipt_dict"] = json.dumps(ret["receipt_dict"])
        if ret["source_code"] is not None:
            ret["source_code"] = json.dumps(ret["source_code"])
        return ret

    @classmethod
    def from_sql_tuple(cls, values):
        assert len(values) == len(fields(cls))
        ret = dict(zip([field.name for field in fields(cls)], values))
        ret["contract_address"] = Address(ret["contract_address"])
        ret["from_"] = Address(ret["from_"])
        ret["tx_dict"] = json.loads(ret["tx_dict"])
        ret["receipt_dict"] = json.loads(ret["receipt_dict"])
        if ret["source_code"] is not None:
            ret["source_code"] = json.loads(ret["source_code"])
        return cls(**ret)



_CREATE_CMD = """
CREATE TABLE IF NOT EXISTS
    deployments(
        contract_address text,
        name text,
        rpc text,
        tx_hash text,
        from_ text,
        tx_dict text,
        broadcast_ts real,
        receipt_dict text,
        source_code text
    );
"""

class DeploymentsDB:
    def __init__(self, path=":memory:"):
        if path != ":memory:":
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)

        # once 3.12 is min version, use autocommit=True
        self.db = sqlite3.connect(path)

        self.db.execute(_CREATE_CMD)

    def __del__(self):
        self.db.close()

    def insert_deployment(self, deployment: Deployment):
        values = deployment.sql_values()

        values_placeholder = ",".join(["?"] * len(values))

        insert_cmd = f"INSERT INTO deployments VALUES({values_placeholder})"

        self.db.execute(insert_cmd, tuple(values.values()))
        self.db.commit()

    def get_deployments_from_sql(self, sql_query: str, parameters=(), /):
        cur = self.db.execute(sql_query, parameters)
        ret = [Deployment.from_sql_tuple(item) for item in cur.fetchall()]
        return ret


    def get_deployments(self) -> list[Deployment]:
        return self.get_deployments_from_sql("SELECT * FROM deployments")

_db: Optional[DeploymentsDB] = None

def set_deployments_db(db: Optional[DeploymentsDB]):
    def set_(db):
        global _db
        _db = db
    return Open(get_deployments_db, set_, db)

def get_deployments_db():
    global _db
    return _db
