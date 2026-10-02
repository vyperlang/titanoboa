# Explorer configuration

## `set_etherscan`

!!! function "`boa.set_etherscan(uri=..., api_key=None, chain_id=1, **retry_options)`"

    Configure the `Etherscan` client used by `boa.from_etherscan()` and by
    Etherscan verification. The default endpoint is Etherscan API v2 and the
    default chain ID is Ethereum mainnet (`1`).

    The function returns a context-capable setting. Calling it normally keeps
    the new explorer configuration; using it in a `with` statement restores
    the previous configuration on exit.

    ```python
    import boa

    boa.set_etherscan(
        api_key="YOUR_ETHERSCAN_API_KEY",
        chain_id=1,
    )
    token = boa.from_etherscan(
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    )
    ```

    For temporary configuration:

    ```python
    with boa.set_etherscan(
        uri="https://api.etherscan.io/v2/api",
        api_key="YOUR_ETHERSCAN_API_KEY",
        chain_id=1,
    ):
        token = boa.from_etherscan(
            "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
        )
    ```

    Supported retry options include `num_retries`, `backoff_ms`, and
    `backoff_factor`. `chain_id` must be a positive integer.

## `from_etherscan`

!!! function "`boa.from_etherscan(address, name=None, uri=None, api_key=None, chain_id=None)`"

    Fetch the contract ABI, resolve one proxy implementation layer when
    reported by the explorer, and return an `ABIContract` attached to
    `address`.

    When both `uri` and `api_key` are omitted, Titanoboa uses the configured
    client. Passing either creates a new client: omitted settings use the
    `Etherscan` constructor defaults, not the configured client's values.
    Pass both arguments to retain a custom endpoint and API key; custom retry
    settings are not carried over.

    When `chain_id` is omitted, Titanoboa uses the active environment's chain
    ID. The selected client's chain ID is updated before fetching the ABI.
    When using the configured client, this update persists and also affects
    subsequent verification through that client.

See [Loading contracts](load_contracts.md#from_etherscan) for more examples.
