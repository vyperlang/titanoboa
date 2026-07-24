# Testing and Forking

### Description

Boa provides various utilities to test vyper contracts and execute them in a forked environment.

---

## **Methods**

### `eval`
!!! function "`boa.eval(statement)`"

    **Description**

    Evaluate a Vyper statement in the context of a contract with no state.

    ---

    **Parameters**

    - `statement`: A valid Vyper statement.

    ---

    **Returns**

    The result of the statement execution.

    ---

    **Examples**

    ```python
    >>> import boa
    >>> boa.eval("keccak256('Hello World!')").hex()
    '3ea2f1d0abf3fc66cf29eebb70cbd4e7fe762ef8a09bcc06c8edf641230afec0'
    >>> boa.eval("empty(uint256[10])")
    (0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    ```

---

### `fork`
!!! function "`boa.fork(url)`"

    **Description**

    Forks the environment to a local chain using the specified RPC URL and block identifier. This allows testing in a forked state of the blockchain.

    ---

    **Parameters**

    - `url: str`: The RPC URL to fork from.
    - `block_identifier: int | str = "safe"`: The block identifier to fork from, can be an integer or a string (default is "safe").
    - `allow_dirty: bool = False`: If `True`, allows forking with a dirty state (default is `False`).
    - `reset_traces: bool = True`: Whether to reset the traces.
    - `cache_dir: str | None = ~/.cache/titanoboa/fork/`: The directory to create the cache database for forked state. To learn more about caching see [Caching](../explain/caching.md).
    - `debug: bool = False`: Whether to debug RPC calls.
    - `**kwargs`: Additional arguments for the RPC.
    ---

    **Returns**

    Sets the environment to the new forked state. Calling `boa.fork(...)`
    directly keeps that fork active. Using it as a context manager restores the
    previous environment on exit. To learn more about environments see
    [Titanoboa Environments](../explain/singleton_env.md).

    ---

    **Examples**

    ```python
    import boa

    # Fork mainnet at latest safe block
    with boa.fork("https://eth.llamarpc.com"):
        # Deploy and test against mainnet state
        contract = boa.loads_partial(source).deploy()
    ```


---

### `boa.deal`
!!! function "`deal(token, receiver, amount)`"

    **Description**

    Overwrites the balance of `receiver` for `token` to `amount`, and adjusts the total supply if `adjust_supply` is True.

    ---

    **Parameters**

    - `token`: The token contract to modify.
    - `receiver`: The address to modify the balance for.
    - `amount`: The new balance amount.
    - `adjust_supply`: Whether to adjust the total supply of the token. Defaults to True.

    ---

    **Limitations**

    `deal` finds storage by tracing `SLOAD` during `balanceOf(receiver)` and,
    when `adjust_supply` is true, `totalSupply()`. It only works when those
    values live in unpacked storage slots that mirror the returned integers.
    Tokens that pack storage, compute balances on the fly, or omit a standard
    `totalSupply` raise `ValueError`. Use `adjust_supply=False` for tokens
    where supply tracking is unavailable or exotic (for example some WETH
    layouts).

    ---

    **Examples**

    === "Vanilla ERC20"

        Let's modify the balance of `alice` for `usdc` to 100.

        ```python
        import os

        import boa

        boa.fork(os.environ["ETH_RPC_URL"])
        usdc = boa.from_etherscan(
            "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            name="USDC",
            chain_id=1,
        )
        alice = boa.env.generate_address("alice")

        boa.deal(usdc, alice, 100 * 10 ** usdc.decimals())  # (1)!

        usdc.balanceOf(alice) # returns 100 * 10 ** 6
        ```

        1. We multiply the amount by `10 ** usdc.decimals()` to account for the token's decimals.
    === "WETH"
        ```python
        import os

        import boa

        boa.fork(os.environ["ETH_RPC_URL"])
        weth = boa.from_etherscan(
            "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
            name="WETH",
            chain_id=1,
        )
        alice = boa.env.generate_address("alice")

        boa.deal(weth, alice, 10 * 10**18, adjust_supply=False)
        ```



---

### `boa.reverts`
!!! function "`reverts(*args, reason=None, compiler=None, vm_error=None, **dev_reasons)`"

    **Description**

    A context manager which validates an execution error occurs with optional reason matching.

    ---

    **Parameters**

    - Positional string (or `reason=`): Match against the execution error / developer reason.
    - `compiler`: A string to match against the internal compiler revert reason.
    - `vm_error`: A string to match against the revert reason string.
    - Other keyword arguments (for example `dev=`): Match a developer revert comment by
      reason type. The keyword name is the `DevReason.reason_type` (commonly `dev`).

    ---

    **Examples**

    Boa supports matching against different revert reasons, to learn more about them see [Revert Reasons](../explain/revert_reasons.md).

    === "Revert reason provided as a positional argument"

        ```python
        import boa

        source = """
        @external
        def foo():
            raise "0xdeadbeef"

        @external
        def bar():
            raise  # dev: 0xdeadbeef
        """
        contract = boa.loads(source)

        with boa.reverts("0xdeadbeef"):
            contract.foo()

        with boa.reverts("0xdeadbeef"):
            contract.bar()
        ```

    === "Compiler revert reason"

        ```python
        import boa

        source = """
        @external
        def subtract(a: uint256, b: uint256) -> uint256:
            return a - b

        @external
        def addition(a: uint256, b: uint256) -> uint256:
            return a + b
        """
        contract = boa.loads(source)

        with boa.reverts(compiler="safesub"):
            contract.subtract(1, 2)

        with boa.reverts(compiler="safeadd"):
            contract.addition(1, 2**256 - 1)
        ```

    === "VM error reason"

        ```python
        import boa

        source = """
        @external
        def main(a: uint256):
            assert a == 0, "A is not 0"
        """
        contract = boa.loads(source)

        with boa.reverts(vm_error="A is not 0"):
            contract.main(69)
        ```

    === "Developer revert comment"

        ```python
        import boa

        source = """
        @external
        def main(a: uint256):
            assert a == 0  # dev: a is not 0
        """
        contract = boa.loads(source)

        with boa.reverts(dev="a is not 0"):
            contract.main(69)
        ```
