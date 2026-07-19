# Env

### Description

A wrapper class around py-evm which provides a "contract-centric" API. More details on the environment architecture in [boa-singleton-env](../../explain/singleton_env.md).

---

## `timestamp`

!!! property "`boa.env.timestamp`"

    **Description**

    Returns the internal pyevm timestamp. Should be equal to evaluating `block.timestamp`.

    Uses the low-level `boa.env.evm.patch` object so timestamp changes are rolled
    back after exiting `boa.env.anchor()` blocks.

## `alias`

!!! function "`boa.env.alias(address, name)`"

    **Description**

    Associates an alias with an address. This is useful to make the address more human-readable in tracebacks.

    ---

    **Parameters**

    - `address`: The address to alias.
    - `name`: The alias to use for the address.

---

## `anchor`

!!! function "`boa.env.anchor()`"

    **Description**

    A context manager which snapshots the state and the vm, and reverts to the snapshot on exit. Properties in the low-level `boa.env.evm.patch` object are also rolled back after exiting the context manager.

    ---

    **Examples**

    ```python
    >>> import boa
    >>> src = """
    ... stored_value: public(uint256)
    ... """
    >>> contract = boa.loads(src)
    >>> contract.stored_value()
    0
    >>> with boa.env.anchor():
    ...     contract.eval("self.stored_value += 1")
    ...     contract.stored_value()
    ...
    1
    >>> contract.stored_value()
    0
    ```

---

## `deploy_code`

!!! function "`boa.env.deploy_code(bytecode=..., **kwargs) -> tuple[Address, bytes]`"

    **Description**

    Execute deployment bytecode and return the created address and the
    deployment output (normally the runtime bytecode).

    ---

    **Parameters**

    - `sender`: The account to set as `tx.origin` for the execution context and `msg.sender` for the top-level call.
    - `gas`: The gas limit provided for the execution (a.k.a. `msg.gas`).
    - `value`: The ether value to attach to the execution (a.k.a `msg.value`).
    - `bytecode`: The deployment bytecode.
    - `start_pc`: Accepted for API compatibility, but unused for deployments.
    - `override_address`: Create the contract at this address instead of the
      address derived from the sender and nonce.

    ---

    **Returns**

    A `(created_address, output)` tuple.

    ---

    **Examples**

    ```python
    >>> import boa
    >>> code = bytes.fromhex("333452602034f3")  # simply returns the caller
    >>> address, output = boa.env.deploy_code(
    ...     bytecode=code,
    ...     sender="0x0000000022D53366457F9d5E68Ec105046FC4383",
    ... )
    >>> output.hex()
    '0000000000000000000000000000000022d53366457f9d5e68ec105046fc4383'
    >>> boa.env.get_code(address).hex()
    '0000000000000000000000000000000022d53366457f9d5e68ec105046fc4383'
    ```

---

## `disable_gas_metering`

!!! function "`boa.env.disable_gas_metering() -> None`"

    **Description**

    Disable gas metering by setting the gas meter class to `NoGasMeter`.

    ---

    **Example**

    ```python
    >>> import boa
    >>> boa.env.disable_gas_metering()
    >>> # Subsequent operations will not meter gas
    ```

---

## `enable_fast_mode`

!!! function "`boa.env.enable_fast_mode(flag=True) -> None`"

    **Description**

    Enable or disable fast mode. This can speed up tests by using alternative
    execution paths.

    ---

    **Parameters**

    - `flag`: Whether to enable or disable fast mode.

    ---

    **Warning**

    Fast mode is experimental and can break other features of boa (like coverage).

---

## `enable_gas_profiling`

!!! function "`boa.env.enable_gas_profiling() -> None`"

    **Description**

    Enable gas profiling by setting the gas meter class to `ProfilingGasMeter`. This is useful for detailed analysis of gas consumption in contract executions.

    ---

    **Example**

    ```python
    >>> import boa
    >>> boa.env.enable_gas_profiling()
    >>> # Subsequent operations will use ProfilingGasMeter
    ```

---

## `execute_code`

