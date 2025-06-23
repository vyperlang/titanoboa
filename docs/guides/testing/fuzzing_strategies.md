# Fuzzing Strategies

Titanoboa offers custom [hypothesis](https://hypothesis.readthedocs.io/en/latest/quickstart.html) strategies for testing. These can be used to generate EVM-compliant random inputs for tests.

## Overview

Fuzzing (property-based testing) helps find edge cases by automatically generating test inputs. Titanoboa provides strategies that generate valid Ethereum/Vyper types, ensuring your tests receive properly formatted data.

## Available Strategies

Import strategies from `boa.test.strategies`:

```python
from boa.test import strategies as boa_st
from hypothesis import given
```

### Address Strategy

Generate valid Ethereum addresses:

```python
@given(addr=boa_st.address())
def test_transfer(addr):
    contract = boa.load("""
@external
def transfer(to: address, amount: uint256):
    # Implementation
    pass
""")
    contract.transfer(addr, 100)
```

### Integer Strategies

Generate integers within Vyper bounds:

```python
# Unsigned integers
@given(value=boa_st.uint256())
def test_uint256(value):
    assert 0 <= value <= 2**256 - 1

@given(value=boa_st.uint128())
def test_uint128(value):
    assert 0 <= value <= 2**128 - 1

# Signed integers
@given(value=boa_st.int128())
def test_int128(value):
    assert -2**127 <= value <= 2**127 - 1
```

### Bytes Strategies

Generate bytes of specific lengths:

```python
@given(data=boa_st.bytes32())
def test_hash(data):
    contract = boa.load("""
@external
def store_hash(data: bytes32):
    self.hash = data
""")
    contract.store_hash(data)

# Variable-length bytes
@given(data=boa_st.bytes_(max_size=1024))
def test_variable_bytes(data):
    assert len(data) <= 1024
```

### Boolean Strategy

```python
@given(flag=boa_st.bool_())
def test_toggle(flag):
    contract = boa.load("""
flag: public(bool)

@external
def set_flag(value: bool):
    self.flag = value
""")
    contract.set_flag(flag)
    assert contract.flag() == flag
```

### Decimal Strategy

Generate fixed-point decimals:

```python
@given(price=boa_st.decimal())
def test_pricing(price):
    contract = boa.load("""
@external
def calculate_fee(amount: decimal) -> decimal:
    return amount * 0.03  # 3% fee
""")
    if price >= 0:
        fee = contract.calculate_fee(price)
        assert fee == price * decimal("0.03")
```

### String Strategy

Generate strings within Vyper limits:

```python
@given(name=boa_st.string(max_size=32))
def test_naming(name):
    contract = boa.load("""
name: public(String[32])

@external
def set_name(new_name: String[32]):
    self.name = new_name
""")
    contract.set_name(name)
    assert contract.name() == name
```

### Array Strategies

Generate fixed and dynamic arrays:

```python
# Fixed array
@given(values=boa_st.array(boa_st.uint256(), 5))
def test_fixed_array(values):
    assert len(values) == 5
    for v in values:
        assert 0 <= v <= 2**256 - 1

# Dynamic array
@given(values=boa_st.dynamic_array(boa_st.address(), max_size=100))
def test_dynamic_array(values):
    assert len(values) <= 100
    contract = boa.load("""
@external
def process_addresses(addresses: DynArray[address, 100]):
    for addr in addresses:
        # Process each address
        pass
""")
    contract.process_addresses(values)
```

### Tuple Strategy

Generate tuples for struct-like data:

```python
@given(position=boa_st.tuple_(boa_st.uint256(), boa_st.uint256(), boa_st.bool_()))
def test_position(position):
    amount, price, is_long = position
    contract = boa.load("""
struct Position:
    amount: uint256
    price: uint256
    is_long: bool

@external
def open_position(amount: uint256, price: uint256, is_long: bool):
    # Implementation
    pass
""")
    contract.open_position(amount, price, is_long)
```

## Advanced Usage

### Composite Strategies

Build complex test scenarios:

```python
from hypothesis import strategies as st

# Strategy for token transfer test
transfer_strategy = st.tuples(
    boa_st.address(),  # sender
    boa_st.address(),  # recipient
    boa_st.uint256().filter(lambda x: x > 0 and x < 10**20)  # amount
)

@given(transfer_data=transfer_strategy)
def test_token_transfer(token_contract, transfer_data):
    sender, recipient, amount = transfer_data

    # Setup sender balance
    boa.env.set_balance(sender, 10**18)
    token_contract.mint(sender, amount * 2)

    # Test transfer
    with boa.env.prank(sender):
        token_contract.transfer(recipient, amount)

    assert token_contract.balanceOf(recipient) == amount
```

### Stateful Testing

Use hypothesis stateful testing for complex protocols:

```python
from hypothesis.stateful import RuleBasedStateMachine, rule, invariant

class TokenStateMachine(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.token = boa.load("Token.vy")
        self.balances = {}
        self.total_supply = 0

    @rule(
        account=boa_st.address(),
        amount=boa_st.uint256().filter(lambda x: x < 10**20)
    )
    def mint(self, account, amount):
        self.token.mint(account, amount)
        self.balances[account] = self.balances.get(account, 0) + amount
        self.total_supply += amount

    @rule(
        sender=boa_st.address(),
        recipient=boa_st.address(),
        amount=boa_st.uint256()
    )
    def transfer(self, sender, recipient, amount):
        if self.balances.get(sender, 0) >= amount:
            with boa.env.prank(sender):
                self.token.transfer(recipient, amount)
            self.balances[sender] -= amount
            self.balances[recipient] = self.balances.get(recipient, 0) + amount

    @invariant()
    def check_total_supply(self):
        assert self.token.totalSupply() == self.total_supply

    @invariant()
    def check_balances(self):
        for account, expected in self.balances.items():
            assert self.token.balanceOf(account) == expected

# Run the state machine test
TestTokenStateMachine = TokenStateMachine.TestCase
```

### Filtering Strategies

Add constraints to generated values:

```python
# Only positive amounts
@given(amount=boa_st.uint256().filter(lambda x: x > 0))
def test_deposit(amount):
    contract.deposit(value=amount)

# Addresses excluding zero address
@given(addr=boa_st.address().filter(lambda x: x != "0x0000000000000000000000000000000000000000"))
def test_set_owner(addr):
    contract.set_owner(addr)

# Realistic token amounts (0.01 to 1000 tokens with 18 decimals)
@given(amount=boa_st.uint256().filter(lambda x: 10**16 <= x <= 10**21))
def test_realistic_transfer(amount):
    contract.transfer(recipient, amount)
```

## Integration with Pytest

The Titanoboa pytest plugin automatically handles hypothesis test isolation:

```python
# conftest.py
pytest_plugins = ["boa.test"]

# test_token.py
@given(
    initial_supply=boa_st.uint256().filter(lambda x: x < 10**24),
    transfer_amount=boa_st.uint256()
)
def test_token_economics(initial_supply, transfer_amount):
    token = boa.load("Token.vy", initial_supply)

    if transfer_amount <= initial_supply:
        owner = boa.env.eoa
        recipient = boa.env.generate_address()

        token.transfer(recipient, transfer_amount)

        assert token.balanceOf(owner) == initial_supply - transfer_amount
        assert token.balanceOf(recipient) == transfer_amount
```

## Best Practices

1. **Use filters for realistic values**:
   ```python
   # Good: Realistic gas prices
   gas_price = boa_st.uint256().filter(lambda x: 10**9 <= x <= 10**11)

   # Bad: Any uint256 (includes unrealistic values)
   gas_price = boa_st.uint256()
   ```

2. **Combine with regular tests**:
   ```python
   # Specific edge cases
   def test_zero_transfer():
       with boa.reverts("Cannot transfer 0"):
           contract.transfer(recipient, 0)

   # Fuzzing for general properties
   @given(amount=boa_st.uint256().filter(lambda x: x > 0))
   def test_transfer_properties(amount):
       # Test invariants hold for all valid amounts
       pass
   ```

3. **Set reasonable test budgets**:
   ```python
   from hypothesis import settings

   @settings(max_examples=1000, deadline=None)
   @given(value=boa_st.uint256())
   def test_expensive_operation(value):
       # Limit examples for slow operations
       contract.expensive_operation(value)
   ```

4. **Use stateful testing for protocols**:
   - Model your protocol as a state machine
   - Define rules for state transitions
   - Check invariants after each operation
   - Let hypothesis find breaking sequences

## Common Patterns

### Testing Numerical Boundaries

```python
@given(value=boa_st.uint256())
def test_overflow_protection(value):
    contract = boa.load("""
MAX_SUPPLY: constant(uint256) = 10**24

@external
def mint(amount: uint256):
    assert self.total_supply + amount <= MAX_SUPPLY, "Exceeds max supply"
    self.total_supply += amount
""")

    if value <= 10**24:
        contract.mint(value)
    else:
        with boa.reverts("Exceeds max supply"):
            contract.mint(value)
```

### Testing Access Control

```python
@given(
    caller=boa_st.address(),
    authorized=boa_st.address()
)
def test_access_control(caller, authorized):
    contract = boa.load("""
owner: public(address)

@deploy
def __init__(owner: address):
    self.owner = owner

@external
def restricted_function():
    assert msg.sender == self.owner, "Not authorized"
""", authorized)

    with boa.env.prank(caller):
        if caller == authorized:
            contract.restricted_function()
        else:
            with boa.reverts("Not authorized"):
                contract.restricted_function()
```

## See Also

- [Hypothesis Documentation](https://hypothesis.readthedocs.io/)
- [Testing Guide](../testing/gas_profiling.md)
- [Test Module Reference](../../api/testing.md)
