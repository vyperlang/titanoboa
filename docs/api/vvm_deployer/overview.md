# `VVMDeployer`

### Description

The `VVMDeployer` class provides functionality for deploying smart contracts for older Vyper versions via the [Vyper Version Manager (VVM)](http://github.com/vyperlang/vvm).
It includes methods for handling contract deployment, execution, and interaction.

### Methods
<!-- TODO use the !!!function syntax for the functions -->

- [\_\_init\_\_](\_\_init\_\_.md)
- [from_compiler_output](from_compiler_output.md)
- [factory](factory.md)
- [constructor](constructor.md)
- [deploy](deploy.md)
- [\_\_call\_\_](\_\_call\_\_.md)
- [at](at.md)

### Examples

!!!python

    ```python
    deployer = boa.loads_partial("""
    # pragma version 0.3.10

    foo: public(uint256)
    bar: public(uint256)

    @external
    def __init__(bar: uint256):
        self.foo = 42
        self.bar = bar
    """)
    contract = deployer.deploy()

    >>> type(deployer)
    <class 'boa.contracts.vvm.vvm_contract.VVMDeployer'>

    >>> type(contract)
    <class 'boa.contracts.vvm.vvm_contract.VVMContract'>
    ```


!!! warning

    Titanoboa will automatically read the version pragma in the source code and install the right compiler version via `vvm`
