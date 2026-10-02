# `inject_function`

### Signature

```python
inject_function(fn_source_code, force=False)
```

### Description

Injects a function into the contract without affecting the contract's source code. Useful for testing private functionality.

- `fn_source_code`: The source code of an `@external` function to inject.
  It can access the original contract's storage and internal functions.
- `force`: Whether to force the injection if a function with the same name already exists.
- Returns: None. Call injected functions through `contract.inject.<name>()`.
  `contract.internal` exposes internal functions from the original source.

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
>>> contract.inject_function("""
... @external
... def injected_function() -> uint256:
...     return 42
... """)
>>> contract.inject.injected_function()
42
```
