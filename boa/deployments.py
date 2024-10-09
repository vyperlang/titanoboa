import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Generator, Optional

from boa.util.abi import Address
from boa.util.open_ctx import Open

"""
Module to handle deployment objects. When a contract is deployed in network
mode, we enter it into the deployments database so that it can be
queried/verified later.

This module could potentially be handled as plugin functionality / or left
as functionality for higher-level frameworks.
"""

_session_id: str = None  # type: ignore


# generate a unique session id, so that deployments can be queried by session
def get_session_id():
    global _session_id
    if _session_id is None:
        _session_id = str(uuid.uuid4())
    return _session_id


@dataclass(frozen=True)
class Deployment:
    contract_address: Address  # receipt_dict["createAddress"]
    contract_name: str
    rpc: str
    deployer: Address  # ostensibly equal to tx_dict["from"]
    tx_hash: str
    broadcast_ts: float  # time the tx was broadcast
    tx_dict: dict  # raw tx fields
    receipt_dict: dict  # raw receipt fields
    source_code: Optional[Any]  # optional source code or bundle
    abi: Optional[Any]
    session_id: str = field(default_factory=get_session_id)
    deployment_id: Optional[int] = None  # the db-assigned id - primary key

    def sql_values(self):
        ret = asdict(self)
        # sqlite doesn't have json, just dump to string
        ret["tx_dict"] = json.dumps(ret["tx_dict"])
        ret["receipt_dict"] = json.dumps(ret["receipt_dict"])
        if ret["source_code"] is not None:
            ret["source_code"] = json.dumps(ret["source_code"])
        if ret["abi"] is not None:
            ret["abi"] = json.dumps(ret["abi"])
        return ret

    def to_dict(self):
        """
        Convert Deployment object to a dict, which is prepared to be
        dumped to json.
        """
        return asdict(self)

    def to_json(self, *args, **kwargs):
        """
        Convert a Deployment object to a json object. *args and **kwargs
        are forwarded to the `json.dumps()` call.
        """
        return json.dumps(self.to_dict(), *args, **kwargs)

    @classmethod
    def from_sql_tuple(cls, values):
        assert len(values) == len(fields(cls))
        ret = dict(zip([field.name for field in fields(cls)], values))
        ret["contract_address"] = Address(ret["contract_address"])
        ret["deployer"] = Address(ret["deployer"])
        ret["tx_dict"] = json.loads(ret["tx_dict"])
        ret["receipt_dict"] = json.loads(ret["receipt_dict"])
        if ret["source_code"] is not None:
            ret["source_code"] = json.loads(ret["source_code"])
        if ret["abi"] is not None:
            ret["abi"] = json.loads(ret["abi"])
        return cls(**ret)


_CREATE_CMD = """
CREATE TABLE IF NOT EXISTS
    deployments(
        deployment_id integer primary key autoincrement,
        session_id text,
        contract_address text,
        contract_name text,
        rpc text,
        deployer text,
        tx_hash text,
        broadcast_ts real,
        tx_dict text,
        receipt_dict text,
        source_code text,
        abi text
    );
"""


class DeploymentsDB:
    def __init__(self, path=":memory:"):
        if path != ":memory:":  # sqlite magic path
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
        colnames = ",".join(values.keys())

        insert_cmd = f"INSERT INTO deployments({colnames}) VALUES({values_placeholder})"

        self.db.execute(insert_cmd, tuple(values.values()))
        self.db.commit()

    def _get_deployments_from_sql(self, sql_query: str, parameters=(), /):
        cur = self.db.execute(sql_query, parameters)
        return (Deployment.from_sql_tuple(item) for item in cur)

    def _get_fieldnames_str(self) -> str:
        return ",".join(field.name for field in fields(Deployment))

    def get_deployments(self) -> Generator[Deployment, None, None]:
        """
        Return all the deployments from the database. Returns an iterator
        which can be converted to a list with `list(db.get_deployments())`.

        Returns the deployments ordered by most recent first, i.e. using
        an `ORDER BY deployment_id DESC` clause.
        """
        fieldnames = self._get_fieldnames_str()
        return self._get_deployments_from_sql(
            f"SELECT {fieldnames} FROM deployments order by deployment_id desc"
        )


_db: Optional[DeploymentsDB] = None


def set_deployments_db(db: Optional[DeploymentsDB]):
    def set_(db):
        global _db
        _db = db

    return Open(get_deployments_db, set_, db)


def get_deployments_db():
    global _db
    return _db
