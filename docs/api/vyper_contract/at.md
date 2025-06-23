# at

### Description

Create a VyperContract instance from an existing deployed contract address. This method allows you to interact with contracts that are already deployed on the blockchain without needing to deploy them again.

---

## Syntax

```python
contract = VyperContract.at(address)
```

**Parameters:**
- `address` - The address of the deployed contract (as string or Address object)

**Returns:**
- A VyperContract instance connected to the specified address

---

## Basic Usage

```python
import boa

# Deploy a contract first
original = boa.loads("""
value: public(uint256)

@external
def set_value(v: uint256):
    self.value = v
""")
original.set_value(42)

# Connect to the same contract using at()
contract = boa.loads("""
value: public(uint256)

@external
def set_value(v: uint256):
    self.value = v
""").at(original.address)

# Verify it's the same contract
assert contract.value() == 42
```

---

## Using with Deployers

The `at()` method is commonly used with deployers:

```python
# Load contract without deploying
deployer = boa.load_partial("MyContract.vy")

# Connect to existing deployment
existing_address = "0x1234567890123456789012345678901234567890"
contract = deployer.at(existing_address)

# Interact with the contract
result = contract.some_function()
```

---

## Network Mode

In network mode, `at()` is essential for interacting with deployed contracts:

```python
# Connect to mainnet
boa.set_network_env("https://eth-mainnet.g.alchemy.com/v2/YOUR-KEY")

# Connect to USDC contract
usdc_address = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
usdc = boa.load_partial("USDC.vy").at(usdc_address)

# Query contract
total_supply = usdc.totalSupply()
print(f"USDC Total Supply: {total_supply / 10**6:,.0f}")
```

---

## From Etherscan

When using `from_etherscan()`, the contract is automatically connected using `at()`:

```python
# This internally uses at() to connect to the deployed contract
contract = boa.from_etherscan(
    "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984",  # UNI token
    name="UNI"
)

# Equivalent to:
# 1. Fetch ABI from Etherscan
# 2. Create deployer with ABI
# 3. Call deployer.at(address)
```

---

## Working with Proxies

Use `at()` to interact with proxy contracts:

```python
# Implementation ABI
implementation_deployer = boa.load_partial("ImplementationV2.vy")

# Connect to proxy address with implementation ABI
proxy_address = "0x1234567890123456789012345678901234567890"
contract = implementation_deployer.at(proxy_address)

# Calls go through proxy to implementation
contract.upgradedFunction()
```

---

## Factory Pattern

Use `at()` with factory-deployed contracts:

```python
factory = boa.loads("""
event ContractDeployed:
    deployed: address

@external
def deploy_child() -> address:
    # Deploy child contract
    child: address = create(Child())
    log ContractDeployed(child)
    return child
""")

# Deploy child through factory
tx = factory.deploy_child()
child_address = tx.return_value

# Connect to deployed child
child_deployer = boa.load_partial("Child.vy")
child = child_deployer.at(child_address)
```

---

## Address Validation

The `at()` method validates addresses:

```python
# Valid addresses work
contract = deployer.at("0x1234567890123456789012345678901234567890")
contract = deployer.at(some_contract.address)

# Invalid addresses raise errors
try:
    contract = deployer.at("0xinvalid")
except ValueError as e:
    print(f"Invalid address: {e}")

# Empty/zero address warning
zero_addr = "0x0000000000000000000000000000000000000000"
contract = deployer.at(zero_addr)  # Works but may not be useful
```

---

## Multiple Instances

Create multiple contract instances at different addresses:

```python
# Token addresses on mainnet
addresses = {
    "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
    "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
}

# Create instances for each
erc20_deployer = boa.load_partial("ERC20.vy")
tokens = {}

for name, addr in addresses.items():
    tokens[name] = erc20_deployer.at(addr)
    print(f"{name}: {tokens[name].symbol()}")
```

---

## Testing Pattern

Use `at()` in tests to verify contract state:

```python
def test_contract_upgrade():
    # Deploy V1
    v1 = boa.load("ContractV1.vy")
    v1.initialize(100)

    # Store address
    contract_address = v1.address

    # Simulate upgrade by connecting V2 ABI to same address
    v2_deployer = boa.load_partial("ContractV2.vy")
    v2 = v2_deployer.at(contract_address)

    # Verify state persisted
    assert v2.get_value() == 100

    # Use new functionality
    v2.new_function()
```

---

## Fork Mode Testing

Test against forked mainnet contracts:

```python
# Fork mainnet
boa.fork("https://eth-mainnet.g.alchemy.com/v2/YOUR-KEY")

# Connect to existing DeFi protocol
vault_deployer = boa.load_partial("YearnVault.vy")
vault = vault_deployer.at("0x1234...")  # Actual vault address

# Test interactions
user = boa.env.generate_address()
boa.env.set_balance(user, 10**20)  # 100 ETH

with boa.env.prank(user):
    vault.deposit(10**18)
```

---

## Error Handling

Handle connection errors gracefully:

```python
def safe_connect(deployer, address):
    """Safely connect to contract with verification"""
    try:
        contract = deployer.at(address)
        # Verify contract exists by calling a view function
        contract.address  # Will fail if no code at address
        return contract
    except Exception as e:
        print(f"Failed to connect to {address}: {e}")
        return None

# Use the safe connection
contract = safe_connect(deployer, some_address)
if contract:
    contract.some_function()
```

---

## See Also

- [Deployer](../common_classes/deployer.md) - Deployer pattern overview
- [Load Contracts](../load_contracts.md) - Loading contracts
- [from_etherscan](../load_contracts.md#from_etherscan) - Load from Etherscan
- [Network Environment](../env/network_env.md) - Network mode usage
