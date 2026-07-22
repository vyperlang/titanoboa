# Typed precompiles

## `precompile`

!!! function "`@boa.precompile(vyper_signature, force=False)`"

    Register a Python function as a typed Vyper builtin backed by a py-evm
    precompile. Titanoboa derives the precompile address from
    `keccak256(vyper_signature)[:20]`, ABI-decodes arguments before calling
    Python, and ABI-encodes the return value.

    ```python
    import boa


    @boa.precompile("def double(number: uint256) -> uint256")
    def double(number):
        return number * 2


    contract = boa.loads(
        """
    @external
    @view
    def run(number: uint256) -> uint256:
        return double(number)
    """
    )

    assert contract.run(21) == 42
    ```

    - `vyper_signature` must be a Vyper function declaration without the
      trailing colon, for example
      `def double(number: uint256) -> uint256`.
    - `force=True` replaces an existing raw precompile registered at the
      derived address.
    - The decorator returns the low-level computation wrapper, not the
      original Python function. Keep a separate undecorated function if it
      also needs to be called directly from Python.

    Registration updates process-global Vyper builtin tables and the global
    raw-precompile registry. It therefore affects contracts compiled and
    environments created later in the same Python process. Use unique function
    names and signatures in test suites.

!!! warning "Vyper compatibility"
    Titanoboa 0.2.8's typed decorator works with Vyper 0.4.2. Vyper 0.4.3
    changed the internal function-type API used by this feature, so decorator
    registration currently raises `TypeError` with that version.

For fixed-address computation callbacks, use the
[raw precompile API](pyevm/register_precompile.md).
