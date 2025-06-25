"""
Network tests for EIP-7702 functionality using Anvil.
These tests require a running Anvil instance with EIP-7702 support.
"""

import pytest
from eth_account import Account

import boa
from boa.util.abi import Address


@pytest.fixture
def simple_wallet_code():
    """Simple wallet contract for testing"""
    return """
owner: public(address)

@deploy
def __init__():
    self.owner = msg.sender

@external
def execute(target: address, value: uint256, data: Bytes[1024]) -> Bytes[1024]:
    assert msg.sender == self.owner, "Only owner"
    success: bool = False
    response: Bytes[1024] = b""
    success, response = raw_call(
        target,
        data,
        value=value,
        max_outsize=1024,
        revert_on_failure=False
    )
    assert success, "Call failed"
    return response
"""


class TestEIP7702Network:
    """Tests for EIP-7702 in NetworkEnv with Anvil"""

    def test_sign_authorization(self, simple_wallet_code):
        """Test signing an authorization"""
        # Deploy wallet logic
        wallet_logic = boa.loads(simple_wallet_code)

        # Create an account
        account = Account.create()
        boa.env.add_account(account)

        # Sign authorization
        auth = boa.env.sign_authorization(
            account=account, contract_address=wallet_logic, nonce=0
        )

        # Verify authorization structure
        assert "chainId" in auth
        assert "address" in auth
        assert "nonce" in auth
        assert "yParity" in auth
        assert "r" in auth
        assert "s" in auth

        assert auth["address"] == wallet_logic.address
        assert auth["nonce"] == 0

    def test_sign_authorization_with_contract_object(self, simple_wallet_code):
        """Test that contract objects can be passed to sign_authorization"""
        wallet = boa.loads(simple_wallet_code)
        account = Account.create()
        boa.env.add_account(account)

        # Pass contract object directly
        auth = boa.env.sign_authorization(account, wallet)
        assert auth["address"] == wallet.address

    def test_execute_with_authorizations(self):
        """Test the execute_with_authorizations helper"""
        # Create test accounts
        alice = Account.create()
        bob = Account.create()

        for account in [alice, bob]:
            boa.env.add_account(account)
            # Fund the accounts
            boa.env.set_balance(account.address, 10 * 10**18)

        # Create mock authorizations (would be real in actual usage)
        mock_auths = [
            {
                "chainId": boa.env.get_chain_id(),
                "address": Address("0x" + "11" * 20),
                "nonce": 0,
                "yParity": 0,
                "r": 1,
                "s": 1,
            }
        ]

        # Test that execute_with_authorizations works
        result = boa.env.execute_with_authorizations(
            mock_auths,
            target=bob.address,
            data=b"",
            value=1 * 10**18,
            sender=alice.address,
        )

        assert result is not None

    @pytest.mark.skip(reason="Requires Anvil with EIP-7702 support")
    def test_eoa_delegation_flow(self, simple_wallet_code):
        """Test full EOA delegation flow"""
        # Deploy wallet logic contract
        wallet_logic = boa.loads(simple_wallet_code)

        # Create EOA that will delegate
        eoa = Account.create()
        boa.env.add_account(eoa)
        boa.env.set_balance(eoa.address, 10 * 10**18)

        # Sign authorization for EOA to act as wallet
        auth = boa.env.sign_authorization(
            account=eoa, contract_address=wallet_logic, nonce=0
        )

        # Deploy a target contract to interact with
        target_code = """
value_received: public(uint256)

@external
@payable
def receive_value():
    self.value_received = msg.value
"""
        target = boa.loads(target_code)

        # Execute transaction where EOA acts as a wallet
        # The EOA will execute wallet_logic's code
        calldata = wallet_logic.execute.prepare_calldata(
            target.address,
            1 * 10**18,  # Send 1 ETH
            target.receive_value.prepare_calldata(),
        )

        _ = boa.env.execute_with_authorizations(
            [auth],
            target=eoa.address,  # Call the EOA itself
            data=calldata,
            sender=eoa.address,
        )

        # Verify the target contract received the value
        assert target.value_received() == 1 * 10**18
