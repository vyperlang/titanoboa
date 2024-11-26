# Templates

Templates used throughout the documentation.

---

## Custom Admonitions

!!!vyper
    lorem ipsum dolor sit amet

!!!titanoboa
    lorem ipsum dolor sit amet

!!!moccasin
    lorem ipsum dolor sit amet

!!!python
    lorem ipsum dolor sit amet

---


## Function Documentation Template

Basic template for documenting functions. The link to the source code needs to be added manually. If no link is given, the GitHub emoji with the embedded link will not be rendered.
### `load`
!!! function "`load`"
    <a href="https://github.com/vyperlang/titanoboa/blob/v0.2.4/boa/interpret.py#L171-L177" class="source-code-link" target="_blank" rel="noopener"></a>

    **Signature**

    ```python
    load(
        fp: str,
        *args: Any,
        **kwargs: Any
    ) -> VyperContract | VyperBlueprint
    ```

    ---

    **Description**

    Compile source from disk and return a deployed instance of the contract.

    ---

    **Parameters**

    - `fp`: The contract source code file path.
    - `args`: Contract constructor arguments.
    - `kwargs`: Keyword arguments to pass to the [`boa.loads`](api/load_contracts.md#loads) function.

    ---

    **Returns**

    A [`VyperContract`](api/vyper_contract/overview.md) or [`VyperBlueprint`](api/vyper_blueprint/overview.md) instance.

    ---

    **Examples**

    === "Deployment"

        ```python
        >>> import boa
        >>> boa.load("Foo.vy")
        <tmp/Foo.vy at 0x0000000000000000000000000000000000000066, compiled with ...>
        ```

        ```python
        >>> import boa
        >>> from vyper.compiler.settings import OptimizationLevel, Settings
        >>> boa.load("Foo.vy", compiler_args={"settings": Settings(optimize=OptimizationLevel.CODESIZE)})
        <tmp/Foo.vy at 0xf2Db9344e9B01CB353fe7a2d076ae34A9A442513, compiled with ...>
        ```

    === "Foo.vy"

        ```vyper
        # Foo.vy
        @external
        def addition(a: uint256, b: uint256) -> uint256:
            return a + b
        ```