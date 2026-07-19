# Fuzzing strategies

Titanoboa integrates with [Hypothesis](https://hypothesis.readthedocs.io/) and
provides strategies for canonical ABI type strings.

## Generating values for ABI types

Import `strategy` from `boa.test`:

```python
from hypothesis import given

from boa.test import strategy


@given(
    account=strategy("address"),
    amount=strategy("uint256", max_value=10**24),
)
def test_transfer(token, account, amount):
    token.mint(account, amount)
    assert token.balanceOf(account) == amount
```

`strategy(type_string, **kwargs)` supports:

- signed and unsigned integers, including constrained `min_value`,
  `max_value`, and `exclude` values;
- `address`, optionally with an `env` and `exclude`;
- `bool`;
- fixed and dynamic bytes such as `bytes32` and `bytes`;
- `string`;
- fixed and dynamic ABI arrays;
- ABI tuples;
- Vyper `decimal` (translated to ABI `fixed168x10`).

Examples:

```python
from hypothesis import given

from boa.test import strategy


@given(value=strategy("int128"))
def test_int128_bounds(value):
    assert -(2**127) <= value <= 2**127 - 1


@given(data=strategy("bytes", min_size=1, max_size=1024))
def test_dynamic_bytes(data):
    assert 1 <= len(data) <= 1024


@given(values=strategy("uint256[5]"))
def test_fixed_array(values):
    assert len(values) == 5


@given(values=strategy("address[]", min_length=0, max_length=100))
def test_dynamic_array(values):
    assert len(values) <= 100


@given(position=strategy("(uint256,uint256,bool)"))
def test_tuple(position):
    amount, price, is_long = position
```

For nested dynamic arrays, `min_length` and `max_length` can be lists with one
entry for each dynamic dimension.

## Deriving strategies from a contract function

`@boa.fuzz` inspects a deployed Vyper function and supplies a strategy for each
argument:

```python
import boa

contract = boa.loads(
    """
@external
def identity(item: uint256) -> uint256:
    return item
"""
)


@boa.fuzz(contract.identity)
def check_identity(item):
    assert contract.identity(item) == item


check_identity()
```

The decorated function is a Hypothesis test and must be called. Strategies are
generated from every argument in the Vyper function signature, including
arguments that have default values.

Use `strategy()` directly when values need tighter bounds:

```python
from hypothesis import given, settings

from boa.test import strategy


@settings(max_examples=200, deadline=None)
@given(amount=strategy("uint256", min_value=1, max_value=10**21))
def test_deposit(vault, amount):
    vault.deposit(value=amount)
    assert vault.totalAssets() == amount
```

## Pytest isolation

Titanoboa installs a pytest plugin that is discovered automatically. The plugin
anchors the environment around tests and fixtures, and patches Hypothesis so
each generated example also runs in an anchor. If pytest plugin autoloading is
disabled, register the plugin explicitly:

```python
# conftest.py
pytest_plugins = ["boa.test.plugin"]
```

This prevents state written by one generated example from leaking into the
next. Normal Hypothesis strategies and state-machine tests can be mixed with
`boa.test.strategy`.

## See also

- [Hypothesis documentation](https://hypothesis.readthedocs.io/)
- [Gas profiling](gas_profiling.md)
- [Testing API](../../api/testing.md)
