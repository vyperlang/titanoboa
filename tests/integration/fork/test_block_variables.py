import pytest

import boa


def test_block_number():
    getter_contract = boa.loads("""
    @external
    def get_block_number() -> uint256:
        return block.number
    """)
    assert getter_contract.get_block_number() == boa.env.evm.patch.block_number


def test_block_timestamp():
    getter_contract = boa.loads("""
    @external
    def get_block_timestamp() -> uint256:
        return block.timestamp
    """)
    assert getter_contract.get_block_timestamp() == boa.env.evm.patch.timestamp


def test_chain_id():
    getter_contract = boa.loads("""
    @external
    def get_chain_id() -> uint256:
        return chain.id
    """)
    assert getter_contract.get_chain_id() == boa.env.evm.patch.chain_id


def test_prev_hash():
    getter_contract = boa.loads("""
    @external
    def get_prevhash() -> bytes32:
        return block.prevhash
    """)
    # print(getter_contract.get_prevhash())
    # assert True
    assert getter_contract.get_prevhash() == list(boa.env.evm.patch.prev_hashes)[0]


def test_block_hash():  # only works for previous block
    current_block = boa.env.evm.patch.block_number
    getter_contract = boa.loads(f"""
    @external
    def get_blockhash() -> bytes32:
        return blockhash({current_block-1})
    """)
    assert getter_contract.get_blockhash() == list(boa.env.evm.patch.prev_hashes)[0]
