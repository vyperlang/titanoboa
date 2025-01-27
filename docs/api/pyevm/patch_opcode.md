# `patch_opcode`

### Signature

```python
patch_opcode(opcode: int, fn: Callable[[eth.abc.ComputationAPI], None])
```

### Description

Patch an opcode.

- `opcode`: The opcode to patch.
- `fn`: The function implementing the desired opcode functionality.

### Examples

The following code snippet implements tracing for the `CREATE` opcode and stores all newly created accounts in a list.

```python
# example.py
import boa

class CreateTracer:
    def __init__(self, super_fn):
        """Track addresses of contracts created via the CREATE opcode.

        Parameters:
            super_fn: The original opcode implementation.
        """
        self.super_fn = super_fn
        self.trace = []

    def __call__(self, computation):
        # first, dispatch to the original opcode implementation provided by py-evm
        self.super_fn(computation)
        # then, store the output of the CREATE opcode in our `trace` list for later
        self.trace.append("0x" + computation._stack.values[-1][-1].hex())

if __name__ == "__main__":
    create_tracer = CreateTracer(boa.env.vm.state.computation_class.opcodes[0xf0])
    boa.patch_opcode(0xf0, create_tracer)

    source = """
@external
def main():
    for _ in range(10):
        addr: address = create_minimal_proxy_to(self)
    """
    contract = boa.loads(source)
    contract.main()  # execute the contract function
    print(create_tracer.trace)
```

Running the code would produce the following results:

```bash
$ python example.py
[
    "0xd130b7e7f212ecadcfcca3cecc89f85ce6465896",
    "0x37fdb059bf647b88dbe172619f00b8e8b1cf9338",
    "0x40bcd509b3c1f42d535d1a8f57982729d4b52adb",
    "0xaa35545ac7a733600d658c3f516ce2bb2be99866",
    "0x29e303d13a16ea18c6b0e081eb566b55a74b42d6",
    "0x3f69d814da1ebde421fe7dc99e24902b15af960b",
    "0x719c0dc21639008a2855fdd13d0d6d89be53f991",
    "0xf6086a85f5433f6fbdcdcf4f2ace7915086a5130",
    "0x097dec6ea6b9eb5fc04db59c0d343f0e3b4097a0",
    "0x905794c5566184e642ef14fb0e72cf68ff8c79bf"
]
```
