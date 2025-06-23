# Address

### Description

The `Address` class represents an Ethereum address in Titanoboa. It provides a type-safe wrapper around address values with built-in validation and utility methods.

---

## Creating Addresses

```python
import boa
from boa import Address

# From hex string
addr1 = Address("0x0000000000000000000000000000000000000001")

# From checksum address
addr2 = Address("0x5B38Da6a701c568545dCfcB03FcB875f56beddC4")

# From bytes
addr3 = Address(b"\x00" * 20)

# From integer
addr4 = Address(1)

# Generate new address
addr5 = boa.env.generate_address()
```

---

## Properties and Methods

### `canonical_address`

Returns the address as a 20-byte bytes object.

```python
addr = Address("0x0000000000000000000000000000000000000001")
print(addr.canonical_address)  # b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01'
```

### String Representation

The Address class inherits from `str` and provides checksum address representation:

```python
addr = Address("0x5B38Da6a701c568545dCfcB03FcB875f56beddC4")

# Checksum address (default string representation)
print(str(addr))  # 0x5B38Da6a701c568545dCfcB03FcB875f56beddC4

# Lowercase hex
print(str(addr).lower())  # 0x5b38da6a701c568545dcfcb03fcb875f56beddc4
```

---

## Type Checking

Address objects can be compared and used in type checks:

```python
addr1 = Address("0x0000000000000000000000000000000000000001")
addr2 = Address(1)
addr3 = Address("0x0000000000000000000000000000000000000002")

# Equality
assert addr1 == addr2
assert addr1 != addr3

# Type checking
assert isinstance(addr1, Address)
```

---

## Integration with Contracts

Address objects are automatically used when interacting with contracts:

```python
contract = boa.loads("""
balances: public(HashMap[address, uint256])

@external
def set_balance(account: address, amount: uint256):
    self.balances[account] = amount
""")

# Address objects work seamlessly
user = boa.env.generate_address()
contract.set_balance(user, 1000)

# Hex strings are automatically converted
contract.set_balance("0x0000000000000000000000000000000000000001", 500)
```

---

## Special Addresses

Commonly used special addresses:

```python
# Zero address
ZERO_ADDRESS = Address("0x0000000000000000000000000000000000000000")

# Common precompiles
ECRECOVER = Address("0x0000000000000000000000000000000000000001")
SHA256 = Address("0x0000000000000000000000000000000000000002")
RIPEMD160 = Address("0x0000000000000000000000000000000000000003")
IDENTITY = Address("0x0000000000000000000000000000000000000004")
MODEXP = Address("0x0000000000000000000000000000000000000005")
```

---

## Aliasing

Titanoboa supports address aliasing for better test readability:

```python
# Generate address with alias
alice = boa.env.generate_address(alias="alice")
bob = boa.env.generate_address(alias="bob")

# Use in tests
with boa.env.prank(alice):
    contract.transfer(bob, 100)

# The alias appears in error messages and logs
# e.g., "alice (0x1234...)" instead of just "0x1234..."
```

---

## Address Validation

The Address class validates input on construction:

```python
# Valid addresses
Address("0x5B38Da6a701c568545dCfcB03FcB875f56beddC4")  # OK
Address("0x" + "00" * 20)  # OK
Address(12345)  # OK - converts integer to address

# Invalid addresses raise ValueError
try:
    Address("0x123")  # Too short
except ValueError as e:
    print(f"Invalid: {e}")

try:
    Address("not_an_address")  # Invalid format
except ValueError as e:
    print(f"Invalid: {e}")
```

---

## Working with Storage

When accessing storage directly, addresses are used as keys:

```python
contract = boa.loads("""
owner: public(address)
admins: public(HashMap[address, bool])
""")

# Set owner
owner_addr = boa.env.generate_address(alias="owner")
contract.eval(f"self.owner = {owner_addr}")

# Access storage
print(contract._storage.owner)  # Returns Address object
print(contract._storage.admins)  # Returns dict with Address keys
```

---

## See Also

- [Environment - generate_address](../env/env.md#generate_address) - Generate new addresses
- [Common Classes - VyperContract](../common_classes/_BaseVyperContract.md) - Using addresses with contracts
- [Testing - prank](../testing.md#prank) - Impersonate addresses in tests
