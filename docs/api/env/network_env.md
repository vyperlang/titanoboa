# NetworkEnv

Inherits: [`Env`](env.md)

### Description

NetworkEnv is a specialized environment for interacting with real or forked blockchain networks via RPC. It extends the base `Env` class with network-specific functionality including account management, transaction broadcasting, and state forking.

---

## `tx_settings`

!!! property "`boa.env.tx_settings`"

    **Description**

    Access and modify transaction settings for network interactions. These settings control gas estimation, transaction timeouts, and base fee calculations.

    ---

    **Attributes**

    - `base_fee_estimator_constant`: Number of blocks ahead to estimate base fee for (default: 5)
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
    >>> # Don't use block parameter for gas estimation (for certain RPC providers)
    >>> boa.env.tx_settings.estimate_gas_block_identifier = None
    ```

    ---

    **Note**

    These settings are particularly useful when dealing with network congestion or RPC provider quirks.

    The `base_fee_estimator_constant` determines how many blocks ahead to calculate the base fee cap. Since EIP-1559 allows base fee to increase by at most 12.5% per block, the maximum base fee after n blocks is calculated as: `current_base_fee * (9/8)^n`. For example, with the default value of 5, the base fee cap would be `current_base_fee * 1.8` (approximately). If you encounter errors like "max fee per gas less than block base fee", try increasing this value.

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
    - `describe_capabilities()`: Get a human-readable string describing the capabilities

    ---

    **Examples**

    ```python
    >>> import boa
    >>> boa.set_network_env("https://eth-mainnet.g.alchemy.com/v2/YOUR-KEY")
    >>>
    >>> # Check if Cancun features are available
    >>> if boa.env.capabilities.has_cancun:
    ...     print("Cancun features are supported")
    ... else:
    ...     print("Cancun features not available")
    ...
    >>> # Get human-readable description
    >>> print(boa.env.capabilities.describe_capabilities())
    'cancun'  # or 'shanghai', 'paris', etc.
    ```

    ---

    **Note**

    This is particularly useful when deploying contracts that use newer opcodes, as it prevents deployment failures on networks that don't support them yet.

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

## `fork`

!!! function "`fork(url: str, block_identifier: Union[int, str] = "safe", **kwargs)`"

    **Description**

    Fork the state from a remote network. This creates a local copy of the blockchain state that can be modified without affecting the real network.

    ---

    **Parameters**

    - `url`: The RPC URL to fork from
    - `block_identifier`: Block number or tag to fork from (default: "safe")
    - `**kwargs`: Additional arguments passed to Web3 provider

    ---

    **Example**

    ```python
    >>> import boa
    >>> # Fork mainnet at a specific block
    >>> boa.fork("https://eth-mainnet.g.alchemy.com/v2/YOUR-API-KEY", block_identifier=18000000)
    >>>
    >>> # Now you can interact with mainnet contracts
    >>> usdc = boa.from_etherscan("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "USDC")
    ```

---

## `deploy_code`

!!! function "`deploy_code(bytecode: bytes, *args, value=0, gas=None, sender=None) -> tuple[Address, bytes]`"

    **Description**

    Deploy contract bytecode to the network. Returns the deployed contract address.

    ---

    **Parameters**

    - `bytecode`: The deployment bytecode
    - `*args`: Constructor arguments
    - `value`: ETH value to send with deployment
    - `gas`: Gas limit (auto-estimated if None)
    - `sender`: Sender address (uses env.eoa if None)

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
    >>> address, runtime_bytecode = boa.env.deploy_code(bytecode)
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

    **Example**

    ```python
    >>> import boa
    >>> # Give an address 100 ETH
    >>> boa.env.set_balance("0x...", 100 * 10**18)
    ```

    ---

    **Note**

    This method raises `NotImplementedError` in NetworkEnv. To set balances in a test environment, use `boa.fork()` which returns a regular Env instance that supports balance manipulation.

---

## `sign_authorization`

!!! function "`sign_authorization(account, contract_address, nonce=None, chain_id=None)`"

    **Description**

    Sign an EIP-7702 authorization for an EOA to delegate its execution to smart contract code. When processed in a transaction, this sets the EOA's code to a delegation designator that points to the specified contract. The delegation is persistent and remains active until explicitly cleared or changed.

    ---

    **Parameters**

    - `account`: An account object with `sign_authorization` method (e.g., from eth_account library)
    - `contract_address`: Address of the contract whose code to execute, or a contract object with an `address` attribute
    - `nonce`: Authorization nonce (defaults to current EOA nonce)
    - `chain_id`: Chain ID for the authorization (defaults to current chain, use 0 for all chains)

    ---

    **Returns**

    A signed authorization dictionary that can be included in a transaction's `authorization_list`.

    ---

    **Example**

    ```python
    >>> import boa
    >>> from eth_account import Account
    >>>
    >>> # Deploy a smart wallet contract
    >>> wallet = boa.load("SmartWallet.vy")
    >>>
    >>> # Create and add an EOA
    >>> eoa = Account.create()
    >>> boa.env.add_account(eoa)
    >>>
    >>> # Sign authorization for EOA to execute wallet code
    >>> auth = boa.env.sign_authorization(
    ...     account=eoa,
    ...     contract_address=wallet,  # Can pass contract object directly
    ...     nonce=0  # First authorization for this EOA
    ... )
    >>>
    >>> # The authorization can now be used in transactions
    >>> result = some_contract.method(authorization_list=[auth])
    ```

    ---

    **Note**

    EIP-7702 delegations are persistent. Once an authorization is processed, the EOA's code is set to a delegation designator (`0xef0100` + contract address) that remains active until the EOA sends another authorization to change or clear it (by delegating to address `0x0`).

---

## `authorize`

!!! function "`authorize(account, contract_address)`"

    **Description**

    Activate EIP-7702 authorization for an EOA by sending a self-call transaction. This convenience method allows an EOA to delegate its execution to contract code. The delegation persists beyond the transaction and remains active until explicitly changed or cleared.

    ---

    **Parameters**

    - `account`: Account object or address of an account managed by the environment
    - `contract_address`: Address of the contract to delegate to, or a contract object

    ---

    **Returns**

    The result of the authorization transaction.

    ---

    **Example**

    ```python
    >>> import boa
    >>> from eth_account import Account
    >>>
    >>> # Create account and contract
    >>> alice = Account.create()
    >>> boa.env.add_account(alice)
    >>> wallet = boa.load("SmartWallet.vy")
    >>>
    >>> # Activate authorization for alice
    >>> boa.env.authorize(alice, wallet)
    >>>
    >>> # Now alice can be called as if it were the wallet contract
    >>> # (within the same transaction context)
    ```

    ---

    **Note**

    This method sends a transaction from the EOA to itself with the authorization, establishing a persistent delegation. The EOA will continue to execute the delegated contract's code in all future transactions until the delegation is changed or cleared. For more complex use cases involving multiple authorizations or specific calldata, use the `authorization_list` parameter available on contract call methods.

---

## `execute_with_authorizations`

!!! function "`execute_with_authorizations(authorizations, target=None, data=b"", **kwargs)`"

    **Description**

    Execute a transaction with one or more EIP-7702 authorizations. This is a convenience method for sending transactions where EOAs need to delegate to contract code.

    ---

    **Parameters**

    - `authorizations`: List of either:
        - Signed authorization dicts (from `sign_authorization`)
        - `(account, contract_address)` tuples to auto-sign
    - `target`: Target address for the transaction (optional)
    - `data`: Transaction data (optional)
    - `**kwargs`: Additional transaction parameters (sender, value, gas, etc.)

    ---

    **Returns**

    The computation result from executing the transaction.

    ---

    **Example**

    ```python
    >>> import boa
    >>> from eth_account import Account
    >>>
    >>> # Example 1: Simple auto-signing with tuples
    >>> wallet = boa.load("SmartWallet.vy")
    >>> alice = Account.create()
    >>> boa.env.add_account(alice)
    >>>
    >>> # Execute with auto-signed authorization
    >>> result = boa.env.execute_with_authorizations(
    ...     [(alice, wallet)],  # Auto-signs authorization
    ...     target=some_contract.address,
    ...     data=some_contract.method.prepare_calldata(args)
    ... )
    >>>
    >>> # Example 2: Multi-party delegation
    >>> defi_protocol = boa.load("DefiProtocol.vy")
    >>> bob = Account.create()
    >>> carol = Account.create()
    >>> boa.env.add_account(bob)
    >>> boa.env.add_account(carol)
    >>>
    >>> # Option 1: Simple tuple syntax (auto-signs)
    >>> boa.env.execute_with_authorizations(
    ...     [(alice, defi_protocol), (bob, defi_protocol), (carol, defi_protocol)],
    ...     target=defi_protocol.address,
    ...     data=defi_protocol.initialize.prepare_calldata(),
    ...     sender=alice.address
    ... )
    >>>
    >>> # Option 2: Manual signing (for advanced control)
    >>> auth_alice = boa.env.sign_authorization(alice, defi_protocol, nonce=1)
    >>> auth_bob = boa.env.sign_authorization(bob, defi_protocol, chain_id=1)
    >>> auth_carol = boa.env.sign_authorization(carol, defi_protocol)
    >>>
    >>> boa.env.execute_with_authorizations(
    ...     [auth_alice, auth_bob, auth_carol],
    ...     target=defi_protocol.address
    ... )
    ```

    ---

    **Note**

    This method is particularly useful for testing account abstraction patterns and multi-party protocols where multiple EOAs need to delegate atomically.
