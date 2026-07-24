# Loading contracts

Titanoboa can compile Vyper source from files or strings, load ABI and Vyper
interfaces, and fetch deployed contract ABIs from block explorers.

## Vyper source

### `load`

!!! function "`boa.load(filename, *constructor_args, **kwargs)`"

    Compile a Vyper file and deploy it.

    Common keyword arguments include:

    - `compiler_args: dict | None`: Vyper compiler settings.
    - `as_blueprint: bool`: Deploy an EIP-5202 blueprint.
    - `value: int`: Wei sent to the constructor.
    - `name: str`: Override the contract name inferred from the filename.
    - `no_vvm: bool`: Disable compilation through VVM for version-pinned source.
    - deployment options such as `sender`, `gas`, `override_address`, and
      `skip_initcode`.

    The result is a deployed `VyperContract` or `VyperBlueprint`. Source pinned
    to a different supported Vyper version may use VVM and return its
    ABI-backed contract type.

    ```python
    import boa
    from vyper.compiler.settings import OptimizationLevel

    token = boa.load("contracts/Token.vy", "My Token", "TKN")
    compact = boa.load(
        "contracts/Compact.vy",
        compiler_args={"optimize": OptimizationLevel.CODESIZE},
    )
    blueprint = boa.load("contracts/Factory.vy", as_blueprint=True)
    ```

### `loads`

!!! function "`boa.loads(source_code, *constructor_args, **kwargs)`"

    Compile Vyper source from a string and deploy it. It accepts the same
    compilation and deployment options as `load`, plus `filename`, which is
    used for diagnostics and import resolution. The source is dedented before
    compilation.

    ```python
    import boa
    from vyper.compiler.settings import OptimizationLevel

    counter = boa.loads(
        """
    stored_value: public(uint256)

    @deploy
    def __init__(initial_value: uint256):
        self.stored_value = initial_value
    """,
        42,
        name="Counter",
        compiler_args={"optimize": OptimizationLevel.GAS},
    )

    assert counter.stored_value() == 42
    ```

## Undeployed Vyper contracts

### `load_partial`

!!! function "`boa.load_partial(filename, compiler_args=None)`"

    Compile a Vyper file and return a `VyperDeployer` (or a `VVMDeployer` for
    source requiring VVM) without deploying it.

    ```python
    import boa

    Counter = boa.load_partial("contracts/Counter.vy")
    first = Counter.deploy(1)
    second = Counter.deploy(2)
    ```

    A deployer is also callable, so `Counter(1)` is equivalent to
    `Counter.deploy(1)`.

### `loads_partial`

!!! function "`boa.loads_partial(source_code, name=None, filename=None, dedent=True, compiler_args=None, no_vvm=False)`"

    Compile Vyper source from a string and return an undeployed deployer.

    ```python
    import boa

    Counter = boa.loads_partial(
        """
    stored_value: public(uint256)

    @deploy
    def __init__(initial_value: uint256):
        self.stored_value = initial_value
    """,
        name="Counter",
    )

    counter = Counter.deploy(7)
    assert counter.stored_value() == 7
    ```

## JSON ABIs

`load_abi` and `loads_abi` return an `ABIContractFactory`, not a deployed
contract. Couple the factory to an existing address with `.at(address)`.

### `load_abi`

!!! function "`boa.load_abi(filename, name=None)`"

    Read a JSON ABI from a file.

    ```python
    import boa

    ERC20 = boa.load_abi("interfaces/ERC20.json", name="ERC20")
    token = ERC20.at("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
    ```

### `loads_abi`

!!! function "`boa.loads_abi(json_str, name=None)`"

    Parse a JSON string containing an ABI. Pass serialized JSON, not a Python
    list.

    ```python
    import json

    import boa

    abi = [
        {
            "type": "function",
            "name": "balanceOf",
            "stateMutability": "view",
            "inputs": [{"name": "account", "type": "address"}],
            "outputs": [{"name": "", "type": "uint256"}],
        }
    ]

    ERC20 = boa.loads_abi(json.dumps(abi), name="ERC20")
    token = ERC20.at("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
    ```

## Vyper interfaces

Vyper interface loaders also return an `ABIContractFactory`.

### `load_vyi`

!!! function "`boa.load_vyi(filename, name=None)`"

    Compile a `.vyi` file into an interface factory.

    ```python
    import boa

    ERC20 = boa.load_vyi("interfaces/ERC20.vyi")
    token = ERC20.at("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
    ```

### `loads_vyi`

!!! function "`boa.loads_vyi(source_code, name=None, filename=None)`"

    Compile a Vyper interface from a string.

    ```python
    import boa

    ERC20 = boa.loads_vyi(
        """
    @external
    @view
    def balanceOf(account: address) -> uint256:
        ...
    """,
        name="ERC20",
    )

    token = ERC20.at("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
    ```

## Block explorer ABIs

### `from_etherscan`

!!! function "`boa.from_etherscan(address, name=None, uri=None, api_key=None, chain_id=None)`"

    Fetch an ABI through an Etherscan-compatible API and return an
    `ABIContract` attached to `address`.

    When `chain_id` is omitted, Titanoboa uses the active environment's chain
    ID. The default explorer endpoint is Etherscan API v2. Configure explorer
    defaults with `boa.set_etherscan(...)`, or pass `uri`, `api_key`, and
    `chain_id` for a one-off request.

    ```python
    import boa

    with boa.set_etherscan(api_key="YOUR_ETHERSCAN_API_KEY"):
        usdc = boa.from_etherscan(
            "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            name="USDC",
            chain_id=1,
        )
    ```

    A custom Etherscan-compatible endpoint can be selected explicitly:

    ```python
    contract = boa.from_etherscan(
        "0x1234567890123456789012345678901234567890",
        uri="https://api.etherscan.io/v2/api",
        api_key="YOUR_API_KEY",
        chain_id=1,
    )
    ```

## Native Python imports

After `import boa` installs Titanoboa's importer, `.vy` files visible on
Python's `sys.path` can be imported as deployer objects:

```python
import boa
from contracts import token

deployed_token = token.deploy("My Token", "TKN")
```

Use `boa.interpret.set_search_paths([...])` to configure Vyper compiler import
paths. This setting affects Vyper import resolution; Python's native import
mechanism continues to search `sys.path`.
