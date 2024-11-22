import sqlite3
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings

import boa
import boa.test.strategies as vy
from boa.deployments import _CREATE_CMD, DeploymentsDB, set_deployments_db
from boa.network import NetworkEnv
from boa.rpc import to_bytes
from boa.util.abi import Address

code = """
totalSupply: public(uint256)
balances: HashMap[address, uint256]

@deploy
def __init__(t: uint256):
    self.totalSupply = t
    self.balances[self] = t

@external
def update_total_supply(t: uint16):
    self.totalSupply += convert(t, uint256)

@external
def raise_exception(t: uint256):
    raise "oh no!"
"""

STARTING_SUPPLY = 100


@pytest.fixture(scope="module")
def simple_contract():
    return boa.loads(code, STARTING_SUPPLY)


def test_env_type():
    # sanity check
    assert isinstance(boa.env, NetworkEnv)


def test_network_env_nickname(free_port):
    assert boa.env.nickname == f"http://localhost:{free_port}"


def test_total_supply(simple_contract):
    assert simple_contract.totalSupply() == STARTING_SUPPLY


@settings(max_examples=100, deadline=None)
@given(vy.strategy("uint16"))
def test_update_total_supply(simple_contract, t):
    orig_supply = simple_contract.totalSupply()
    assert orig_supply == STARTING_SUPPLY  # test isolation in fork
    simple_contract.update_total_supply(t)
    assert simple_contract.totalSupply() == orig_supply + t


@settings(max_examples=1, deadline=None)
@given(vy.strategy("uint256"))
def test_raise_exception(simple_contract, t):
    with boa.reverts("oh no!"):
        simple_contract.raise_exception(t)


def test_failed_transaction():
    with pytest.raises(Exception) as ctx:
        boa.loads(code, STARTING_SUPPLY, gas=149377)
    error = str(ctx.value)
    assert error.startswith("txn failed:")


# XXX: probably want to test deployment revert behavior


def test_deployment_db_overriden_contract_name():
    with set_deployments_db(DeploymentsDB(":memory:")) as db:
        arg = 5
        contract_name = "test_deployment"
        filename = "my_filename"

        # contract is written to deployments db
        contract = boa.loads(code, arg, name=contract_name, filename=filename)

        # test get_deployments()
        deployment = next(db.get_deployments())

        initcode = contract.compiler_data.bytecode + arg.to_bytes(32, "big")

        # sanity check all the fields
        assert deployment.contract_address == contract.address
        assert deployment.contract_name == contract.contract_name
        assert deployment.filename == contract.filename
        assert deployment.contract_name == contract_name
        assert deployment.deployer == boa.env.eoa
        assert deployment.rpc == boa.env._rpc.name
        assert deployment.source_code == contract.deployer.solc_json
        assert deployment.abi == contract.abi

        # some sanity checks on tx_dict and rx_dict fields
        assert to_bytes(deployment.tx_dict["data"]) == initcode
        assert deployment.tx_dict["chainId"] == hex(boa.env.get_chain_id())
        assert Address(deployment.receipt_dict["contractAddress"]) == contract.address


def test_deployment_db_no_overriden_name():
    with set_deployments_db(DeploymentsDB(":memory:")) as db:
        arg = 5
        non_contract_name = "test_deployment"

        # contract is written to deployments db
        contract = boa.loads(code, arg)

        # test get_deployments()
        deployment = next(db.get_deployments())

        initcode = contract.compiler_data.bytecode + arg.to_bytes(32, "big")

        # sanity check all the fields
        assert deployment.contract_address == contract.address
        assert deployment.contract_name == contract.contract_name
        assert deployment.filename == "<unknown>"
        assert deployment.contract_name != non_contract_name
        assert deployment.deployer == boa.env.eoa
        assert deployment.rpc == boa.env._rpc.name
        assert deployment.source_code == contract.deployer.solc_json
        assert deployment.abi == contract.abi

        # some sanity checks on tx_dict and rx_dict fields
        assert to_bytes(deployment.tx_dict["data"]) == initcode
        assert deployment.tx_dict["chainId"] == hex(boa.env.get_chain_id())
        assert Address(deployment.receipt_dict["contractAddress"]) == contract.address


@pytest.fixture
def temp_legacy_db_path() -> Path:
    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / "test.db"
    conn = sqlite3.connect(db_path)
    conn.execute(_CREATE_CMD)
    DROP_COLUMN_SQL = "ALTER TABLE deployments DROP COLUMN filename;"
    conn.execute(DROP_COLUMN_SQL)
    return db_path


def test_deployments_db_migration(temp_legacy_db_path):
    sql_db = sqlite3.connect(temp_legacy_db_path)
    cursor = sql_db.execute("PRAGMA table_info(deployments);")
    columns = [col[1] for col in cursor.fetchall()]
    assert "filename" not in columns

    # This next line is what does the migration (added the filename column)
    db = DeploymentsDB(temp_legacy_db_path)
    cursor = db.db.execute("PRAGMA table_info(deployments);")
    columns = [col[1] for col in cursor.fetchall()]
    assert "filename" in columns
