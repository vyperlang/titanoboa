# Pytest Plugin and Hypothesis

Titanoboa ships a pytest plugin that gives every test a fresh, isolated blockchain, and a set of Hypothesis strategies that generate valid Vyper values for fuzz testing. Both load automatically when titanoboa is installed: the plugin is registered via the `boa_test` entry point, so there is nothing to add to your `conftest.py`.

## Automatic State Isolation

Every test (and every fixture) runs against its own anchored copy of the chain. Changes made in one test are rolled back before the next one starts, so tests can be run in any order and never leak state into each other:

```python
import boa
import pytest


@pytest.fixture(scope="module")
def counter():
    return boa.loads(
        """
counter: public(uint256)

@external
def increment():
    self.counter += 1
"""
    )


def test_a(counter):
    assert counter.counter() == 0
    counter.increment()
    assert counter.counter() == 1


def test_b(counter):
    # isolation guarantees this still sees a fresh chain
    assert counter.counter() == 0
```

If a test genuinely needs to opt out of isolation (rare, e.g. tests about the environment itself), mark it with `@pytest.mark.ignore_isolation`.

## Fuzzing with Hypothesis

`boa.test.strategies.strategy()` builds a Hypothesis strategy for any Vyper type string. Combine it with `@given` to run the same test against dozens of generated inputs:

```python
from hypothesis import given, settings

import boa
from boa.test.strategies import strategy


@given(
    a=strategy("uint256", max_value=2**128),
    b=strategy("uint256", max_value=2**128),
)
@settings(max_examples=50)
def test_add_commutative(a, b):
    contract = boa.loads(
        """
@external
@view
def add(x: uint256, y: uint256) -> uint256:
    return x + y
"""
    )
    assert contract.add(a, b) == a + b
```

Notes:

- Each Hypothesis example is isolated just like a normal test, so fuzz runs cannot permanently mutate the chain.
- Generated inputs respect Vyper semantics: a `uint256` strategy produces values in the valid unsigned range. If your function can revert for large inputs (like plain addition overflowing), bound the strategy with `max_value`/`min_value` or filter, otherwise Hypothesis will eventually find the reverting case and fail the test.
- Supported type strings mirror Vyper's: `uint256`, `int128`, `address`, `bytes32`, `String[n]`, `DynArray[...]`, and more (see `boa/test/strategies.py` for the full set).

## Gas Profiling Markers

The plugin also provides the gas profiling markers. See [Gas profiling](gas_profiling.md) for the full guide; the short version:

```python
@pytest.mark.gas_profile      # profile this one test
def test_expensive(...):
    ...

@pytest.mark.ignore_gas_profiling  # exempt a test when running with --gas-profile
def test_not_profiled(...):
    ...
```

Running `pytest --gas-profile` turns on profiling for every test that is not exempted.

## Troubleshooting

- **Markers are unknown / have no effect.** The plugin registers itself via the `boa_test` entry point. If markers are unrecognized, check that titanoboa is installed in the same environment that runs pytest (`pip show titanoboa`), not merely importable.
- **Hypothesis tests fail with reverts.** That is usually the fuzzer doing its job: an unbounded strategy found an input your contract rejects. Bound the strategy or handle the revert in the test.
- **State appears to leak between tests.** Make sure you are not using `@pytest.mark.ignore_isolation`, and that fixtures deploy contracts inside the fixture (deployment happens on the anchored chain of the test that requests it).
