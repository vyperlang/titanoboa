# Fuzzing Strategies

Titanoboa offers custom [Hypothesis](https://hypothesis.readthedocs.io/) strategies for testing. These generate EVM-compliant random inputs from canonical ABI type strings.

For the compact API reference, see [`boa.fuzz` / `strategy`](../../api/fuzz.md).

## Overview

Fuzzing (property-based testing) helps find edge cases by automatically generating test inputs. Titanoboa provides a single entry point, `strategy(type_string, **kwargs)`, that builds Hypothesis strategies for Ethereum/Vyper ABI types so your tests receive properly formatted data.

Import it from `boa.test`:

```python
from hypothesis import given

from boa.test import strategy
```

You can also import the module and call `strategies.strategy(...)`:

```python
import boa.test.strategies as strategies

strategies.strategy("uint256")
```

## Available Strategies

### Address Strategy

Generate checksummed Ethereum addresses. By default the strategy draws from deployed contract addresses in the current environment (when any exist) and from random accounts:

```python
@given(addr=strategy("address"))
def test_transfer(addr):
    contract = boa.loads("""
@external
def transfer(to: address, amount: uint256):
    pass
""")
    contract.transfer(addr, 100)
```

Optional kwargs:

- `env` — environment to sample known contract addresses from (defaults to `boa.env`)
- `exclude` — a value, iterable, or callable used to reject generated addresses

```python
ZERO = "0x0000000000000000000000000000000000000000"

@given(addr=strategy("address", exclude=ZERO))
def test_non_zero_address(addr):
    assert addr != ZERO
```

### Integer Strategies

Generate integers within the bounds of a given ABI integer type. Any `uintN` / `intN` size supported by the ABI grammar works (`uint8` … `uint256`, `int8` … `int256`):

```python
# Unsigned integers
@given(value=strategy("uint256"))
def test_uint256(value):
    assert 0 <= value <= 2**256 - 1

@given(value=strategy("uint128"))
def test_uint128(value):
    assert 0 <= value <= 2**128 - 1

# Signed integers
@given(value=strategy("int128"))
def test_int128(value):
    assert -(2**127) <= value <= 2**127 - 1
```

Optional kwargs:

- `min_value` / `max_value` — tighten the range (must stay inside the type bounds)
- `exclude` — a value, iterable, or callable used to reject generated integers

```python
@given(amount=strategy("uint256", min_value=1, max_value=10**21))
def test_realistic_amount(amount):
    assert 1 <= amount <= 10**21
```

### Bytes Strategies

Generate fixed-length or dynamic bytes:

```python
@given(data=strategy("bytes32"))
def test_hash(data):
    contract = boa.loads("""
hash: public(bytes32)

@external
def store_hash(data: bytes32):
    self.hash = data
""")
    contract.store_hash(data)


# Variable-length bytes
@given(data=strategy("bytes", min_size=1, max_size=1024))
def test_variable_bytes(data):
    assert 1 <= len(data) <= 1024
```

Notes:

- Fixed-length types (`bytes1` … `bytes32`) always generate exactly that many bytes. Passing `min_size` / `max_size` raises `TypeError`.
- Dynamic `bytes` defaults to `min_size=1` and `max_size=64`. Override those kwargs to allow empty bytes or larger payloads.
- `exclude` is supported.

### Boolean Strategy

```python
@given(flag=strategy("bool"))
def test_toggle(flag):
    contract = boa.loads("""
flag: public(bool)

@external
def set_flag(value: bool):
    self.flag = value
""")
    contract.set_flag(flag)
    assert contract.flag() == flag
```

### Decimal Strategy

Generate fixed-point decimals. The type string `"decimal"` is translated to ABI `fixed168x10` (Vyper's decimal representation):

```python
from decimal import Decimal

@given(price=strategy("decimal"))
def test_pricing(price):
    contract = boa.loads("""
@external
def calculate_fee(amount: decimal) -> decimal:
    return amount * 0.03
""")
    if price >= 0:
        fee = contract.calculate_fee(price)
        assert fee == price * Decimal("0.03")
```

Optional kwargs:

- `min_value` / `max_value` — numeric bounds (checked against `int128` limits)
- `places` — decimal places (default `10`)
- `exclude`

### String Strategy

Generate Unicode strings within size limits (defaults: `min_size=0`, `max_size=64`):

```python
@given(name=strategy("string", max_size=32))
def test_naming(name):
    contract = boa.loads("""
name: public(String[32])

@external
def set_name(new_name: String[32]):
    self.name = new_name
""")
    contract.set_name(name)
    assert contract.name() == name
```

Additional kwargs are forwarded to Hypothesis `st.text` (for example `alphabet`). `exclude` is supported.

### Array Strategies

Generate fixed and dynamic arrays using ABI array type strings:

```python
# Fixed array
@given(values=strategy("uint256[5]"))
def test_fixed_array(values):
    assert len(values) == 5
    for v in values:
        assert 0 <= v <= 2**256 - 1


# Dynamic array
@given(values=strategy("address[]", min_length=0, max_length=100))
def test_dynamic_array(values):
    assert len(values) <= 100
    contract = boa.loads("""
@external
def process_addresses(addresses: DynArray[address, 100]):
    pass
""")
    contract.process_addresses(values)
```

Optional kwargs for dynamic dimensions:

- `min_length` / `max_length` — defaults are `1` and `8` when the dimension is dynamic
- For nested dynamic arrays, pass a list with one entry per dynamic dimension
- `unique` — require unique elements
- Element-type kwargs (such as `min_value` for integer elements) are forwarded inward

```python
@given(matrix=strategy("uint8[][]", min_length=[2, 2], max_length=[4, 4]))
def test_nested_dynamic(matrix):
    assert 2 <= len(matrix) <= 4
    assert all(2 <= len(row) <= 4 for row in matrix)
```

### Tuple Strategy

Generate tuples for struct-like / multi-value data using ABI tuple notation:

```python
@given(position=strategy("(uint256,uint256,bool)"))
def test_position(position):
    amount, price, is_long = position
    contract = boa.loads("""
@external
def open_position(amount: uint256, price: uint256, is_long: bool):
    pass
""")
    contract.open_position(amount, price, is_long)
```

## `@boa.fuzz`

`@boa.fuzz` inspects a deployed Vyper function and builds a `strategy(...)` for each argument from its canonical ABI type:

```python
import boa

contract = boa.loads("""
@external
def identity(item: uint256) -> uint256:
    return item
""")


@boa.fuzz(contract.identity)
def check_identity(item):
    assert contract.identity(item) == item


check_identity()
```

Important details:

- The decorated function is a Hypothesis test and **must be called** (or collected by pytest).
- A strategy is generated for every argument in the Vyper signature, including arguments that have default values.
- Use `strategy()` with `@given` when you need custom ranges or sizes that `@boa.fuzz` does not expose.

```python
from hypothesis import given, settings

from boa.test import strategy


@settings(max_examples=200, deadline=None)
@given(amount=strategy("uint256", min_value=1, max_value=10**21))
def test_deposit(vault, amount):
    vault.deposit(value=amount)
    assert vault.totalAssets() == amount
```

## Advanced Usage

### Composite Strategies

Combine Titanoboa strategies with Hypothesis helpers:

```python
import boa
from hypothesis import given
from hypothesis import strategies as st

from boa.test import strategy

transfer_strategy = st.tuples(
    strategy("address"),  # sender
    strategy("address"),  # recipient
    strategy("uint256", min_value=1, max_value=10**20 - 1),  # amount
)


@given(transfer_data=transfer_strategy)
def test_token_transfer(token_contract, transfer_data):
    sender, recipient, amount = transfer_data

    boa.env.set_balance(sender, 10**18)
    token_contract.mint(sender, amount * 2)

    with boa.env.prank(sender):
        token_contract.transfer(recipient, amount)

    assert token_contract.balanceOf(recipient) == amount
```

### Stateful Testing

Use Hypothesis stateful testing for complex protocols:

```python
import boa
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from boa.test import strategy


class TokenStateMachine(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.token = boa.load("Token.vy")
        self.balances = {}
        self.total_supply = 0

    @rule(
        account=strategy("address"),
        amount=strategy("uint256", max_value=10**20 - 1),
    )
    def mint(self, account, amount):
        self.token.mint(account, amount)
        self.balances[account] = self.balances.get(account, 0) + amount
        self.total_supply += amount

    @rule(
        sender=strategy("address"),
        recipient=strategy("address"),
        amount=strategy("uint256"),
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


TestTokenStateMachine = TokenStateMachine.TestCase
```

### Filtering Strategies

Prefer built-in bounds/`exclude` when possible; use `.filter(...)` for arbitrary predicates:

```python
ZERO = "0x0000000000000000000000000000000000000000"

# Built-in bounds
@given(amount=strategy("uint256", min_value=1))
def test_deposit(amount):
    contract.deposit(value=amount)


# Built-in exclude
@given(addr=strategy("address", exclude=ZERO))
def test_set_owner(addr):
    contract.set_owner(addr)


# Hypothesis filter for custom predicates
@given(amount=strategy("uint256").filter(lambda x: 10**16 <= x <= 10**21))
def test_realistic_transfer(amount):
    contract.transfer(recipient, amount)
```

## Integration with Pytest

Titanoboa installs a pytest plugin that is discovered automatically. The plugin anchors the environment around tests and fixtures, and patches Hypothesis so each generated example also runs inside an anchor. That prevents state written by one example from leaking into the next.

If pytest plugin autoloading is disabled, register it explicitly:

```python
# conftest.py
pytest_plugins = ["boa.test.plugin"]
```

Example test:

```python
from hypothesis import given

from boa.test import strategy


@given(
    initial_supply=strategy("uint256", max_value=10**24 - 1),
    transfer_amount=strategy("uint256"),
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

Normal Hypothesis strategies and state-machine tests can be mixed with `boa.test.strategy`.

## Best Practices

1. **Use bounds for realistic values**:
   ```python
   # Good: realistic gas prices
   gas_price = strategy("uint256", min_value=10**9, max_value=10**11)

   # Broad: any uint256 (includes unrealistic values)
   gas_price = strategy("uint256")
   ```

2. **Combine with regular tests**:
   ```python
   def test_zero_transfer():
       with boa.reverts("Cannot transfer 0"):
           contract.transfer(recipient, 0)

   @given(amount=strategy("uint256", min_value=1))
   def test_transfer_properties(amount):
       # Invariants that should hold for all valid amounts
       pass
   ```

3. **Set reasonable test budgets**:
   ```python
   from hypothesis import given, settings

   from boa.test import strategy


   @settings(max_examples=1000, deadline=None)
   @given(value=strategy("uint256"))
   def test_expensive_operation(value):
       contract.expensive_operation(value)
   ```

4. **Use stateful testing for protocols**:
   - Model your protocol as a state machine
   - Define rules for state transitions
   - Check invariants after each operation
   - Let Hypothesis find breaking sequences

## Common Patterns

### Testing Numerical Boundaries

```python
import boa
from hypothesis import given

from boa.test import strategy


@given(value=strategy("uint256"))
def test_overflow_protection(value):
    contract = boa.loads("""
total_supply: public(uint256)
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
import boa
from hypothesis import given

from boa.test import strategy


@given(
    caller=strategy("address"),
    authorized=strategy("address"),
)
def test_access_control(caller, authorized):
    contract = boa.loads(
        """
owner: public(address)

@deploy
def __init__(owner: address):
    self.owner = owner

@external
def restricted_function():
    assert msg.sender == self.owner, "Not authorized"
""",
        authorized,
    )

    with boa.env.prank(caller):
        if caller == authorized:
            contract.restricted_function()
        else:
            with boa.reverts("Not authorized"):
                contract.restricted_function()
```

## See Also

- [Fuzzing API](../../api/fuzz.md)
- [Hypothesis documentation](https://hypothesis.readthedocs.io/)
- [Gas profiling](gas_profiling.md)
- [Testing API](../../api/testing.md)
