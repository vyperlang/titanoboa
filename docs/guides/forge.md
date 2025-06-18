# Forge analogues

This guide maps common Foundry/Forge commands and patterns to their Titanoboa equivalents.

## Environment Setup

### Forge
```bash
forge init my-project
cd my-project
forge install
```

### Titanoboa
```bash
mkdir my-project
cd my-project
pip install titanoboa
# No separate install needed - dependencies managed via pip
```

## Running Tests

### Forge
```bash
forge test
forge test --match-test testFoo
forge test --match-contract TestContract
forge test -vvvv  # Max verbosity
```

### Titanoboa
```bash
pytest tests/
pytest tests/test_file.py::test_foo
pytest tests/test_contract.py
pytest tests/ -v  # Verbose output
```

## Contract Deployment

### Forge
```solidity
contract = new MyContract();
contract = new MyContract{value: 1 ether}(arg1, arg2);
```

### Titanoboa
```python
contract = boa.load("MyContract.vy")
contract = boa.load("MyContract.vy", arg1, arg2, value=10**18)
```

## Pranking (Impersonating Addresses)

### Forge
```solidity
vm.prank(alice);
contract.withdraw();  // Called as alice

vm.startPrank(alice);
contract.withdraw();
contract.deposit();
vm.stopPrank();
```

### Titanoboa
```python
with boa.env.prank(alice):
    contract.withdraw()  # Called as alice

# Or for multiple calls
with boa.env.prank(alice):
    contract.withdraw()
    contract.deposit()
```

## Setting Balances

### Forge
```solidity
vm.deal(alice, 100 ether);
```

### Titanoboa
```python
boa.env.set_balance(alice, 100 * 10**18)
```

## Time Manipulation

### Forge
```solidity
vm.warp(block.timestamp + 1 days);
skip(1 days);
```

### Titanoboa
```python
boa.env.time_travel(seconds=86400)  # 1 day
```

## Block Manipulation

### Forge
```solidity
vm.roll(block.number + 100);
```

### Titanoboa
```python
boa.env.time_travel(blocks=100)
```

## Forking

### Forge
```bash
forge test --fork-url https://eth-mainnet.g.alchemy.com/v2/KEY
forge test --fork-url https://eth-mainnet.g.alchemy.com/v2/KEY --fork-block-number 12345678
```

### Titanoboa
```python
boa.fork("https://eth-mainnet.g.alchemy.com/v2/KEY")
boa.fork("https://eth-mainnet.g.alchemy.com/v2/KEY", block_identifier=12345678)
```

## Expecting Reverts

### Forge
```solidity
vm.expectRevert("Insufficient balance");
token.transfer(recipient, amount);

vm.expectRevert();
contract.failingFunction();
```

### Titanoboa
```python
with boa.reverts("Insufficient balance"):
    token.transfer(recipient, amount)

with boa.reverts():
    contract.failing_function()
```

## Storage Manipulation

### Forge
```solidity
vm.store(address(contract), bytes32(slot), bytes32(value));
bytes32 stored = vm.load(address(contract), bytes32(slot));
```

### Titanoboa
```python
boa.env.set_storage(contract.address, slot, value)
stored = boa.env.get_storage(contract.address, slot)
```

## Snapshots/Checkpoints

### Forge
```solidity
uint256 snapshot = vm.snapshot();
// Do some operations
vm.revertTo(snapshot);
```

### Titanoboa
```python
with boa.env.anchor():
    # Do some operations
    pass
# Automatically reverts after context
```

## Event Testing

### Forge
```solidity
vm.expectEmit(true, true, false, true);
emit Transfer(from, to, amount);
token.transfer(to, amount);
```

### Titanoboa
```python
token.transfer(to, amount)
logs = token.get_logs()
assert len(logs) == 1
assert logs[0].event_type.name == "Transfer"
assert logs[0].args.sender == from
assert logs[0].args.receiver == to
assert logs[0].args.value == amount
```

## Gas Profiling

### Forge
```bash
forge test --gas-report
forge snapshot
```

