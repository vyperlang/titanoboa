# `inject_function`

### Signature

```python
inject_function(fn_source_code, force=False)
```

### Description

Injects a function into the contract without affecting the contract's source code. Useful for testing private functionality.

- `fn_source_code`: The source code of the function to inject.
- `force`: Whether to force the injection if a function with the same name already exists.
- Returns: None.

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
... @internal
... def injected_function() -> uint256:
...     return 42
... """)
>>> contract.internal.injected_function()
42
```