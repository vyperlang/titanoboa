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

!!! function "`deploy_code(bytecode: bytes, *args, value=0, gas=None, sender=None) -> str`"

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

    The address of the deployed contract.

    ---

    **Example**

    ```python
    >>> import boa
    >>> bytecode = bytes.fromhex("608060...")
    >>> address = boa.env.deploy_code(bytecode)
    >>> print(f"Deployed at: {address}")
    ```

---

## `execute_code`

!!! function "`execute_code(to: str, data: bytes = b"", value: int = 0, gas: int = None, sender: str = None) -> bytes`"

    **Description**

    Execute a transaction on the network and return the result.

    ---

    **Parameters**

    - `to`: Target address
    - `data`: Calldata
    - `value`: ETH value to send
    - `gas`: Gas limit (auto-estimated if None)
    - `sender`: Sender address (uses env.eoa if None)

    ---

    **Returns**

    The return data from the transaction.

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

## `wait_for_tx_receipt`

!!! function "`wait_for_tx_receipt(tx_hash: str, timeout: float = None) -> dict`"

    **Description**

    Wait for a transaction receipt. Uses the timeout from `tx_settings.poll_timeout` if not specified.

    ---

    **Parameters**

    - `tx_hash`: The transaction hash to wait for
    - `timeout`: Custom timeout in seconds (optional)

    ---

    **Returns**

    The transaction receipt as a dictionary.

    ---

    **Example**

    ```python
    >>> import boa
    >>> tx_hash = contract.some_function()
    >>> receipt = boa.env.wait_for_tx_receipt(tx_hash)
    >>> print(f"Gas used: {receipt['gasUsed']}")
    ```

---

## `set_balance`

!!! function "`set_balance(address: str, value: int)`"

    **Description**

    Set the ETH balance of an address. Only works with local development networks that support `evm_setBalance`.

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

    This only works on local development networks (Anvil, Hardhat) that support the `evm_setBalance` RPC method.
