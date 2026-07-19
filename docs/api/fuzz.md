# Fuzzing API

## `fuzz`

!!! function "`@boa.fuzz(contract_function)`"

    Derive Hypothesis strategies from a deployed Vyper function's canonical
    ABI argument types and apply them to the decorated Python test.

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

    The result is a Hypothesis test and must be called (or collected by
    pytest). A strategy is generated for every Vyper argument, including
    arguments with defaults. Use `boa.test.strategy` with `hypothesis.given`
    when you need custom ranges or sizes.

## `strategy`

!!! function "`boa.test.strategy(type_string, **kwargs)`"

    Return a Hypothesis strategy for a canonical ABI type string.

    ```python
    from hypothesis import given

    from boa.test import strategy


    @given(
        account=strategy("address"),
        amount=strategy("uint256", min_value=1, max_value=10**24),
        route=strategy("address[]", min_length=2, max_length=5),
    )
    def test_inputs(account, amount, route):
        assert amount > 0
        assert 2 <= len(route) <= 5
    ```

    Supported values include integers, `address`, `bool`, fixed and dynamic
    bytes, `string`, arrays, tuples, and Vyper `decimal`. Type-specific keyword
    arguments are passed to the underlying strategy builder. Nested dynamic
    arrays accept a list for `min_length` or `max_length`, one value per dynamic
    dimension. Dynamic `bytes` defaults to `min_size=1` (empty bytes are not
    generated unless you override that).

See the [fuzzing strategies guide](../guides/testing/fuzzing_strategies.md) for
per-type examples, `@boa.fuzz`, composite and stateful testing, pytest
isolation, and common patterns.