!!! function "`boa.env.execute_code(to_address=..., **kwargs) -> ComputationAPI`"

    **Description**

    Execute bytecode at a specific account.

    ---

    **Parameters**

    - `to_address`: The account to target.
    - `sender`: The account to set as `tx.origin` for the execution context and `msg.sender` for the top-level call.
    - `gas`: The gas limit provided for the execution (a.k.a. `msg.gas`).
    - `value`: The ether value to attach to the execution (a.k.a `msg.value`).
    - `data`: The data to attach to the execution (a.k.a. `msg.data`).
    - `override_bytecode`: Runtime bytecode to execute instead of code stored at
      `to_address`.
    - `is_modifying`: If false, execute as a static call.
    - `simulate`: If true, roll state back after execution.
    - `start_pc`: The initial program counter.

    ---

    **Returns**

    A `ComputationAPI` object containing the execution result. Key members include:
    - `output`: The return data as bytes
    - `is_error`: Boolean indicating if the execution failed
    - `error`: The exception if execution failed
    - `get_gas_used()`: Amount of gas consumed

    ---

    **Note**

    Unlike `raw_call`, this method returns the computation object directly without raising exceptions on errors.

---

## `gas_meter_class`

!!! function "`boa.env.gas_meter_class()`"

    **Description**

    A context manager to temporarily set the gas meter class. This is useful for temporarily changing the gas metering behavior for specific operations.

    ---

    **Parameters**

    - `cls`: The gas meter class to use within the context.

    ---

    **Example**

    ```python
    >>> import boa
    >>> from boa.vm.gas_meters import ProfilingGasMeter
    >>> with boa.env.gas_meter_class(ProfilingGasMeter):
    ...     # Operations using ProfilingGasMeter
    ...     pass
    >>> # Gas meter class is reset to the previous value
    ```

---

## `generate_address`

!!! function "`boa.env.generate_address() -> str`"

    **Description**

    Generate an address and optionally alias it.

    ---

    **Parameters**

    - `alias`: The alias to use for the generated address.

    ---

    **Examples**

    ```python
    >>> import boa
    >>> boa.env.generate_address()
    'd13f0Bd22AFF8176761AEFBfC052a7490bDe268E'
    ```

---

## `get_balance`

!!! function "`boa.env.get_balance(address: str) -> int`"

    **Description**

    Get the ether balance of an account.

---

## `get_code`

!!! function "`boa.env.get_code(address)`"

    **Description**

    Get the bytecode stored at the specified address. This is useful for inspecting deployed contract bytecode.

    ---

    **Parameters**

    - `address`: The address to retrieve the code from.

    ---

    **Returns**

    The bytecode as bytes.

    ---

    **Example**

    ```python
    >>> import boa
    >>> code = boa.env.get_code("0x1234...")
    >>> print(f"Bytecode length: {len(code)}")
    ```

---

## `get_gas_meter_class`

!!! function "`boa.env.get_gas_meter_class()`"

    **Description**

    Get the current gas meter class used in the environment. This method is useful for inspecting the current gas metering behavior in the environment.

    ---

    **Returns**

    The current gas meter class.

    ---

    **Example**

    ```python
    >>> import boa
    >>> gas_meter_class = boa.env.get_gas_meter_class()
    >>> print(gas_meter_class.__name__)
    'GasMeter'  # Default gas meter class
    ```

---

## `get_gas_price`

!!! function "`boa.env.get_gas_price()`"

    **Description**

    Get the current gas price used for transactions in the environment.

    ---

    **Returns**

    The current gas price as an integer.

    ---

    **Example**

    ```python
    >>> import boa
    >>> boa.env.get_gas_price()
    0  # Default gas price is 0
    ```

---

## `get_gas_used`

!!! function "`boa.env.get_gas_used()`"

    **Description**

    Get the total amount of gas used in the current environment. This is useful for tracking gas consumption across multiple operations.

    ---

    **Returns**

    The total gas used as an integer.

    ---

    **Example**

    ```python
    >>> import boa
    >>> gas_used = boa.env.get_gas_used()
    >>> print(f"Total gas used: {gas_used}")
    ```

---

## `get_singleton`

!!! function "`boa.env.get_singleton()`"

    **Description**

    Get or create the singleton instance of the `Env` class. This is typically used internally to ensure a single environment instance.

    ---

    **Returns**

    The singleton instance of the `Env` class.

    ---

    **Example**

    ```python
    >>> import boa
    >>> env = boa.env.get_singleton()
    >>> # Use env for environment operations
    ```

---

## `get_storage`

!!! function "`boa.env.get_storage(address: str, slot: int) -> int`"

    **Description**

    Get the value stored at a specific storage slot for the given address. This allows direct access to contract storage, which can be useful for debugging and testing.

    ---

    **Parameters**

    - `address`: The address of the contract.
    - `slot`: The storage slot to read from.

    ---

    **Returns**

    The value stored in the specified slot as an integer.

    ---

    **Example**

    ```python
    >>> import boa
    >>> value = boa.env.get_storage("0x1234...", 0)
    >>> print(f"Value in slot 0: {value}")
    ```

---

