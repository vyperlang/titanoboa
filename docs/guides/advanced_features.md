# Advanced Features Guide

This guide covers advanced Titanoboa features that provide powerful capabilities for contract development, testing, and debugging.

## Contract Introspection

### Storage Variable Access

Titanoboa provides direct access to contract storage variables through special properties:

```python
import boa

# Deploy a contract
src = """
owner: public(address)
balances: public(HashMap[address, uint256])
total_supply: public(uint256)

@deploy
def __init__():
    self.owner = msg.sender
    self.total_supply = 1_000_000
    self.balances[msg.sender] = self.total_supply
"""
contract = boa.loads(src)

# Access storage variables directly
print(contract._storage.owner)  # '0x00000000000000000000000000000000000000065'
print(contract._storage.total_supply)  # 1000000
print(contract._storage.balances)  # {Address('0x00...65'): 1000000}

# Dump all storage
storage_snapshot = contract._storage.dump()
print(storage_snapshot)  # {'owner': '0x00...', 'balances': {...}, 'total_supply': 1000000}
```

### Immutables and Constants

```python
src = """
DECIMALS: public(immutable(uint8))
VERSION: public(constant(String[32])) = "1.0.0"

@deploy
def __init__(decimals: uint8):
    DECIMALS = decimals
"""
contract = boa.loads(src, 18)

# Access immutables
print(contract._immutables.DECIMALS)  # 18

# Access constants
print(contract._constants.VERSION)  # "1.0.0"
```

### Storage Slot Information

```python
# Get storage slot locations
print(contract._storage.owner.slot)  # 0
print(contract._storage.balances.slot)  # 1
print(contract._storage.total_supply.slot)  # 2
```

## Eval - Execute Arbitrary Vyper Code

The `eval` method allows execution of arbitrary Vyper expressions within a contract's context:

### Basic Usage

```python
contract = boa.loads("""
balance: uint256
locked: bool

@external
def deposit(amount: uint256):
    self.balance += amount
""")

# Execute Vyper code in contract context
contract.eval("self.balance = 1000")
assert contract.eval("self.balance") == 1000

# Complex expressions
result = contract.eval("self.balance * 2 + 100")
assert result == 2100
```

### Accessing Internal Functions

```python
contract = boa.loads("""
@internal
def _calculate_fee(amount: uint256) -> uint256:
    return amount * 3 // 100

@internal
def _is_valid_amount(amount: uint256) -> bool:
    return amount > 0 and amount <= 10**18
""")

# Call internal functions through eval
fee = contract.eval("self._calculate_fee(1000)")
assert fee == 30

is_valid = contract.eval("self._is_valid_amount(500)")
assert is_valid == True
```

### Debugging with Eval

```python
# Complex contract state debugging
contract = boa.loads("""
struct Position:
    amount: uint256
    entry_price: uint256
    
positions: HashMap[address, Position]
total_positions: uint256

@external
def open_position(amount: uint256, price: uint256):
    self.positions[msg.sender] = Position(amount=amount, entry_price=price)
    self.total_positions += 1
""")

# Open a position
contract.open_position(1000, 50000)

# Debug using eval
position = contract.eval("self.positions[msg.sender]")
print(f"Position: amount={position[0]}, price={position[1]}")

# Check multiple conditions
is_profitable = contract.eval("""
self.positions[msg.sender].amount > 0 and self.positions[msg.sender].entry_price < 60000
""")
```

## Contract Creation Tracking

Track contract deployment relationships:

```python
# Deploy a factory contract
factory_src = """
@external
def deploy_child() -> address:
    return create_minimal_proxy_to(self)
"""
factory = boa.loads(factory_src)

# Deploy child contract
child_address = factory.deploy_child()
child = boa.loads_partial(child_src).at(child_address)

# Track creation relationship
print(child.created_from)  # Factory contract address
```

## Advanced State Management

### Open Context Manager Pattern

Titanoboa uses a special "open" pattern that allows functions to work both as regular calls and context managers:

