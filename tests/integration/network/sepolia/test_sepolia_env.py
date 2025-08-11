import os
from random import randint, sample
from string import ascii_lowercase

import pytest

import boa
from boa import Etherscan
from boa.deployments import DeploymentsDB, set_deployments_db
from boa.network import NetworkEnv
from boa.rpc import to_bytes
from boa.util.abi import Address
from boa.verifiers import Blockscout

# boa.env.anchor() does not work in prod environment
pytestmark = pytest.mark.ignore_isolation

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


@pytest.fixture(scope="module", params=[Etherscan, Blockscout])
def verifier(request):
    if request.param == Blockscout:
        api_key = os.getenv("BLOCKSCOUT_API_KEY")
        return Blockscout("https://eth-sepolia.blockscout.com", api_key)
    elif request.param == Etherscan:
        api_key = os.environ["ETHERSCAN_API_KEY"]
        return Etherscan("https://api.etherscan.io/v2/api", api_key)
    raise ValueError(f"Unknown verifier: {request.param}")


def test_verify(verifier):
    # generate a random contract so the verification will actually be done again
    name = "".join(sample(ascii_lowercase, 10))
    value = randint(0, 2**256 - 1)
    contract = boa.loads(
        f"""
    import module_lib

    @deploy
    def __init__(t: uint256):
        if t == 0:
            module_lib.throw()

    @external
    def {name}() -> uint256:
        return {value}
        """,
        value,
        name=name,
    )
    result = boa.verify(contract, verifier)
    result.wait_for_verification()
    assert result.is_verified()


def test_env_type():
    # sanity check
    assert isinstance(boa.env, NetworkEnv)


def test_total_supply(simple_contract):
    assert simple_contract.totalSupply() == STARTING_SUPPLY


@pytest.mark.parametrize("amount", [0, 1, 100])
def test_update_total_supply(simple_contract, amount):
    orig_supply = simple_contract.totalSupply()
    simple_contract.update_total_supply(amount)
    assert simple_contract.totalSupply() == orig_supply + amount


@pytest.mark.parametrize("amount", [0, 1, 100])
def test_raise_exception(simple_contract, amount):
    with boa.reverts("oh no!"):
        simple_contract.raise_exception(amount)


# test that simulate= doesn't actually modify the chain
@pytest.mark.parametrize("pragma", ["# pragma version 0.4.0", ""])
def test_simulate_network(pragma):
    # NOTE duplicated code with test_simulate_local
    code = f"""
{pragma}

counter: public(uint256)

@external
def get_next_counter() -> uint256:
    self.counter += 1
    return self.counter
    """
    c = boa.loads(code)

    assert c.get_next_counter() == 1
    assert c.counter() == 1

    assert c.get_next_counter(simulate=True) == 2
    assert c.counter() == 1


# XXX: probably want to test deployment revert behavior


def test_deployment_db():
    with set_deployments_db(DeploymentsDB(":memory:")) as db:
        arg = 5
        contract_name = "test_deployment"

        # contract is written to deployments db
        contract = boa.loads(code, arg, name=contract_name)

        # test get_deployments()
        deployment = next(db.get_deployments())

        initcode = contract.compiler_data.bytecode + arg.to_bytes(32, "big")

        # sanity check all the fields
        assert deployment.contract_address == contract.address
        assert deployment.contract_name == contract.contract_name
        assert deployment.contract_name == contract_name
        assert deployment.deployer == boa.env.eoa
        assert deployment.rpc == boa.env._rpc.name
        assert deployment.source_code == contract.deployer.solc_json

        # some sanity checks on tx_dict and rx_dict fields
        assert to_bytes(deployment.tx_dict["data"]) == initcode
        assert deployment.tx_dict["chainId"] == hex(boa.env.get_chain_id())
        assert Address(deployment.receipt_dict["contractAddress"]) == contract.address