## `lookup_alias`

!!! function "`boa.env.lookup_alias(address: str) -> str`"

    **Description**

    Look up the alias for a given address. This is useful for working with human-readable names for addresses.

    ---

    **Parameters**

    - `address`: The address to look up the alias for.

    ---

    **Returns**

    The alias associated with the address.

    ---

    **Example**

    ```python
    >>> import boa
    >>> alias = boa.env.lookup_alias("0x1234...")
    >>> print(f"Alias for 0x1234... is {alias}")
    ```

---

## `lookup_contract`

!!! function "`boa.env.lookup_contract(address: str) -> Any`"

    **Description**

    Look up a contract object by its address. This is useful for retrieving previously registered contracts.

    ---

    **Parameters**

    - `address`: The address of the contract to look up.

    ---

    **Returns**

    The contract object if found, otherwise None.

    ---

    **Example**

    ```python
    >>> import boa
    >>> contract = boa.env.lookup_contract("0x1234...")
    >>> if contract:
    ...     print("Contract found")
    ... else:
    ...     print("Contract not found")
    ```

---

## `prank`

!!! function "`boa.env.prank(address)`"

    **Description**

    A context manager which temporarily sets `eoa` and resets it on exit.

    ---

    **Examples**

    ```python
    >>> import boa
    >>> boa.env.eoa
    '0x0000000000000000000000000000000000000065'
    >>> with boa.env.prank("0x00000000000000000000000000000000000000ff"):
    ...     boa.env.eoa
    ...
    '0x00000000000000000000000000000000000000ff'
    >>> boa.env.eoa
    ```

---

## `raw_call`

!!! function "`boa.env.raw_call(to_address) -> ComputationAPI`"

    **Description**

    Execute a call to a contract address, simulating an EOA transaction.

    ---

    **Parameters**

    - `to_address`: The contract to target.
    - `sender`: The account to set as `tx.origin` for the execution context and `msg.sender` for the top-level call.
    - `gas`: The gas limit provided for the execution (a.k.a. `msg.gas`).
    - `value`: The ether value to attach to the execution (a.k.a `msg.value`).
    - `data`: The data to attach to the execution (a.k.a. `msg.data`).
    - `simulate`: If True, the call is executed in a context that is rolled back after execution.

    ---

    **Returns**

    A `ComputationAPI` object containing the execution result. Key members include:
    - `output`: The return data as bytes
    - `is_error`: Boolean indicating if the execution failed
    - `error`: The exception if execution failed
    - `get_gas_used()`: Amount of gas consumed

    ---

    **Important**

    Unlike `execute_code`, if the computation fails (`is_error` is True), this method raises the error as an exception.

    ---

    **Example**

    ```python
    >>> computation = boa.env.raw_call(contract_address, data=b"\x00\x00\x00\x00")
    >>> print(computation.output.hex())
    ```

---

## `register_blueprint`

!!! function "`boa.env.register_blueprint(bytecode, obj)`"

    **Description**

    Register a blueprint object with its bytecode in the environment. This is used for managing blueprint contracts in the environment.

    ---

    **Parameters**

    - `bytecode`: The bytecode of the blueprint.
    - `obj`: The blueprint object to register.

    ---

    **Example**

    ```python
    >>> import boa
    >>> blueprint = boa.load_partial("path/to/blueprint.vy")
    >>> boa.env.register_blueprint(blueprint.bytecode, blueprint)
    ```

---

## `register_contract`

!!! function "`boa.env.register_contract(address, obj)`"

    **Description**

    Register a contract object with its address in the environment.

    ---

    **Parameters**

    - `address`: The address of the contract.
    - `obj`: The contract object to register.

    ---

    **Example**

    ```python
    >>> import boa
    >>> contract = boa.load("path/to/contract.vy")
    >>> boa.env.register_contract(contract.address, contract)
    ```

    ---

    **Note**

    This is typically used internally but can be useful for manual contract management.

---

## `reset_gas_metering_behavior`

!!! function "`boa.env.reset_gas_metering_behavior()`"

    **Description**

    Reset gas metering to the default behavior by setting the gas meter class to `GasMeter`.

    ---

    **Example**

    ```python
    >>> import boa
    >>> boa.env.reset_gas_metering_behavior()
    >>> # Gas metering is reset to default
    ```

    ---

    **Note**

    This is useful for restoring normal gas metering after using specialized gas meters.

---

## `reset_gas_used`

!!! function "`boa.env.reset_gas_used()`"

    **Description**

    Reset the gas usage counter to zero and reset access counters.

    ---

    **Example**

    ```python
    >>> import boa
    >>> boa.env.reset_gas_used()
    >>> # Gas usage is now reset to 0
    ```

    ---

    **Note**

    This is useful when you want to start a fresh gas measurement.

