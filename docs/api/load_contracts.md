<h1>Loading contracts</h1>

Boa offers multiple ways to load contracts from various sources. Either from [local files](#from-local-files), [strings](#from-strings) or directly [from block explorer sources](#from-block-explorer-sources).

---

## **From local files**

### `load`
!!! function "`boa.load(filepath)`"
    <a href="https://github.com/vyperlang/titanoboa/blob/v0.2.4/boa/interpret.py#L171-L177" class="source-code-link" target="_blank" rel="noopener"></a>

    **Description**

    The `load` function is designed to compile a Vyper contract from a file located on disk. It provides a straightforward way to deploy contracts by reading the source code from the specified file path.

    ---

    **Parameters**

    - `filepath`: The contract source code file path.
    - `*args`: Contract constructor arguments.
    - `compiler_args: list = None`: Compiler arguments to be passed to the Vyper compiler.
    - `filename: str = None`: The filename of the contract source code or a related file.
    - `as_blueprint: bool = False`: Whether to deploy an [`eip-5202`](https://eips.ethereum.org/EIPS/eip-5202) blueprint of the compiled contract.
    - `value: int = 0`: The amount of cryptocurrency to send with the transaction (default is 0).
    - `env: Env = None`: The environment in which the contract is being deployed or executed.
    - `override_address: Address = None`: A different address for the contract deployment or interaction.
    - `skip_initcode: bool = False`: Whether to skip the execution of the contract's constructor code.
    - `created_from: Address = None`: The address from which the contract is created.
    - `gas: int = None`: The gas limit for the transaction.

    ---

    **Returns**

    A [`VyperContract`](vyper_contract/overview.md), [`VyperBlueprint`](vyper_blueprint/overview.md), or [`ABIContract`](abi_contract/overview.md) instance.

    If a legacy Vyper version is detected, an `ABIContract` may be returned due to VVM usage. See [Legacy Vyper Contracts](../explain/vvm_contracts.md) for more details.

    ---

    **Examples**

    ```python
    >>> import boa
    >>> # Basic contract loading
    >>> contract = boa.load("contracts/Token.vy", "MyToken", "TKN", 18, 1000000)
    >>>
    >>> # Load with specific compiler settings
    >>> contract = boa.load("contracts/Complex.vy", compiler_args={"optimize": "codesize"})
    >>>
    >>> # Load as blueprint
    >>> blueprint = boa.load("contracts/Factory.vy", as_blueprint=True)
    >>>
    >>> # Load with value (payable constructor)
    >>> contract = boa.load("contracts/Vault.vy", value=10**18)  # 1 ETH
    >>>
    >>> # Load at specific address (for testing upgrades)
    >>> contract = boa.load("contracts/V2.vy", override_address="0x1234...")
    ```

---

### `load_abi`
!!! function "`boa.load_abi(filename)`"
    <a href="https://github.com/vyperlang/titanoboa/blob/v0.2.4/boa/interpret.py#L196-L201" class="source-code-link" target="_blank" rel="noopener"></a>

    **Description**

    The `load_abi` function allows you to load a contract's ABI from a JSON file.

    ---

    **Parameters**

    - `filename`: The file containing the ABI as a JSON string (something like `my_abi.json`).
    - `*args`: Additional arguments.
    - `name`: The name of the contract (optional).

    ---

    **Returns**

    An [`ABIContract`](abi_contract/overview.md) instance.

    ---

    **Examples**

    ```python
    >>> import boa
    >>> # Fetch from Etherscan
    >>> usdc = boa.from_etherscan("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", name="USDC")
    >>>
    >>> # Use custom API key
    >>> contract = boa.from_etherscan(
    ...     "0x1234...",
    ...     api_key="YOUR_ETHERSCAN_API_KEY"
    ... )
    >>>
    >>> # Fetch from other explorers
    >>> contract = boa.from_etherscan(
    ...     "0x5678...",
    ...     uri="https://api.arbiscan.io/api",  # Arbitrum
    ...     api_key="YOUR_ARBISCAN_API_KEY"
    ... )
    ```

---

## **Cache Management**

Titanoboa includes a disk caching system to speed up contract compilation. Compiled contracts are cached based on their content hash.

### `set_cache_dir`
!!! function "`boa.set_cache_dir(path)`"

    **Description**

    Set the directory for caching compiled contracts. By default, contracts are cached in a system-appropriate location.

    ---

    **Parameters**

    - `path`: The directory path for storing cached contracts. Can be a string or Path object.

    ---

    **Examples**

    ```python
    >>> import boa
    >>> # Set custom cache directory
    >>> boa.set_cache_dir("~/.my_boa_cache")
    >>>
    >>> # Use Path object
    >>> from pathlib import Path
    >>> boa.set_cache_dir(Path.home() / ".cache" / "boa")
    ```

---

### `disable_cache`
!!! function "`boa.disable_cache()`"

    **Description**

    Disable the contract compilation cache. This forces recompilation of all contracts.

    ---

    **Examples**

    ```python
    >>> import boa
    >>> # Disable caching for debugging
    >>> boa.disable_cache()
    >>>
    >>> # All subsequent loads will recompile
    >>> contract = boa.load("MyContract.vy")  # Always recompiles
    ```

    ---

    **Note**

    Disabling cache can significantly slow down test suites and development workflows. Use sparingly.

---

## **Module System**

Titanoboa integrates with Python's import system, allowing you to import Vyper files directly.

### Direct Import

```python
# Assuming you have token.vy in your project
import token  # Imports token.vy

# Deploy the contract
deployed_token = token.deploy("MyToken", "TKN", 18, 1000000)
```

### Import with Custom Names

```python
# Import with alias
import token as MyToken

# Or use from import
from contracts import token, vault

# Deploy contracts
token_contract = token.deploy()
vault_contract = vault.deploy(token_contract.address)
```

### Module Search Path

Vyper files are searched in:
1. Current working directory
2. Directories in `sys.path`
3. Directories added via `boa.interpret.set_search_paths()`

```python
>>> import boa.interpret
>>> # Add custom search paths
>>> boa.interpret.set_search_paths(["/path/to/my/contracts"])
>>>
>>> # Now you can import from that directory
>>> import my_contract
```

---

### `load_partial`
!!! function "`boa.load_partial(filepath)`"
    <a href="https://github.com/vyperlang/titanoboa/blob/v0.2.4/boa/interpret.py#L261-L265" class="source-code-link" target="_blank" rel="noopener"></a>

    **Description**

    The `load_partial` function is used to compile a Vyper contract from a file and return a deployer instance.

    ---

    **Parameters**

    - `filepath`: The contract source code file path.
    - `compiler_args`: Argument to be passed to the Vyper compiler (optional).
    - `**kwargs`: Additional arguments like (`no_vvm`, `base_path`...).

    ---

    **Returns**

    A [`VyperDeployer`](vyper_deployer/overview.md) or [`VVMDeployer`](vvm_deployer/overview.md) instance.

    If a legacy Vyper version is detected, a `VVMDeployer` may be returned due to VVM usage. See [Legacy Vyper Contracts](../explain/vvm_contracts.md) for more details.

    ---

    **Examples**

    SOON

---

### `load_vyi`
!!! function "`boa.load_vyi(filename)`"
    <a href="https://github.com/vyperlang/titanoboa/blob/v0.2.4/boa/interpret.py#L211-L215" class="source-code-link" target="_blank" rel="noopener"></a>

    **Description**

    The `load_vyi` function is designed to load a Vyper interface from a `.vyi` file.

    ---

    **Parameters**

    - `filename`: The file containing the Vyper interface.
    - `name`: The name of the contract (optional).

    ---

    **Returns**

    An [`ABIContract`](abi_contract/overview.md) instance.

    ---

    **Examples**

    SOON

---

## **From strings**

### `loads`
!!! function "`boa.loads(source)`"
    <a href="https://github.com/vyperlang/titanoboa/blob/v0.2.4/boa/interpret.py#L180-L193" class="source-code-link" target="_blank" rel="noopener"></a>

    **Description**

    The `loads` function compiles Vyper source code provided as a string. This is useful for dynamic contract creation or testing scenarios where the source code is generated or modified at runtime.

    ---

    **Parameters**

    - `source`: The source code to compile and deploy.
    - `*args`: Contract constructor arguments.
    - `compiler_args: list = None`: Compiler arguments to be passed to the Vyper compiler.
    - `as_blueprint: bool = False`: Whether to deploy an [`eip-5202`](https://eips.ethereum.org/EIPS/eip-5202) blueprint of the compiled contract.
    - `value: int = 0`: The amount of cryptocurrency to send with the transaction (default is 0).
    - `env: Env = None`: The environment in which the contract is being deployed or executed.
    - `override_address: Address = None`: A different address for the contract deployment or interaction.
    - `skip_initcode: bool = False`: Whether to skip the execution of the contract's constructor code.
    - `created_from: Address = None`: The address from which the contract is created.
    - `gas: int = None`: The gas limit for the transaction.
    - `name`: The name of the contract.

    ---

    **Returns**

    A [`VyperContract`](vyper_contract/overview.md), [`VyperBlueprint`](vyper_blueprint/overview.md), or [`ABIContract`](abi_contract/overview.md) instance.

    If a legacy Vyper version is detected, an `ABIContract` may be returned due to VVM usage. See [Legacy Vyper Contracts](../explain/vvm_contracts.md) for more details.

    ---

    **Examples**

    SOON

---

### `loads_abi`
!!! function "`boa.loads_abi(json_str)`"
    <a href="https://github.com/vyperlang/titanoboa/blob/v0.2.4/boa/interpret.py#L204-L205" class="source-code-link" target="_blank" rel="noopener"></a>

    **Description**

    The `loads_abi` function creates an `ABIContract` from a JSON string representing the contract's ABI.

    ---

    **Parameters**

    - `json_str`: The ABI as a JSON string (something which can be passed to `json.loads()`).
    - `*args`: Additional arguments.
    - `name`: The name of the contract (optional).

    ---

    **Returns**

    An [`ABIContract`](abi_contract/overview.md) instance.

    **Examples**

    SOON

---

### `loads_partial`
!!! function "`boa.loads_partial(source)`"
    <a href="https://github.com/vyperlang/titanoboa/blob/v0.2.4/boa/interpret.py#L235-L258" class="source-code-link" target="_blank" rel="noopener"></a>

    **Description**

    The `loads_partial` function compiles Vyper source code provided as a string and returns a deployer instance. This function is useful for preparing contracts for deployment in environments where the source code is dynamically generated or modified.

    ---

    **Parameters**

    - `source`: The Vyper source code.
    - `name`: The name of the contract (optional).
    - `dedent`: If `True`, remove any common leading whitespace from every line in `source`.
    - `compiler_args`: Argument to be passed to the Vyper compiler (optional).
    - `no_vvm`: If `True`, do not use the Vyper Virtual Machine. (optional)
    - `base_path`: Path to the base directory for the contract (optional).

    ---

    **Returns**

    A [`VyperDeployer`](vyper_deployer/overview.md) or [`VVMDeployer`](vvm_deployer/overview.md) instance.

    If a legacy Vyper version is detected, a `VVMDeployer` may be returned due to VVM usage. See [Legacy Vyper Contracts](../explain/vvm_contracts.md) for more details.

    ---

    **Examples**

    SOON

---

### `loads_vyi`
!!! function "`boa.loads_vyi(source_code)`"
    <a href="https://github.com/vyperlang/titanoboa/blob/v0.2.4/boa/interpret.py#L218-L232" class="source-code-link" target="_blank" rel="noopener"></a>

    **Description**

    The `loads_vyi` function loads a Vyper interface from a string. This is useful for defining and using contract interfaces directly in code without needing separate interface files.

    ---

    **Parameters**

    - `source_code`: The Vyper interface source code as a string.
    - `name`: The name of the contract (optional).
    - `filename`: The filename for reference (optional).

    ---

    **Returns**

    An [`ABIContract`](abi_contract/overview.md) instance.

    ---

    **Examples**

    SOON

---

## **From block explorer sources**

### `from_etherscan`
!!! function "`boa.from_etherscan(address)`"
    <a href="https://github.com/vyperlang/titanoboa/blob/v0.2.4/boa/interpret.py#L289-L300" class="source-code-link" target="_blank" rel="noopener"></a>

    **Description**

    The `from_etherscan` function fetches the ABI for a contract at a given address from Etherscan and returns an `ABIContract` instance. This is particularly useful for interacting with contracts deployed on the Ethereum network when you have the contract address but not the source code.

    ---

    **Parameters**

    - `address`: The address. Can be str, bytes or Address.
    - `name`: The name of the contract (optional).
    - `uri`: The API endpoint URI (default: "https://api.etherscan.io/api").
    - `api_key`: The API key for Etherscan (optional).

    ---

    **Returns**

    An [`ABIContract`](abi_contract/overview.md) instance.

    ---

    **Examples**

    SOON
