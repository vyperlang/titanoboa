# Env

### Description

TODO
<!-- A wrapper class around py-evm which provides a "contract-centric" API. TODO more details on the singleton architecture in [boa-singleton-env](../../explain/singleton_env.md). -->

### Attributes

- `eoa`: The account to use as `msg.sender` for top-level calls and `tx.origin` in the context of state mutating function calls.
- `chain`: The global py-evm chain instance.

---

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

    A context manager which snapshots the state and the vm, and reverts to the snapshot on exit.

    ---

    **Examples**

    ```python
    >>> import boa
    >>> src = """
    ... value: public(uint256)
    ... """
    >>> contract = boa.loads(src)
    >>> contract.value()
    0
    >>> with boa.env.anchor():
    ...     contract.eval("self.value += 1")
    ...     contract.value()
    ...
    1
    >>> contract.value()
    0
    ```

---

## `deploy_code`

!!! function "`boa.env.deploy_code(bytecode) -> bytes`"

    **Description**

    Deploy bytecode at a specific account.

    ---

    **Parameters**

    - `at`: The account the deployment bytecode will run at.
    - `sender`: The account to set as `tx.origin` for the execution context and `msg.sender` for the top-level call.
    - `gas`: The gas limit provided for the execution (a.k.a. `msg.gas`).
    - `value`: The ether value to attach to the execution (a.k.a `msg.value`).
    - `bytecode`: The deployment bytecode.
    - `data`: The data to attach to the execution (a.k.a. `msg.data`).
    - `pc`: The program counter to start the execution at.

    ---

    **Returns**

    The return value from the top-level call (typically the runtime bytecode of a contract).

    ---

    **Examples**

    ```python
    >>> import boa
    >>> code = bytes.fromhex("333452602034f3")  # simply returns the caller
    >>> boa.env.deploy_code(bytecode=code, sender="0x0000000022D53366457F9d5E68Ec105046FC4383").hex()
    '0000000000000000000000000000000022d53366457f9d5e68ec105046fc4383'
    >>> boa.env.vm.state.get_code(b"\x00" * 20).hex()
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

!!! function "`boa.env.enable_fast_mode() -> None`"

    **Description**

    Enable or disable fast mode. This can be useful for speeding up tests.

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

!!! function "`boa.env.execute_code() -> bytes`"

    **Description**

    Execute bytecode at a specific account.

    ---

    **Parameters**

    - `at`: The account to target.
    - `sender`: The account to set as `tx.origin` for the execution context and `msg.sender` for the top-level call.
    - `gas`: The gas limit provided for the execution (a.k.a. `msg.gas`).
    - `value`: The ether value to attach to the execution (a.k.a `msg.value`).
    - `bytecode`: The runtime bytecode.
    - `data`: The data to attach to the execution (a.k.a. `msg.data`).
    - `pc`: The program counter to start the execution at.

    ---

    **Returns**

    The return value from the top-level call.

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

!!! function "`boa.env.raw_call(to_address) -> bytes`"

    **Description**

    TODO too many details this should go in the explain section
    Simple wrapper around `execute_code`, to execute as if the contract is being called from an EOA.

    ---

    **Parameters**

    - `to_address`: The contract to target.
    - `sender`: The account to set as `tx.origin` for the execution context and `msg.sender` for the top-level call.
    - `gas`: The gas limit provided for the execution (a.k.a. `msg.gas`).
    - `value`: The ether value to attach to the execution (a.k.a `msg.value`).
    - `data`: The data to attach to the execution (a.k.a. `msg.data`).

    ---

    **Returns**

    The return value from the top-level call.

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