---

## `set_balance`

!!! function "`boa.env.set_balance(address: str, value: int)`"

    **Description**

    Set the ether balance of an account. This is useful for testing scenarios that require specific account balances.

    ---

    **Parameters**

    - `address`: The address to set the balance for
    - `value`: The new balance in wei

    ---

    **Example**

    ```python
    >>> import boa
    >>> boa.env.set_balance("0x1234...", 10**18)  # Set balance to 1 ETH
    >>> boa.env.get_balance("0x1234...")
    1000000000000000000
    ```

---

## `set_storage`

!!! function "`boa.env.set_storage(address: str, slot: int, value: int)`"

    **Description**

    Set a value in a specific storage slot for the given address. This allows direct manipulation of contract storage, which can be useful for advanced testing scenarios.

    ---

    **Parameters**

    - `address`: The address of the contract
    - `slot`: The storage slot to write to
    - `value`: The value to store

    ---

    **Example**

    ```python
    >>> import boa
    >>> # Set storage slot 0 to value 42
    >>> boa.env.set_storage("0x1234...", 0, 42)
    >>> boa.env.get_storage("0x1234...", 0)
    42
    ```

    ---

    **Warning**

    Direct storage manipulation can break contract invariants. Use with caution.

---

## `set_code`

!!! function "`boa.env.set_code(address: str, bytecode: bytes)`"

    **Description**

    Set the bytecode at a specific address. This is useful for testing upgrades or deploying code to specific addresses.

    ---

    **Parameters**

    - `address`: The address to set the code at
    - `bytecode`: The bytecode to deploy

    ---

    **Example**

    ```python
    >>> import boa
    >>> bytecode = bytes.fromhex("6080604052...")
    >>> boa.env.set_code("0x1234...", bytecode)
    ```

    ---

    **Warning**

    This operation bypasses normal deployment procedures and should be used carefully.

---

## `deploy`

!!! function "`boa.env.deploy(sender=None, gas=None, value=0, bytecode=b'', override_address=None, contract=None)`"

    Execute deployment bytecode and return `(address, computation)`. Unlike
    `deploy_code`, this lower-level method returns the computation even when
    deployment fails, so callers can inspect `computation.is_error` and
    `computation.error`.

    `override_address` bypasses normal CREATE address derivation and is intended
    for local testing. `contract` associates source metadata with tracing and
    coverage.

    ```python
    address, computation = boa.env.deploy(bytecode=initcode)
    if computation.is_error:
        raise computation.error
    ```

---

## `sender`

!!! function "`boa.env.sender(address)`"

    Temporarily set the environment's default EOA. Top-level calls and
    deployments that omit `sender=` use this address for both `msg.sender` and
    `tx.origin`. The previous EOA is restored when the context exits.
    `boa.env.prank(address)` is an alias.

    ```python
    user = boa.env.generate_address("user")

    with boa.env.sender(user):
        contract.deposit(value=10**18)
    ```

    Nested contract calls still follow normal EVM semantics: `msg.sender`
    becomes the calling contract while `tx.origin` remains the top-level EOA.

---

## `set_random_seed`

!!! function "`boa.env.set_random_seed(seed=None)`"

    Replace the deterministic random generator used by `generate_address`.
    Reusing a seed reproduces the same generated-address sequence.

    ```python
    boa.env.set_random_seed("scenario-a")
    first = boa.env.generate_address()

    boa.env.set_random_seed("scenario-a")
    assert boa.env.generate_address() == first
    ```

    This does not change EVM randomness (`block.prevrandao`) or cryptographic
    randomness in contracts. Passing `None` uses Python's default seeding
    behavior and is not reproducible.

---

## `time_travel`

!!! function "`boa.env.time_travel(seconds=None, blocks=None, block_delta=12)`"

    Advance local block time by exactly one of `seconds` or `blocks`.

    - `seconds=N` adds `N` to the timestamp and `N // block_delta` to the block
      number.
    - `blocks=N` adds `N` to the block number and `N * block_delta` to the
      timestamp.
    - Supplying both arguments, or neither, raises `ValueError`.

    ```python
    start = boa.env.timestamp
    boa.env.time_travel(seconds=3600)
    assert boa.env.timestamp == start + 3600
    ```

    Changes inside `boa.env.anchor()` are reverted with the rest of the
    environment patch state. This is a local py-evm cheat method; it does not
    advance the remote chain used by `NetworkEnv`.
