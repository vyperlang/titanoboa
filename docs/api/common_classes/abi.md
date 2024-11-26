# `abi`

### Property

```python
@property
abi: dict
```

### Description

Returns the ABI (Application Binary Interface) of the Vyper contract.

- Returns: A dictionary representing the ABI of the contract.

### Examples

```python
>>> import boa
>>> src = """
... @external
... def main():
...     pass
... """
>>> deployer = boa.loads_partial(src, name="Foo")
>>> contract = deployer.deploy()
>>> contract_abi = contract.abi
>>> type(contract_abi)
<class 'dict'>
```
