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