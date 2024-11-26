# `standard_json`

### Property

```python
@property
standard_json: dict
```

### Description

Generates a standard JSON representation of the Vyper contract.

- Returns: A dictionary representing the standard JSON output.

### Examples

```python
>>> import boa
>>> src = """
... @external
... def main():
...     pass
... """
>>> deployer = boa.loads_partial(src, "Foo")
>>> deployer.standard_json
{'contracts': {'Foo': {'abi': [...], 'bin': '...'}}}
```