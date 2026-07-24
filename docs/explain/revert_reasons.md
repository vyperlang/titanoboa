# Revert Reasons

A contract may revert during the runtime via the `REVERT` opcode.
During execution, the revert does exactly the same thing independent on the error source.
However, for a developer, there are different reasons to get a revert.
Each of them may be used with [`boa.reverts`](../api/testing.md#boareverts) to test the contract behavior.

## Compiler Revert Reasons

These happen when Vyper inserts a runtime check.
For example:
- Range errors
- Overflows
- Division by zero
- Re-entrancy locks

Things like syntax errors will not be caught during the runtime, but the contract will fail to compile on the first place.

Match these with the `compiler` keyword:

```python
with boa.reverts(compiler="safeadd"):
    contract.add(max_value, 1)
```

## User Revert Reasons

These happen when the user calls `raise` or `assert` fails in the contract.
The user may provide a reason for the revert, which will be shown to the end user.
!!! vyper
    ```vyper
    @external
    def foo(x: uint256):
        assert x > 0, "x must be greater than 0"
    ```

Note that this may happen directly on the contract being called, or any external contract that the contract interacts with.

Pass a string positionally, or use `reason`/`vm_error`, to match an onchain revert string:

```python
with boa.reverts("x must be greater than 0"):
    contract.foo(0)

with boa.reverts(vm_error="x must be greater than 0"):
    contract.foo(0)
```

## Dev Revert Reasons

Developer reasons are comments attached to a statement. The text before `:` is an arbitrary tag, not a fixed `dev` keyword. Titanoboa can recover the tag and reason from source information without adding the string to deployed bytecode.

!!! vyper
    ```vyper
    @external
    def foo(x: uint256):
        assert x > 0  # dev: x must be greater than 0

    @external
    def bar(x: uint256):
        assert x < 10  # rekt: x must be less than 10
    ```

These reasons are completely offchain and useful when the contract storage is limited (EIP 170).

Traditional revert strings cost gas and bytecode when deploying.
When a revert condition is triggered, extra gas will also be incurred.
Strings are relatively heavy - each character consumes gas.

However, when using [`VyperContract`](../api/vyper_contract/overview.md), Titanoboa is able to track the line where the revert happened.
If it finds a `# dev: <reason>` comment, it will provide a more detailed error message to the developer.

This is particularly useful when testing contracts with [`boa.reverts`](../api/testing.md#boareverts), for example:
!!! python
    ```python
    with boa.reverts(dev="x must be greater than 0"):
        contract.foo(0)

    with boa.reverts(rekt="x must be less than 10"):
        contract.bar(10)
    ```

`reason`, `compiler`, and `vm_error` have special matching behavior. Any other keyword is treated as a developer tag, so its spelling must match the source comment. `boa.reverts()` with no arguments accepts any `BoaError`, while a mismatched reason raises `ValueError`.
