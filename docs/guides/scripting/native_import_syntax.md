## Native Import Syntax

Titanoboa supports the native Python import syntax for Vyper contracts. This means that you can import Vyper contracts in any Python script as if you were importing a Python module.

For example, if you have a contract `contracts/Foo.vy`:

```vyper
x: public(uint256)

def __init__(x_initial: uint256):
    self.x = x_initial
```

You can import it in a Python script `tests/bar.py` like this

```python
from contracts import Foo

my_contract = Foo(42) # This will create a new instance of the contract

my_contract.x() # Do anything with the contract as you normally would
```

Internally this will use the `importlib` module to call [`boa.load_partial`](../../api/load_contracts.md#load_partial) on the file and create a `ContractFactory`.

!!! note
    For this to work `boa` must be imported first.
    Due to limitations in the Python import system, only imports of the form `import Foo` or `from <folder> import Foo` will work and it is not possible to use `import <folder>`.
