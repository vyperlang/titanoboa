# `deregister_raw_precompile`

### Signature

```python
from boa.vm.py_evm import deregister_raw_precompile

deregister_raw_precompile(address: str, force: bool = True)
```

### Description

Remove a previously registered precompile.

**Note:** `deregister_precompile` has been renamed to `deregister_raw_precompile`. The old name is deprecated.

**Important:** This function is not available directly from the `boa` module. You must import it from `boa.vm.py_evm`.

- `address`: The address of a previously registered precompile.
- `force`: Whether to force removal of the precompile at the specified address.
- Raises `ValueError`: If a precompile is not registered at the specified address and the force argument is `False`.

### Examples

```python
>>> from boa.vm.py_evm import register_raw_precompile, deregister_raw_precompile
>>>
>>> # Register a precompile
>>> register_raw_precompile("0x00000000000000000000000000000000000000ff", lambda c: None)
>>>
>>> # Remove it
>>> deregister_raw_precompile("0x00000000000000000000000000000000000000ff")
```

### See Also

- [`register_raw_precompile`](./register_precompile.md) - Register a precompile function
