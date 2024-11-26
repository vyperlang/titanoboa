# `VyperInternalFunction`

### Description

Internal contract functions are exposed by wrapping them with a dummy external contract function, appending the wrapper's AST at the top of the contract, and then generating bytecode to run internal methods (as external methods). Therefore, they share the same API as `VyperFunction`. Internal functions can be accessed using the `internal` namespace of a `VyperContract`.

### Examples

```python
>>> import boa
>>> src = """
... @internal
... def main(a: uint256) -> uint256:
...     return 1 + a
... """
>>> contract = boa.loads(src)
>>> contract.internal.main(68)
69
```
