# ABIContract

### Description

ABIContract is a contract class for interacting with contracts via their ABI (Application Binary Interface). This is useful when you have the ABI of a contract but not its source code, such as when interacting with external contracts or contracts deployed by others.

---

## Overview

ABIContract provides a way to interact with any Ethereum contract using just its ABI. It handles:
- Encoding function calls according to the ABI
- Decoding return values
- Event log parsing
- Type checking of inputs

---

## Creating an ABIContract

### From ABI and Address

```python
import boa

# Load contract from ABI
abi = [
    {
        "name": "balanceOf",
        "type": "function",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view"
    },
    {
        "name": "transfer",
        "type": "function",
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "amount", "type": "uint256"}
        ],
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable"
    }
]

# Connect to deployed contract
contract = boa.loads_abi(abi).at("0x...")

# Use the contract
balance = contract.balanceOf(user_address)
contract.transfer(recipient, 100)
```

### From Etherscan

```python
# Automatically fetches ABI from Etherscan
usdc = boa.from_etherscan("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", name="USDC")

# The returned object is an ABIContract
print(type(usdc))  # <class 'boa.contracts.abi.abi_contract.ABIContract'>
```

---

## Working with ABIContract

### Function Calls

ABIContract automatically creates Python methods for each function in the ABI:

```python
# View functions (read-only)
total_supply = contract.totalSupply()
balance = contract.balanceOf(account)
allowance = contract.allowance(owner, spender)

# State-changing functions
contract.transfer(recipient, amount)
contract.approve(spender, amount)
contract.transferFrom(sender, recipient, amount)
```

### Constructor Arguments

When deploying with bytecode:

```python
abi = [...] # Contract ABI with constructor
bytecode = "0x608060405234801561001057600080fd5b5..."

deployer = boa.loads_abi(abi, bytecode=bytecode)
contract = deployer.deploy("Token Name", "TKN", 18, 1000000)
```

### Events

Access and decode events:

```python
# Get all logs
logs = contract.get_logs()

# Filter specific events
transfers = [log for log in logs if log.event_type.name == "Transfer"]

# Access event data
for transfer in transfers:
    print(f"From: {transfer.args['from']}")
    print(f"To: {transfer.args['to']}")
    print(f"Value: {transfer.args['value']}")
```

---

## Type Handling

ABIContract automatically handles type conversions between Python and Solidity types:

### Basic Types

```python
# Integers
contract.setUint(42)  # uint256
contract.setInt(-100)  # int256

# Addresses
contract.setOwner("0x742d35Cc6634C0532925a3b844Bc9e7595f6E86f")

# Booleans
contract.setPaused(True)

# Bytes
contract.setData(b"hello")  # bytes
contract.setBytes32(b"0" * 32)  # bytes32
```

### Arrays

```python
# Fixed arrays
contract.setFixedArray([1, 2, 3, 4, 5])  # uint256[5]

# Dynamic arrays
contract.setDynamicArray([10, 20, 30])  # uint256[]

# Array of addresses
contract.setAddresses(["0x...", "0x...", "0x..."])
```

### Tuples/Structs

```python
# Function expecting tuple/struct
contract.setPosition((100, 50000, True))  # (amount, price, isLong)

# Returning structs
position = contract.getPosition(user)
amount, price, is_long = position
```

---

## Advanced Usage

### Custom Gas Settings

```python
# Set gas limit
contract.expensive_operation(gas=1000000)

# Send ETH with call
contract.deposit(value=10**18)  # 1 ETH
```

### Overloaded Functions

For contracts with overloaded functions, use the full signature:

```python
# If contract has multiple transfer functions
contract["transfer(address,uint256)"](recipient, amount)
contract["transfer(address,uint256,bytes)"](recipient, amount, data)
```

### Raw Calls

For low-level interactions:

```python
# Encode function call
data = contract.transfer.encode_input(recipient, amount)

# Execute raw call
result = boa.env.raw_call(
    contract.address,
    data=data,
    value=0,
    gas=100000
)

# Decode result
success = contract.transfer.decode_output(result)
```

---

## Network Mode

ABIContract works seamlessly with network mode:

```python
# Fork mainnet
boa.fork("https://eth-mainnet.g.alchemy.com/v2/YOUR-KEY")

# Load any contract by ABI
abi = fetch_abi_from_somewhere()
contract = boa.loads_abi(abi).at("0x...")

# Interact with forked state
contract.someMethod()
```

---

## Common Patterns

### ERC20 Token Interaction

```python
# Standard ERC20 ABI
erc20_abi = [
    {"name": "balanceOf", "type": "function", "inputs": [{"name": "account", "type": "address"}], "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "transfer", "type": "function", "inputs": [{"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}], "outputs": [{"name": "", "type": "bool"}]},
    {"name": "approve", "type": "function", "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}], "outputs": [{"name": "", "type": "bool"}]},
    {"name": "allowance", "type": "function", "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}], "outputs": [{"name": "", "type": "uint256"}]},
]

# Create reusable token interface
def get_token(address):
    return boa.loads_abi(erc20_abi).at(address)

# Use with any ERC20 token
usdc = get_token("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
dai = get_token("0x6B175474E89094C44Da98b954EedeAC495271d0F")
```

### Proxy Contract Interaction

```python
# Load implementation ABI
implementation_abi = [...]

# Connect to proxy address with implementation ABI
proxy_address = "0x..."
contract = boa.loads_abi(implementation_abi).at(proxy_address)

# Calls go through proxy to implementation
contract.implementation_function()
```

---

## Limitations

1. **No Source Code**: ABIContract doesn't have access to contract source, so features like storage introspection (`_storage`) are not available

2. **No Internal Functions**: Only external/public functions in the ABI can be called

3. **Type Safety**: Type checking is based on ABI definitions, which may be less strict than Vyper's type system

4. **Gas Estimation**: May be less accurate than VyperContract since it lacks source code context

---

## See Also

- [Load Contracts - loads_abi](../load_contracts.md#loads_abi) - Loading contracts from ABI
- [from_etherscan](../load_contracts.md#from_etherscan) - Load from Etherscan
- [VyperContract](../vyper_contract/overview.md) - Full-featured contract class
- [Common Classes](../common_classes/_BaseEVMContract.md) - Base contract functionality