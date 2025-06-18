# Storage Introspection

### Description

VyperContract provides powerful introspection capabilities for examining contract state through special properties that expose storage variables, immutables, and constants as Python objects.

---

## `_storage`

!!! property "`contract._storage`"

    **Description**

    Access storage variables as Python objects with automatic decoding. This property provides a view into all storage variables defined in the contract, including complex types like mappings and arrays.

    ---

    **Attributes**

    - Individual storage variables are accessible as attributes
    - `dump()`: Returns a dictionary of all storage variables and their values

    ---

    **Examples**

    ```python
    >>> import boa
    >>> src = """
    ... owner: public(address)
    ... balances: public(HashMap[address, uint256])
    ... total_supply: public(uint256)
    ... 
    ... @deploy
    ... def __init__():
    ...     self.owner = msg.sender
    ...     self.total_supply = 1000000
    ... """
    >>> contract = boa.loads(src)
    >>> 
    >>> # Access individual storage variables
    >>> contract._storage.owner
    '0x0000000000000000000000000000000000000065'
    >>> contract._storage.total_supply
    1000000
    >>> 
    >>> # Access mapping contents
    >>> contract._storage.balances
    {}  # Empty mapping
    >>> 
    >>> # Dump all storage variables
    >>> contract._storage.dump()
    {'owner': '0x0000000000000000000000000000000000000065', 'balances': {}, 'total_supply': 1000000}
    ```

    ---

    **Note**

    Storage variables are read directly from the EVM state and automatically decoded according to their Vyper types.

---

## `_immutables`

!!! property "`contract._immutables`"

    **Description**

    Access immutable variables defined in the contract. Immutables are set during deployment and cannot be changed.

    ---

    **Examples**

    ```python
    >>> import boa
    >>> src = """
    ... DECIMALS: public(immutable(uint8))
    ... INITIAL_SUPPLY: public(immutable(uint256))
    ... 
    ... @deploy
    ... def __init__(decimals: uint8, supply: uint256):
    ...     DECIMALS = decimals
    ...     INITIAL_SUPPLY = supply
    ... """
    >>> contract = boa.loads(src, 18, 1000000 * 10**18)
    >>> 
    >>> # Access immutable values
    >>> contract._immutables.DECIMALS
    18
    >>> contract._immutables.INITIAL_SUPPLY
    1000000000000000000000000
    ```

---

## `_constants`

!!! property "`contract._constants`"

    **Description**

    Access constant values defined in the contract. Constants are compile-time values that are embedded in the bytecode.

    ---

    **Examples**

    ```python
    >>> import boa
    >>> src = """
    ... VERSION: public(constant(String[32])) = "1.0.0"
    ... MAX_SUPPLY: public(constant(uint256)) = 10**9 * 10**18
    ... FEE_DENOMINATOR: public(constant(uint256)) = 10000
    ... """
    >>> contract = boa.loads(src)
    >>> 
    >>> # Access constants
    >>> contract._constants.VERSION
    '1.0.0'
    >>> contract._constants.MAX_SUPPLY
    1000000000000000000000000000
    >>> contract._constants.FEE_DENOMINATOR
    10000
    ```

---

## Advanced Usage

### Debugging Complex Storage

When debugging contracts with complex storage layouts, introspection can be invaluable:

```python
>>> import boa
>>> # Complex contract with nested structures
>>> src = """
... struct UserInfo:
...     balance: uint256
...     locked_until: uint256
...     rewards_claimed: bool
... 
... users: public(HashMap[address, UserInfo])
... user_list: public(DynArray[address, 1000])
... 
... @external
... def add_user(user: address, balance: uint256, lock_time: uint256):
...     self.users[user] = UserInfo(
...         balance=balance,
...         locked_until=block.timestamp + lock_time,
...         rewards_claimed=False
...     )
...     self.user_list.append(user)
... """
>>> contract = boa.loads(src)
>>> 
>>> # Add some users
>>> user1 = boa.env.generate_address()
>>> user2 = boa.env.generate_address()
>>> contract.add_user(user1, 1000, 86400)
>>> contract.add_user(user2, 2000, 172800)
>>> 
>>> # Inspect storage
>>> contract._storage.users
{
    '0x...': {'balance': 1000, 'locked_until': 1234567890, 'rewards_claimed': False},
    '0x...': {'balance': 2000, 'locked_until': 1234654290, 'rewards_claimed': False}
}
>>> 
>>> contract._storage.user_list
['0x...', '0x...']
>>> 
>>> # Get a complete snapshot
>>> snapshot = contract._storage.dump()
>>> print(snapshot)
{'users': {...}, 'user_list': [...]}
```

### Finding Storage Slots

For advanced use cases, you can find the actual storage slot of a variable:

```python
>>> import boa
>>> contract = boa.loads("""
... my_value: uint256
... my_mapping: HashMap[address, uint256]
... """)
>>> 
>>> # Storage variables have slot information
>>> contract._storage.my_value.slot
0
>>> contract._storage.my_mapping.slot
1
```

---

## See Also

- [eval](eval.md) - Execute arbitrary Vyper code in contract context
- [Common Classes - VyperContract](../common_classes/_BaseVyperContract.md) - Base contract functionality