# NetworkEnv

Inherits: [`Env`](env.md)

### Description

`NetworkEnv` interacts with a live RPC. View and pure calls use `eth_call`; mutable calls and deployments are locally simulated against a fresh fork before they are signed and broadcast. Use [`boa.fork()`](singleton.md#fork) when you want local py-evm execution against remote state without broadcasting.

Mutable calls require a sender registered with `add_account()`. Local simulation improves diagnostics but is not a guarantee: network state can change before mining, and missing `debug_traceTransaction` support reduces post-broadcast safety checks.

---

## `tx_settings`

!!! property "`boa.env.tx_settings`"

    **Description**

    Access and modify transaction settings for network interactions. These settings control gas estimation, transaction timeouts, base fee calculations, and priority fee calculation.

    ---

    **Attributes**

    - `base_fee_estimator_constant`: Number of blocks ahead to estimate base fee for (default: 5)
    - `priority_fee_strategy`: Optional function for EIP-1559 priority fee calculation. Defaults to `None`, which uses `eth_maxPriorityFeePerGas`.
    - `poll_timeout`: Timeout in seconds for waiting for transaction receipts (default: 240.0)
    - `estimate_gas_block_identifier`: Block identifier for gas estimation (default: "pending")

    ---

    **Examples**

    ```python
    >>> import boa
    >>> # Increase base fee estimation to 10 blocks ahead (for congested networks)
    >>> boa.env.tx_settings.base_fee_estimator_constant = 10
    >>>
    >>> # Increase timeout for slow networks
    >>> boa.env.tx_settings.poll_timeout = 300.0  # 5 minutes
    >>>
    >>> # Set priority fee to at least 2% of the latest base fee
    >>> boa.env.tx_settings.priority_fee_strategy = lambda ctx: max(
    ...     ctx.rpc_priority_fee,
    ...     ctx.base_fee // 50,
    ... )
    >>>
    >>> # Don't use block parameter for gas estimation (for certain RPC providers)
    >>> boa.env.tx_settings.estimate_gas_block_identifier = None
    ```

    ---

    **Note**

    These settings are particularly useful when dealing with network congestion or RPC provider quirks.

    The `base_fee_estimator_constant` determines how many blocks ahead to calculate the base fee cap. Since EIP-1559 allows base fee to increase by at most 12.5% per block, the maximum base fee after n blocks is calculated as: `current_base_fee * (9/8)^n`. For example, with the default value of 5, the base fee cap would be `current_base_fee * 1.8` (approximately). If you encounter errors like "max fee per gas less than block base fee", try increasing this value.

    The `priority_fee_strategy`, when set, receives a context with `base_fee`, `base_fee_estimate`, `rpc_priority_fee`, and `chain_id`, and must return the priority fee in wei as an `int`. More context fields may be exposed as needed.

---

## `capabilities`

!!! property "`boa.env.capabilities`"

    **Description**

    Access the capabilities detection system that automatically detects EVM features supported by the current network. This property provides information about supported opcodes and EVM versions.

    ---

    **Attributes**

    - `has_cancun`: Whether Cancun opcodes (PUSH0, MCOPY, TLOAD/TSTORE) are supported
    - `has_shanghai`: Whether Shanghai opcodes are supported
    - `has_push0`: Whether PUSH0 opcode is supported
    - `has_mcopy`: Whether MCOPY opcode is supported
    - `has_transient`: Whether transient storage (TLOAD/TSTORE) is supported
    - `has_prague`: Whether the EIP-2935 history-storage contract expected for Prague is present
    - `describe_capabilities()`: Get a human-readable string describing the capabilities
    - `check_evm_version(name)`: Check `shanghai`, `cancun`, or `prague`

    ---

    **Examples**

    ```python
    >>> import boa
    >>> boa.set_network_env("https://eth-mainnet.g.alchemy.com/v2/YOUR-KEY")
    >>>
    >>> # Narrow Prague probe: EIP-2935 history-storage contract only.
    >>> if boa.env.capabilities.check_evm_version("prague"):
    ...     print("Prague history-storage contract detected")
    ... else:
    ...     print("Choose an older EVM target")
    ...
    >>> # Get human-readable description
    >>> print(boa.env.capabilities.describe_capabilities())
    'prague'  # or 'cancun', 'shanghai', or 'pre-shanghai'
    ```

    ---

    **Note**

    `has_prague` only checks for the canonical EIP-2935 history-storage
    contract bytecode; it is not a full Prague feature probe. The other flags
    probe opcode support with `eth_call`. Capability checks describe the
    connected node's latest state; they do not select a Vyper compiler target
    automatically.

---

## `add_account`

!!! function "`add_account(account: Account, force_eoa=False)`"

    **Description**

    Add an account to the network environment. This account can then be used to sign and send transactions.

    ---

    **Parameters**

    - `account`: An `Account` object (e.g., from eth_account library)
    - `force_eoa`: Whether to force the account to be treated as an EOA even if it has code

    ---

    **Example**

    ```python
    >>> import boa
    >>> from eth_account import Account
    >>> account = Account.from_key("0x...")
    >>> boa.env.add_account(account)
    >>> boa.env.eoa = account.address  # Set as default sender
    ```

---

## `anchor`

!!! function "`anchor()`"

    **Description**

    Create a state snapshot using the RPC's `evm_snapshot` method. When used as a context manager, automatically reverts to the snapshot on exit using `evm_revert`.

    ---

    **Example**

    ```python
    >>> import boa
    >>> contract = boa.load("MyContract.vy")
    >>> initial_value = contract.get_value()
    >>>
    >>> with boa.env.anchor():
    ...     contract.set_value(42)
    ...     assert contract.get_value() == 42
    ...
    >>> assert contract.get_value() == initial_value  # Reverted!
    ```

    ---

    **Note**

    Requires RPC support for `evm_snapshot` and `evm_revert` methods. Most local development nodes (Anvil, Hardhat) support these.

---

## Simulation

Contract methods accept `simulate=True`. For a mutable method this performs local execution and then uses `eth_call`; it does not broadcast or persist state.

```python
next_value = contract.increment(simulate=True)
assert contract.counter() != next_value
```

Normal mutable calls are also simulated locally first, but are then broadcast. Deployments follow the same simulate-before-broadcast path.

---

## `deploy_code`

!!! function "`deploy_code(sender=None, gas=None, value=0, bytecode=b'', override_address=None, contract=None) -> tuple[Address, bytes]`"

    **Description**

    Deploy contract bytecode to the network. Returns the deployed contract address and constructor return data.
    This inherits the same keyword arguments as `Env.deploy` / `Env.deploy_code` — pass options by name, not as
    positional constructor arguments.

    ---

    **Parameters**

    - `bytecode`: The deployment bytecode (initcode), including any ABI-encoded constructor args
    - `value`: ETH value to send with deployment
    - `gas`: Gas limit (auto-estimated if None)
    - `sender`: Sender address (uses `env.eoa` if None)
    - `override_address`: Optional address to deploy to
    - `contract`: Optional calling Vyper contract (used for coverage tracing)

    ---

    **Returns**

    A tuple containing:
    - The address of the deployed contract
    - The return data from the deployment transaction

    ---

    **Example**

    ```python
    >>> import boa
    >>> bytecode = bytes.fromhex("608060...")
    >>> address, runtime_bytecode = boa.env.deploy_code(bytecode=bytecode)
    >>> print(f"Deployed at: {address}")
    ```

---

## `get_balance`

!!! function "`get_balance(address: str) -> int`"

    **Description**

    Get the ETH balance of an address from the network.

    ---

    **Parameters**

    - `address`: The address to query

    ---

    **Returns**

    The balance in wei.

    ---

    **Example**

    ```python
    >>> import boa
    >>> balance = boa.env.get_balance("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
    >>> print(f"Balance: {balance / 10**18:.4f} ETH")
    ```

---

## `get_code`

!!! function "`get_code(address: str) -> bytes`"

    **Description**

    Get the bytecode at an address from the network.

    ---

    **Parameters**

    - `address`: The address to query

    ---

    **Returns**

    The bytecode as bytes.

    ---

    **Example**

    ```python
    >>> import boa
    >>> code = boa.env.get_code("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
    >>> if code:
    ...     print(f"Contract has {len(code)} bytes of code")
    ... else:
    ...     print("No code at address (EOA)")
    ```

---


## `set_balance`

!!! function "`set_balance(address: str, value: int)`"

    **Description**

    Set the ETH balance of an address. **Note: This method is not implemented in NetworkEnv and will raise NotImplementedError.**

    ---

    **Parameters**

    - `address`: The address to modify
    - `value`: The new balance in wei

    ---

    **Note**

    This method raises `NotImplementedError` in `NetworkEnv`. `set_code` and `set_storage` are unavailable for the same reason. Use `boa.fork()` for local state mutation.

## Live-network isolation

`anchor()` requires nonstandard `evm_snapshot` and `evm_revert` RPC methods. Local development nodes commonly provide them; public networks generally do not. Without both methods, `anchor()` raises `RuntimeError`, and pytest tests must use `@pytest.mark.ignore_isolation`. That marker prevents snapshot errors but cannot revert transactions already broadcast.
