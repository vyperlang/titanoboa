# Revert Reasons

A contract may revert during the runtime via the `REVERT` opcode.
During execution, the revert does exactly the same thing independent on the error source.
However, for a developer, there are different reasons to get a revert.
Each of them may be used with [`boa.reverts`](../api/testing.md#boareverts) to test the contract behavior.

## Compiler Revert Reasons

These happen when the compiler generates the error message.
For example:
- Range errors
- Overflows
- Division by zero
- Re-entrancy locks

Things like syntax errors will not be caught during the runtime, but the contract will fail to compile on the first place.

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

## Dev Revert Reasons

Developer reverts are also raised by `assert` statements in the code.
However, by adding a `# dev: <reason>` comment after the assert call, Titanoboa is able to verify the reason and provide a more detailed error message.

!!! vyper
    ```vyper
    @external
    def foo(x: uint256):
        assert x > 0 # dev: "x must be greater than 0"
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
    ```

## Matching Reverts in Tests

`boa.reverts` accepts different keyword arguments, each matching a different kind of revert reason:

| kwarg | matches |
| --- | --- |
| (none / positional string) | any revert, or a user-provided reason string |
| `reason=` | the user revert string (`raise "reason"` or `assert cond, "reason"`) |
| `vm_error=` | the raw VM error text |
| `compiler=` | a compiler-generated reason (overflow, `safeadd`, bounds checks, ...) |
| `dev=` | a `# dev: <reason>` comment |
| `rekt=` | a `# rekt: <reason>` comment (a dev reason that shadows a compiler reason) |

The positional form is a shorthand for `reason=`:

```python
with boa.reverts("x is 1"):
    contract.foo(1)

# ... is the same as ...

with boa.reverts(reason="x is 1"):
    contract.foo(1)
```

A wildcard `with boa.reverts():` catches any revert, and fails the test if the call does *not* revert. That makes it a cheap sanity check, but prefer a specific matcher when the revert reason matters, so your test fails loudly if the contract starts reverting for a different reason.

### Precedence

Only one reason "wins" for a given revert, and the matchers are checked against that winner:

- A **compiler reason** takes precedence over a plain `assert` string. If `assert x + 1 == 5` overflows, the reason is the compiler's overflow, not the assert string.
- A **`# dev:` / `# rekt:` comment** on the line that actually reverted takes precedence over the compiler reason. This is their whole purpose: naming the intended revert reason offchain, with zero gas or bytecode cost.
- A dev comment on an unrelated line does *not* mask the real reason.

In practice this means: match `compiler=` when you are exercising a language-level failure, and match `dev=`/`rekt=` when the contract author gave the revert a name. If you are unsure which reason a revert produces, let a test fail once and read the error message: titanoboa prints the expected and actual reasons side by side.

### Testing Compiler Reverts

```python
# uint256 addition overflow is a compiler (safeadd) revert
with boa.reverts(compiler="safeadd"):
    contract.bar(2**256 - 1)
```

### Testing Dev Reverts

```python
# given:  def bar(x: uint256) -> uint256: return x + 1  # dev: could overflow
with boa.reverts(dev="could overflow"):
    contract.bar(2**256 - 1)

# `# rekt: <reason>` is matched with the rekt= kwarg
with boa.reverts(rekt="overflow!"):
    contract.baz(2**256 - 1)
```

All the examples above are exercised in `tests/unitary/test_reverts.py`, which is the most complete reference for the edge cases (multiline asserts, nested calls, constructor reverts).
