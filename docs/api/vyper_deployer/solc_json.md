# `solc_json`

### Property

```python
@cached_property
solc_json: dict
```

### Description

Generates a solc "standard JSON" representation of the Vyper contract.

- Returns: A dictionary representing the solc standard JSON input for the contract.

### Examples

```python
>>> import boa
>>> src = """
... @external
... def main():
...     pass
... """
>>> deployer = boa.loads_partial(src, name="Foo")
>>> deployer.solc_json
{'language': 'Vyper', 'sources': {...}, 'settings': {...}, ...}
```
