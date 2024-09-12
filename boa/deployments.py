from dataclasses import dataclass, asdict
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
        ret["tx_hash"] = ret["tx_hash"]
        ret["tx_dict"] = json.dumps(ret["tx_dict"])
        ret["receipt_dict"] = json.dumps(ret["receipt_dict"])
        if ret["source_code"] is not None:
            ret["source_code"] = json.dumps(ret["source_code"])
        return ret


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
    def __init__(self, path="./.boa/deployments.db"):
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

        insert_cmd = f"INSERT INTO deployments VALUES({values_placeholder});"

        self.db.execute(insert_cmd, tuple(values.values()))
        self.db.commit()

_db: Optional[DeploymentsDB] = None

def set_deployments_db(db: Optional[DeploymentsDB]):
    def set_(db):
        global _db
        _db = db
    return Open(get_deployments_db, set_, db)

def get_deployments_db():
    global _db
    return _db
