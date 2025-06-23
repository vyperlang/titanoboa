# Deployer

### Description

The deployer pattern in Titanoboa provides a flexible way to deploy contracts with custom settings, initialization parameters, and deployment strategies. Deployers are created by contract loading functions and allow you to configure deployment before actually deploying the contract.

---

## Basic Usage

```python
import boa

# Load contract source without deploying
deployer = boa.load_partial("MyToken.vy")

# Deploy with constructor arguments
token = deployer.deploy("My Token", "MTK", 18, 1000000)

# Deploy at specific address
token2 = deployer.at("0x1234567890123456789012345678901234567890")
```

---

## Deployer Methods

### `deploy(*args, **kwargs)`

Deploy a new instance of the contract.

**Parameters:**
- `*args` - Constructor arguments
- `value` (optional) - ETH to send with deployment
- `gas` (optional) - Gas limit for deployment

```python
# Deploy with constructor args
contract = deployer.deploy(arg1, arg2)

# Deploy with ETH value
contract = deployer.deploy(arg1, arg2, value=10**18)

# Deploy with custom gas limit
contract = deployer.deploy(arg1, arg2, gas=3000000)
```

### `at(address)`

Create a contract instance at an existing address.

**Parameters:**
- `address` - Address where the contract is deployed

```python
# Connect to existing contract
existing = deployer.at("0x1234567890123456789012345678901234567890")

# Works with Address objects too
from boa.util.abi import Address
addr = Address("0x1234567890123456789012345678901234567890")
existing = deployer.at(addr)
```

---

## VyperDeployer

The standard deployer for Vyper contracts loaded from source.

```python
# Create VyperDeployer
deployer = boa.load_partial("Contract.vy")

# Access compiler output
print(deployer.compiler_output)  # Full compiler output
print(deployer.bytecode)  # Deployment bytecode
print(deployer.abi)  # Contract ABI

# Deploy multiple instances
instance1 = deployer.deploy(100)
instance2 = deployer.deploy(200)
instance3 = deployer.deploy(300)
```

---

## ABIDeployer

Deployer for contracts loaded from ABI and bytecode.

```python
# Load from ABI
abi = [{"type": "constructor", "inputs": [{"name": "x", "type": "uint256"}]}]
bytecode = "0x608060405234801561001057600080fd5b5..."

deployer = boa.loads_abi(abi, bytecode=bytecode)
contract = deployer.deploy(42)
```

---

## Blueprint Deployment

Deploy contracts as [EIP-5202](https://eips.ethereum.org/EIPS/eip-5202) blueprints:

```python
# Deploy as blueprint
blueprint = boa.load_partial("MyContract.vy").deploy_as_blueprint()

# Create instances from blueprint
from boa.contracts.vyper.vyper_contract import VyperBlueprint
instance1 = VyperBlueprint(blueprint).deploy(arg1, arg2)
instance2 = VyperBlueprint(blueprint).deploy(arg1, arg2)
```

---

## Factory Pattern

Using deployers to create factory contracts:

```python
# Token factory example
factory_code = """
@external
def create_token(name: String[32], symbol: String[8]) -> address:
    # Deploy logic here
    return deployed_address
"""

factory = boa.loads(factory_code)

# Load token deployer
token_deployer = boa.load_partial("Token.vy")

# In practice, you'd integrate the deployer with the factory
```

---

## Deployment Tracking

Track deployed contracts:

```python
deployed_contracts = []

# Deploy multiple contracts
for i in range(5):
    contract = deployer.deploy(f"Token{i}", f"TK{i}")
    deployed_contracts.append({
        "name": f"Token{i}",
        "address": contract.address,
        "deployer": boa.env.eoa
    })

# Access deployment info
for info in deployed_contracts:
    print(f"{info['name']} at {info['address']}")
```

---

## Network Mode Deployment

Deploy contracts on real networks:

```python
# Connect to network
boa.set_network_env("https://eth-mainnet.g.alchemy.com/v2/YOUR-KEY")

# Load deployer
deployer = boa.load_partial("MyContract.vy")

# Deploy with network-specific settings
from boa.network import NetworkEnv
boa.env.tx_settings.gas_price = 30 * 10**9  # 30 gwei

contract = deployer.deploy(constructor_arg)
print(f"Deployed at: {contract.address}")
print(f"Transaction: {contract.receipt.transactionHash.hex()}")
```

---

## Advanced Patterns

### Deterministic Deployment

Deploy contracts to predictable addresses using CREATE2:

```python
# Using a factory with CREATE2
factory = boa.loads("""
@external
def deploy_deterministic(salt: bytes32, bytecode: Bytes[24576]) -> address:
    return create2(bytecode, salt=salt)
""")

# Calculate expected address
salt = b"my_unique_salt".ljust(32, b'\0')
# Deploy deterministically
```

### Upgradeable Proxy Pattern

```python
# Deploy implementation
implementation_deployer = boa.load_partial("ImplementationV1.vy")
impl = implementation_deployer.deploy()

# Deploy proxy pointing to implementation
proxy_deployer = boa.load_partial("Proxy.vy")
proxy = proxy_deployer.deploy(impl.address)

# Interact through proxy
contract = implementation_deployer.at(proxy.address)
```

### Batch Deployment

```python
def batch_deploy(deployer, configs):
    """Deploy multiple contracts efficiently"""
    contracts = {}

    for config in configs:
        contract = deployer.deploy(
            config["name"],
            config["symbol"],
            value=config.get("value", 0)
        )
        contracts[config["name"]] = contract

    return contracts

# Deploy batch
configs = [
    {"name": "Token A", "symbol": "TKA"},
    {"name": "Token B", "symbol": "TKB"},
    {"name": "Token C", "symbol": "TKC", "value": 10**18},
]

tokens = batch_deploy(token_deployer, configs)
```

---

## Error Handling

Handle deployment errors gracefully:

```python
try:
    contract = deployer.deploy(invalid_arg)
except Exception as e:
    if "constructor" in str(e):
        print("Constructor failed")
    elif "out of gas" in str(e):
        print("Increase gas limit")
    else:
        raise

# Retry with higher gas
contract = deployer.deploy(valid_arg, gas=5000000)
```

---

## See Also

- [Load Contracts](../load_contracts.md) - Loading contracts to create deployers
- [VyperDeployer](../vyper_deployer/overview.md) - VyperDeployer class details
- [VyperBlueprint](../vyper_blueprint/overview.md) - Blueprint deployment
- [Testing](../testing.md) - Testing deployed contracts
