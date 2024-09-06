import boa
import os
import pytest
from unittest.mock import patch, MagicMock

def test_decode_struct():
    code = """
struct Point:
    x: int8
    y: int8

point: Point

@deploy
def __init__():
    self.point = Point({x: 1, y: 2})
"""
    result = boa.loads(code)._storage.point.get()
    assert str(result) == "Point({'x': 1, 'y': 2})"


def test_decode_tuple():
    code = """
point: (int8, int8)

@deploy
def __init__():
    self.point[0] = 1
    self.point[1] = 2
"""
    assert boa.loads(code)._storage.point.get() == (1, 2)


def test_decode_string_array():
    code = """
point: int8[2]

@deploy
def __init__():
    self.point[0] = 1
    self.point[1] = 2
"""
    assert boa.loads(code)._storage.point.get() == [1, 2]


def test_decode_bytes_m():
    code = """
b: bytes2

@deploy
def __init__():
    self.b = 0xd9b6
"""
    assert boa.loads(code)._storage.b.get() == bytes.fromhex("d9b6")


def test_decode_dynarray():
    code = """
point: DynArray[int8, 10]

@deploy
def __init__():
    self.point = [1, 2]
"""
    assert boa.loads(code)._storage.point.get() == [1, 2]


def test_self_destruct():
    code = """
@external
def foo() -> bool:
    selfdestruct(msg.sender)
    """
    c = boa.loads(code)

    c.foo()


@pytest.mark.skipif(not os.getenv("BLOCKSCOUT_API_KEY"), reason="BLOCKSCOUT_API_KEY not set")
def test_contract_verification():
    """
    This test case rigorously examines the contract verification process.
    It deploys a rudimentary smart contract and subsequently attempts to verify it,
    leveraging mock API responses to simulate both successful and failed verifications.
    """
    code = """
@external
def hello() -> String[32]:
    return "Hello, World!"
"""
    # Fabricate a mock response emulating Blockscout's API
    mock_response = MagicMock()
    mock_response.json.return_value = {"status": "1"}

    # Employ a context manager to intercept and replace the requests.post function
    with patch('requests.post', return_value=mock_response):
        # Instantiate and deploy the contract with immediate verification
        contract = boa.loads(code, verify=True, explorer="blockscout")
        
        # Ascertain the contract's successful deployment and correct type
        assert isinstance(contract, boa.VyperContract), "Contract deployment failed or yielded unexpected type"
        
        # Validate the contract's functionality post-deployment
        assert contract.hello() == "Hello, World!", "Contract function 'hello()' produced unexpected output"

        # Note: Verification success message should be logged or returned.
        # Adapt the following assertion based on your implementation's specific output mechanism
        # assert "Contract verified successfully" in captured_output

    # Scrutinize the system's behavior when confronted with a failed verification scenario
    mock_response.json.return_value = {"status": "0"}
    with patch('requests.post', return_value=mock_response):
        with pytest.raises(Exception) as excinfo:
            boa.loads(code, verify=True, explorer="blockscout")
        assert "Contract verification failed" in str(excinfo.value), "Expected exception not raised or incorrect error message"
