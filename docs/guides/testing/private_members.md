# Accessing private members

Titanoboa allows access to private members of a contract. This is useful for testing internal functions or variables without having to expose them to the outside world.

Given a vyper module `foo.vy` in the same folder as your python code:

```vyper
x: uint256
y: immutable(uint256)

def __init__(y_initial: uint256):
    self.x = 42
    self.y = y_initial

@internal
@pure
def _bar() -> uint256:
    return 111
```

We can notice that `x`, `y` and `_bar` are all private members of the contract that wouldn't be easily accessible in a normal context. Boa allows access to all of these members, let's see how.

## Accessing internal functions

`internal` functions can be accessed by calling the function from the `internal` attribute of the contract.

```python
import foo

my_contract = foo(1234)

my_contract.internal._bar() # returns 111
```

## Accessing private storage variables

Private storage variables can be accessed by calling the variable from the `_storage` attribute of the contract:

```python
import foo

my_contract = foo(1234)

my_contract._storage.x.get() # returns 42
```

## Accessing private immutable variables

Similarly private immutable variables can be accessed by calling the variable from the `_immutable` attribute of the contract:

```python
import foo

my_contract = foo(1234)

my_contract._immutables.y # returns 1234
```

## Accessing internal module variables

Since vyper 0.4.0 it is possible to modularize contracts.

Boa doesn't yet support accessing private module variables. However this can easily be done using [`eval`](../../api/vyper_contract/eval.md).

Given a module `bar.vy`:

```vyper
# bar.vy
x: uint256
```

If another contract `foo.vy` imports `bar`:

```vyper
# foo.vy
import bar

foo: public(uint256)
```

It is possible to access `bar.x` from `foo` using eval:


```python
foo = boa.load("foo.vy")

foo.eval("bar.x") # returns the value of bar.x
```
