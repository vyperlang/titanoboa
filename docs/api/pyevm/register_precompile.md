# `register_raw_precompile`

### Signature

```python
from boa.vm.py_evm import register_raw_precompile

register_raw_precompile(address: str, fn: Callable[[eth.abc.ComputationAPI], None], force: bool = False)
```

### Description

Register a raw precompile function. This is the low-level interface for registering precompiles.

**Note:** `register_precompile` has been renamed to `register_raw_precompile`. The old name is deprecated.

**Important:** This function is not available directly from the `boa` module. You must import it from `boa.vm.py_evm`.

- `address`: The address to register the precompile at.
- `fn`: The function to execute when the precompile is called. Receives a ComputationAPI object.
- `force`: Whether to overwrite the precompile function if one is already registered at the specified address.
- Raises `ValueError`: If a precompile is already registered at the specified address and the force argument is `False`.

### Examples

```python
>>> from boa.vm.py_evm import register_raw_precompile
>>> import boa
>>>
>>> log = lambda computation: print("0x" + computation.msg.sender.hex())
>>> register_raw_precompile("0x00000000000000000000000000000000000000ff", log)
>>> boa.eval("raw_call(0x00000000000000000000000000000000000000ff, b'')")
0x0000000000000000000000000000000000000069
```

### See Also

- [`deregister_raw_precompile`](./deregister_precompile.md) - Remove a registered precompile
- [`@precompile` decorator](../../guides/advanced_features.md#precompiles) - Higher-level interface for creating precompiles
- [`patch_opcode`](./patch_opcode.md) - Modify EVM opcodes