### Titanoboa
```bash
pytest tests/ --gas-profile
# Or in code:
boa.env.enable_gas_profiling()
# Run operations
print(boa.env.get_gas_used())
```

## Console Logging

### Forge
```solidity
import "forge-std/console.sol";
console.log("Value:", value);
console.log("Address:", address);
```

### Titanoboa
```vyper
# In Vyper contract:
print("Value:", value)
print("Address:", address)
```

## Creating Mock Contracts

### Forge
```solidity
contract MockToken is ERC20 {
    function mint(address to, uint256 amount) public {
        _mint(to, amount);
    }
}
```

### Titanoboa
```python
mock_token = boa.loads("""
@external
def mint(to: address, amount: uint256):
    self.balances[to] += amount
    self.totalSupply += amount

@external
def balanceOf(account: address) -> uint256:
    return self.balances[account]
""")
```

## Fuzzing

### Forge
```solidity
function testFuzz_withdraw(uint256 amount) public {
    vm.assume(amount > 0 && amount < 1000 ether);
    // Test with random amount
}
```

### Titanoboa
```python
from hypothesis import given, strategies as st

@given(amount=st.integers(min_value=1, max_value=10**21))
def test_withdraw(amount):
    # Test with random amount
    pass
```

## Script Deployment

### Forge
```solidity
// script/Deploy.s.sol
contract DeployScript is Script {
    function run() external {
        vm.startBroadcast();
        new MyContract();
        vm.stopBroadcast();
    }
}
```

### Titanoboa
```python
# scripts/deploy.py
import boa

def deploy():
    # For testnet/mainnet deployment
    boa.set_network_env("https://eth-sepolia.g.alchemy.com/v2/KEY")
    
    # Add deployer account
    from eth_account import Account
    account = Account.from_key("0x...")
    boa.env.add_account(account)
    
    # Deploy contract
    contract = boa.load("MyContract.vy")
    print(f"Deployed at: {contract.address}")

if __name__ == "__main__":
    deploy()
```

## Contract Verification

### Forge
```bash
forge verify-contract --chain-id 1 CONTRACT_ADDRESS MyContract
```

### Titanoboa
```python
# After deployment
boa.verify(contract, etherscan_api_key="YOUR_KEY")
# Or set verifier globally
boa.set_verifier("etherscan", api_key="YOUR_KEY")
```

## Common Testing Patterns

### Setup Pattern

**Forge:**
```solidity
contract TestContract is Test {
    MyContract contract;
    address alice = address(0x1);
    
    function setUp() public {
        contract = new MyContract();
        vm.deal(alice, 100 ether);
    }
}
```

**Titanoboa:**
```python
import pytest
import boa

@pytest.fixture
def contract():
    return boa.load("MyContract.vy")

@pytest.fixture
def alice():
    addr = boa.env.generate_address()
    boa.env.set_balance(addr, 100 * 10**18)
    return addr
```

### Testing Modifiers/Access Control

**Forge:**
```solidity
function testOnlyOwner() public {
    vm.prank(alice);
    vm.expectRevert("Only owner");
    contract.ownerFunction();
}
```

**Titanoboa:**
```python
def test_only_owner(contract, alice):
    with boa.env.prank(alice):
        with boa.reverts("Only owner"):
            contract.owner_function()
```

## Key Differences

1. **Language**: Forge uses Solidity for tests, Titanoboa uses Python
2. **Contract Language**: Forge is for Solidity, Titanoboa is for Vyper
3. **Test Runner**: Forge has built-in runner, Titanoboa uses pytest
4. **State Management**: Forge uses `vm` cheatcodes, Titanoboa uses context managers
5. **Deployment**: Forge uses `new` keyword, Titanoboa uses `boa.load()`

## Best Practices Migration

- Replace Forge scripts with Python scripts using Titanoboa
- Use pytest fixtures instead of `setUp()` functions
- Use context managers (`with` statements) for state changes
- Leverage Python's testing ecosystem (pytest, hypothesis, coverage)
- Use `boa.env.anchor()` for test isolation instead of snapshots