# `eval`

### Signature

```python
eval(statement: str, value: int = 0, gas: int | None = None, sender: str | None = None) -> Any
```

### Description

Evaluate a Vyper statement in the context of the contract.

- `statement`: A vyper statement.
- `value`: The ether value to attach to the statement evaluation (a.k.a `msg.value`).
- `gas`: The gas limit provided for statement evaluation (a.k.a. `msg.gas`).
- `sender`: The account which will be the `tx.origin`, and `msg.sender` in the context of the evaluation.
- Returns: The result of the statement evaluation.

### Examples

#### Basic State Modification

```python
>>> import boa
>>> src = "value: public(uint256)"
>>> contract = boa.loads(src)
>>> contract.value()
0
>>> contract.eval("self.value += 1")
>>> contract.value()
1
```

#### Evaluating Expressions

```python
>>> import boa
>>> src = """
... balance: public(uint256)
... total_supply: public(uint256)
... 
... @deploy
... def __init__():
...     self.balance = 1000
...     self.total_supply = 10000
... """
>>> contract = boa.loads(src)
>>> 
>>> # Evaluate complex expressions
>>> result = contract.eval("self.balance * 100 // self.total_supply")
>>> result
10
>>> 
>>> # Access msg context
>>> sender_address = contract.eval("msg.sender")
>>> sender_address
'0x0000000000000000000000000000000000000065'
```

#### Working with Mappings and Arrays

```python
>>> import boa
>>> src = """
... balances: HashMap[address, uint256]
... owners: DynArray[address, 10]
... 
... @external
... def setup():
...     self.balances[msg.sender] = 1000
...     self.owners.append(msg.sender)
... """
>>> contract = boa.loads(src)
>>> contract.setup()
>>> 
>>> # Check mapping values
>>> user = boa.env.eoa
>>> balance = contract.eval(f"self.balances[{user}]")
>>> balance
1000
>>> 
>>> # Modify arrays
>>> contract.eval("self.owners.append(0x0000000000000000000000000000000000000123)")
>>> length = contract.eval("len(self.owners)")
>>> length
2
```

#### Advanced Usage with Internal Functions

```python
>>> import boa
>>> src = """
... total: uint256
... 
... @internal
... def _calculate_fee(amount: uint256) -> uint256:
...     return amount * 3 // 100
... 
... @internal
... def _apply_fee(amount: uint256) -> uint256:
...     fee: uint256 = self._calculate_fee(amount)
...     return amount - fee
... """
>>> contract = boa.loads(src)
>>> 
>>> # Call internal functions through eval
>>> fee = contract.eval("self._calculate_fee(1000)")
>>> fee
30
>>> 
>>> # Use internal functions in complex expressions
>>> net_amount = contract.eval("self._apply_fee(1000)")
>>> net_amount
970
```

#### Debugging with eval

```python
>>> import boa
>>> # Complex contract with potential issues
>>> src = """
... struct Position:
...     amount: uint256
...     entry_time: uint256
...     
... positions: HashMap[address, Position]
... 
... @external
... def open_position(amount: uint256):
...     self.positions[msg.sender] = Position(amount=amount, entry_time=block.timestamp)
... """
>>> contract = boa.loads(src)
>>> contract.open_position(5000)
>>> 
>>> # Debug: check position details
>>> position = contract.eval("self.positions[msg.sender]")
>>> position
(5000, 1234567890)  # Returns tuple of struct values
>>> 
>>> # Debug: check specific struct field
>>> amount = contract.eval("self.positions[msg.sender].amount")
>>> amount
5000
```

### Notes

- The `eval` method compiles the provided Vyper code in the contract's context, giving access to all storage variables and internal functions
- Expressions are evaluated with the same permissions as external calls (can't access private functions)
- The code is executed in a transaction context, so state changes are possible
- Complex Vyper expressions including loops, conditions, and function calls are supported
- Useful for debugging, testing internal logic, and performing complex state queries