```python
import boa

# As a regular call - changes persist
new_env = boa.Env()
boa.set_env(new_env)
# Environment is now changed permanently

# As a context manager - changes revert
original_env = boa.env
with boa.set_env(boa.Env()):
    # Temporary environment
    assert boa.env != original_env
# Environment reverts to original
assert boa.env == original_env
```

### Nested Anchoring

```python
contract = boa.loads("""
value: uint256
checkpoint: uint256
""")

# Nested state management
with boa.env.anchor():
    contract.eval("self.value = 100")
    
    with boa.env.anchor():
        contract.eval("self.value = 200")
        contract.eval("self.checkpoint = self.value")
        assert contract.eval("self.checkpoint") == 200
    
    # Inner anchor reverted
    assert contract.eval("self.value") == 100
    assert contract.eval("self.checkpoint") == 0

# Outer anchor reverted
assert contract.eval("self.value") == 0
```

## Advanced Account Management

### Multiple Account Handling

```python
# Generate multiple accounts with aliases
accounts = {}
for i in range(5):
    addr = boa.env.generate_address(alias=f"user_{i}")
    accounts[f"user_{i}"] = addr
    boa.env.set_balance(addr, 10**18)  # 1 ETH each

# Use aliases in testing
contract = boa.loads("""
deposits: public(HashMap[address, uint256])

@external
@payable
def deposit():
    self.deposits[msg.sender] = msg.value
""")

# Test with different accounts
for alias, addr in accounts.items():
    with boa.env.prank(addr):
        contract.deposit(value=10**17)  # 0.1 ETH
        assert contract.deposits(addr) == 10**17
```

### Account Context Stacking

```python
original = boa.env.eoa
user1 = boa.env.generate_address("user1")
user2 = boa.env.generate_address("user2")

with boa.env.prank(user1):
    assert boa.env.eoa == user1
    
    with boa.env.prank(user2):
        assert boa.env.eoa == user2
    
    assert boa.env.eoa == user1

assert boa.env.eoa == original
```

## Direct Storage Manipulation

For advanced testing scenarios, you can directly manipulate storage:

```python
contract = boa.loads("""
private_value: uint256
magic_number: constant(uint256) = 0x1234567890ABCDEF

@external
def get_private() -> uint256:
    return self.private_value
""")

# Direct storage access
boa.env.set_storage(
    contract.address,
    0,  # slot 0
    42  # value
)

assert contract.get_private() == 42

# Manipulate mappings
token = boa.loads("""
balances: HashMap[address, uint256]
""")

# Calculate mapping slot
# slot = keccak256(address + slot_number)
user = boa.env.generate_address()
slot = boa.env.eval(f"keccak256(concat({user}, uint256(0)))")
boa.env.set_storage(token.address, slot, 1000)
```

## Debugging Features

### Source Mapping

```python
contract = boa.loads("""
@external
def complex_function(x: uint256) -> uint256:
    if x > 100:
        return x * 2
    else:
        return x + 50
""")

# Trace execution with source mapping
try:
    with boa.env.anchor():
        result = contract.complex_function(150)
        # Source maps track which lines were executed
except Exception as e:
    # Stack traces include Vyper source lines
    print(contract.stack_trace(e))
```

### Call Traces

```python
# Enable call tracing
contract_a = boa.loads("""
interface B:
    def callback(value: uint256): nonpayable

@external
def call_b(b_address: address, value: uint256):
    B(b_address).callback(value)
""")

contract_b = boa.loads("""
event CallbackReceived:
    value: uint256

@external
def callback(value: uint256):
    log CallbackReceived(value)
""")

# Trace the call
contract_a.call_b(contract_b.address, 123)

# Access call trace information
# (This is automatically captured during execution)
```

## Integration Features

### Module System Hooks

#### Custom Search Paths

Titanoboa allows you to configure custom search paths for Vyper imports and module resolution. This is useful when working with contracts that have dependencies in different directories.

```python
import boa
from boa.interpret import set_search_path

# Set custom search paths for module resolution
set_search_path([
    "/path/to/contracts",
    "/path/to/interfaces",
    "/path/to/libraries"
])

# Now contracts can import from these directories
contract = boa.load("MyContract.vy")  # Can import modules from search paths
```

