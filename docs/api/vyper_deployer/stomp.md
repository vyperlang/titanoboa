# `stomp`

### Signature

```python
stomp(address: Any, data_section=None) -> VyperContract
```

### Description

Replaces the bytecode at a given address with the contract's runtime bytecode.

- `address`: The address where the contract is deployed.
- `data_section`: Optional data section to append to the bytecode.
- Returns: A `VyperContract` instance.

### Examples

```python
>>> import boa
>>> src = """
... @external
... def main():
...     pass
... """
>>> deployer = boa.loads_partial(src, "Foo")
>>> contract = deployer.deploy()
>>> contract.stomp(contract.address)
```