The search path resolution order (from highest to lowest precedence):
1. Paths specified via `set_search_path()` (last path has highest precedence)
2. Current directory (".")
3. Python's `sys.path` (in reverse order)

Example with imports:
```python
# Directory structure:
# /projects/
#   ├── interfaces/
#   │   └── IERC20.vyi
#   ├── libraries/
#   │   └── math.vy
#   └── contracts/
#       └── Token.vy

# Token.vy contains:
# import interfaces.IERC20 as IERC20
# import libraries.math as math

# Set up search paths
set_search_path(["/projects"])

# Load contract - imports will be resolved
token = boa.load("/projects/contracts/Token.vy")
```

#### Python Import System Integration

Titanoboa automatically integrates with Python's import system for `.vy` files:

```python
# After setting search paths, you can import Vyper files directly
set_search_path(["/path/to/vyper/contracts"])

# Import as Python modules (loads the contract)
import mytoken  # Loads /path/to/vyper/contracts/mytoken.vy
import protocols.lending.vault  # Loads /path/to/vyper/contracts/protocols/lending/vault.vy

# Use the imported contracts
token_contract = mytoken.deploy()
```

### Compiler Control

```python
# Fine control over compilation
contract = boa.loads(
    source_code,
    # Force specific compiler version
    compiler_args={"optimize": "codesize"},
    # Skip VVM, use local compiler
    no_vvm=True
)

# Or with VVM for specific version
contract = boa.loads(
    f"# @version {vyper_version}\n{source_code}"
)
```

## Testing Helpers

### Coverage Integration

```python
# Enable coverage tracking
import boa
boa.env._coverage_enabled = True

# Run your tests
contract = boa.loads("MyContract.vy")
contract.function()

# Coverage data is automatically collected
# Use with coverage.py for reports
```

### Hypothesis Integration

The Titanoboa pytest plugin automatically handles state isolation for Hypothesis:

```python
from hypothesis import given, strategies as st

@given(value=st.integers(min_value=0, max_value=10**18))
def test_property(value):
    contract = boa.loads("""
    total: uint256
    
    @external
    def add(amount: uint256):
        self.total += amount
    """)
    
    contract.add(value)
    assert contract.eval("self.total") == value
    # State automatically isolated between examples
```

## Network Mode Advanced Features

### Fork State Management

```python
# Fork from mainnet
boa.fork("https://eth.llamarpc.com")

# Access forked state
usdc = boa.from_etherscan("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")

# Modify forked state
whale = "0x47ac0Fb4F2D84898e4D9E7b4DaB3C24507a6D503"
boa.env.set_balance(whale, 10**20)  # Give whale 100 ETH

# State persists in fork
with boa.env.prank(whale):
    # Whale can now make transactions
    usdc.transfer(user, 1000 * 10**6)
```

### Custom Transaction Settings

```python
# Detailed transaction control
boa.env.tx_settings.poll_timeout = 300.0  # 5 minute timeout
boa.env.tx_settings.base_fee_estimator_constant = 10  # Estimate base fee 10 blocks ahead

# Execute with custom settings
contract.expensive_operation()
```

## Best Practices

1. **Use introspection for debugging, not production logic**
   ```python
   # Good: Debugging in tests
   assert contract._storage.balance == expected
   
   # Bad: Relying on internals in production tests
   if contract._storage.balance > 0:  # Don't do this
       contract.withdraw()
   ```

2. **Combine features for powerful testing**
   ```python
   # Combine eval, anchoring, and introspection
   with boa.env.anchor():
       # Manipulate internal state
       contract.eval("self.internal_flag = True")
       
       # Test behavior with modified state
       result = contract.public_function()
       
       # Verify using introspection
       assert contract._storage.internal_flag == True
   ```

3. **Document advanced usage**
   ```python
   def test_complex_scenario():
       """
       This test uses eval() to set up complex internal state
       that would be difficult to achieve through public methods.
       """
       contract.eval("self.positions[msg.sender].locked = True")
       # Test behavior with locked position
   ```
