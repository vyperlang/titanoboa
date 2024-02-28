API Reference
=============

High-Level Functionality
------------------------

.. module:: boa

.. py:data:: env
    :type: boa.environment.Env

    The global environment object.

.. function:: load(fp: str, *args: Any, **kwargs: Any) -> VyperContract | VyperBlueprint

    Compile source from disk and return a deployed instance of the contract.

    :param fp: The contract source code file path.
    :param args: Contract constructor arguments.
    :param kwargs: Keyword arguments to pass to the :py:func:`loads` function.

    .. rubric:: Example

    .. code-block:: python

        # Foo.vy
        @external
        def addition(a: uint256, b: uint256) -> uint256:
            return a + b

    .. code-block:: python

        >>> import boa
        >>> boa.load("Foo.vy")
        <tmp/Foo.vy at 0x0000000000000000000000000000000000000066, compiled with ...>

    .. code-block:: python

        >>> import boa
        >>> from vyper.compiler.settings import OptimizationLevel, Settings
        >>> boa.load("Foo.vy", compiler_args={"settings": Settings(optimize=OptimizationLevel.CODESIZE)})
        <tmp/Foo.vy at 0xf2Db9344e9B01CB353fe7a2d076ae34A9A442513, compiled with ...>

.. function:: loads(source: str, *args: Any, as_blueprint: bool = False, name: str | None = None, compiler_args: dict | None = None, **kwargs) -> VyperContract | VyperBlueprint

    Compile source code and return a deployed instance of the contract.

    :param source: The source code to compile and deploy.
    :param args: Contract constructor arguments.
    :param as_blueprint: Whether to deploy an :eip:`5202` blueprint of the compiled contract.
    :param name: The name of the contract.
    :param compiler_args: Argument to be passed to the Vyper compiler.
    :param kwargs: Keyword arguments to pass to the :py:class:`VyperContract` or :py:class:`VyperBlueprint` ``__init__`` method.

    .. rubric:: Example

    .. code-block:: python

        >>> import boa
        >>> src = """
        ... value: public(uint256)
        ... @external
        ... def __init__(_initial_value: uint256):
        ...     self.value = _initial_value
        ... """
        >>> boa.loads(src, 69)
        <VyperContract at 0x0000000000000000000000000000000000000066, compiled with ...>

.. function:: load_partial(fp: str, compiler_args: dict | None = None) -> VyperDeployer

    Compile source from disk and return a :py:class:`VyperDeployer`.

    :param fp: The contract source code file path.
    :param compiler_args: Argument to be passed to the Vyper compiler.
    :returns: A :py:class:`VyperDeployer` factory instance.

    .. rubric:: Example

    .. code-block:: python

        # Foo.vy
        @external
        def addition(a: uint256, b: uint256) -> uint256:
            return a + b

    .. code-block:: python

        >>> import boa
        >>> boa.load_partial("Foo.vy")
        <boa.vyper.contract.VyperDeployer object at ...>

.. function:: loads_partial(source: str, name: str | None = None, dedent: bool = True, compiler_args: dict | None = None) -> VyperDeployer

    Compile source and return a :py:class:`VyperDeployer`.

    :param source: The Vyper source code.
    :param name: The name of the contract.
    :param dedent: If `True`, remove any common leading whitespace from every line in `source`.
    :param compiler_args: Argument to be passed to the Vyper compiler.
    :returns: A :py:class:`VyperDeployer` factory instance.

    .. rubric:: Example

    .. code-block:: python

        >>> import boa
        >>> src = """
        ... @external
        ... def main():
        ...     pass
        ... """
        >>> boa.loads_partial(src, "Foo")
        <boa.vyper.contract.VyperDeployer object at ...>


.. function:: load_abi(filename: str, name: str = None) -> ABIContractFactory

    Return a :py:class:`ABIContractFactory` from an ABI file (.json)

    :param filename: The file containing the ABI as a JSON string (something like ``my_abi.json``)
    :param name: The name of the contract.
    :returns: A :py:class:`ABIContractFactory` factory instance.

    .. rubric:: Example

    .. code-block:: python

        >>> import boa
        >>> filename = "foo.json"
        >>> boa.load_abi(src, name="Foo")
        <boa.vyper.contract.ABIContractFactory at 0x7ff0f14a1550>


.. function:: loads_abi(json_str: str, name: str = None) -> ABIContractFactory

    Return a :py:class:`ABIContractFactory` from an ABI string

    :param json_str: The ABI as a JSON string (something which can be passed to ``json.loads()``)
    :param name: The name of the contract.
    :returns: A :py:class:`ABIContractFactory` factory instance.

    .. rubric:: Example

    .. code-block:: python

        >>> import boa
        >>> src = """[{"stateMutability": "nonpayable", "type": "function", "name": "foo", "inputs": [{"name": "", "type": "bytes"}], "outputs": [{"name": "", "type": "bytes"}]}]"""
        >>> boa.loads_abi(src, name="Foo")
        <boa.vyper.contract.ABIContractFactory at 0x7ff0f14a1550>


.. function:: from_etherscan(address: str | bytes | Address, name: str = None, uri: str = "https://api.etherscan.io/api", api_key: str = None) -> ABIContract

    Fetch the ABI for an address from etherscan and return an :py:class:`ABIContract`

    :param address: The address. Can be str, bytes or Address
    :param name: (Optional) The name of the contract.
    :returns: A :py:class:`ABIContract` instance.

    .. rubric:: Example

    .. code-block:: python

        >>> import boa, os
        >>> boa.env.fork(os.environ["ALCHEMY_MAINNET_ENDPOINT"])
        >>> crvusd = boa.from_etherscan("0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E", name="crvUSD")
        >>> crvusd
        <crvUSD interface at 0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E>
        >>> crvusd.totalSupply()
        730773174461124520709282012


.. function:: eval(statement: str) -> Any

    Evaluate a Vyper statement in the context of a contract with no state.

    :param statement: A valid Vyper statement.
    :returns: The result of the statement execution.

    .. rubric:: Example

    .. code-block:: python

        >>> import boa
        >>> boa.eval("keccak256('Hello World!')").hex()
        '3ea2f1d0abf3fc66cf29eebb70cbd4e7fe762ef8a09bcc06c8edf641230afec0'
        >>> boa.eval("empty(uint256[10])")
        (0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

.. function:: reverts(reason: str | None = None, /, **kwargs: str)

    A context manager which validates an execution error occurs with optional reason matching.

    .. note::

        If a keyword argument is provided, as opposed to a positional argument, the argument
        name and value will be used to validate against a developer revert comment.

    :param reason: A string to match against the execution error.
    :param compiler: A string to match against the internal compiler revert reason.
    :param vm_error: A string to match against the revert reason string.
    :raises AssertionError: If there is more than one argument.
    :raises ValueError: If the execution did not have an error.
    :raises ValueError: If the reason string provided does not match the error that occurred.

    .. rubric:: Examples

    Revert reason provided as a positional argument:

    .. code-block:: python

        import boa

        source = """
        @external
        def foo():
            raise "0xdeadbeef"

        @external
        def bar():
            raise  # dev: 0xdeadbeef
        """
        contract = boa.loads(source)

        with boa.reverts("0xdeadbeef"):
            contract.foo()

        with boa.reverts("0xdeadbeef"):
            contract.bar()

    Compiler revert reason:

    .. code-block:: python

        import boa

        source = """
        @external
        def subtract(a: uint256, b: uint256) -> uint256:
            return a - b

        @external
        def addition(a: uint256, b: uint256) -> uint256:
            return a + b
        """
        contract = boa.loads(source)

        with boa.reverts(compiler="safesub"):
            contract.subtract(1, 2)

        with boa.reverts(compiler="safeadd"):
            contract.addition(1, 2**256 - 1)

    VM error reason:

    .. code-block:: python

        import boa

        source = """
        @external
        def main(a: uint256):
            assert a == 0, "A is not 0"
        """
        contract = boa.loads(source)

        with boa.reverts(vm_error="A is not 0"):
            contract.main(69)

    Developer revert comment:

    .. code-block:: python

        import boa

        source = """
        @external
        def main(a: uint256):
            assert a == 0  # dev: a is not 0
        """
        contract = boa.loads(source)

        with boa.reverts(dev="a is not 0"):
            contract.main(69)

.. function:: register_precompile(address: str, fn: Callable[[eth.abc.ComputationAPI], None], force: bool = False)

    Register a precompile.

    :param address: The address to register the precompile at.
    :param fn: The function to execute when the precompile is called.
    :param force: Whether to overwrite the precompile function if one is already registered at the specified address.
    :raises ValueError: If a precompile is already registered at the specified address and the force argument is ``False``.

    .. rubric:: Example

    .. code-block:: python

        >>> import boa
        >>> log = lambda computation: print("0x" + computation.msg.sender.hex())
        >>> boa.register_precompile("0x00000000000000000000000000000000000000ff", log)
        >>> boa.eval("raw_call(0x00000000000000000000000000000000000000ff, b'')")
        0x0000000000000000000000000000000000000069

.. function:: deregister_precompile(address: str, force: bool = True)

    Deregister a precompile.

    :param address: The address of a previously registered precompile.
    :param force: Whether to force removal of the precompile at the specified address.
    :raises ValueError: If a precompile is not registered at the specified address and the force argument is ``False``.

.. function:: patch_opcode(opcode: int, fn: Callable[[eth.abc.ComputationAPI], None])

    Patch an opcode.

    :param opcode: The opcode to patch.
    :param fn: The function implementing the desired opcode functionality.

    .. note::

        The function provided as an argument should be defined with a single keyword parameter, ``computation``, like so:

        .. code-block:: python

            def baz(computation: eth.abc.ComputationAPI):
                ...

    .. rubric:: Example

    The following code snippet implements tracing for the ``CREATE`` opcode and stores all
    newly created accounts in a list.

    .. code-block:: python

        # example.py
        import boa

        class CreateTracer:
            def __init__(self, super_fn):
                """Track addresses of contracts created via the CREATE opcode.

                Parameters:
                    super_fn: The original opcode implementation.
                """
                self.super_fn = super_fn
                self.trace = []

            def __call__(self, computation):
                # first, dispatch to the original opcode implementation provided by py-evm
                self.super_fn(computation)
                # then, store the output of the CREATE opcode in our `trace` list for later
                self.trace.append("0x" + computation._stack.values[-1][-1].hex())

        if __name__ == "__main__":
            create_tracer = CreateTracer(boa.env.vm.state.computation_class.opcodes[0xf0])
            boa.patch_opcode(0xf0, create_tracer)

            source = """
        @external
        def main():
            for _ in range(10):
                addr: address = create_minimal_proxy_to(self)
            """
            contract = boa.loads(source)
            contract.main()  # execute the contract function
            print(create_tracer.trace)

    Running the code would produce the following results:

    .. code-block:: bash

        $ python example.py
        [
            "0xd130b7e7f212ecadcfcca3cecc89f85ce6465896",
            "0x37fdb059bf647b88dbe172619f00b8e8b1cf9338",
            "0x40bcd509b3c1f42d535d1a8f57982729d4b52adb",
            "0xaa35545ac7a733600d658c3f516ce2bb2be99866",
            "0x29e303d13a16ea18c6b0e081eb566b55a74b42d6",
            "0x3f69d814da1ebde421fe7dc99e24902b15af960b",
            "0x719c0dc21639008a2855fdd13d0d6d89be53f991",
            "0xf6086a85f5433f6fbdcdcf4f2ace7915086a5130",
            "0x097dec6ea6b9eb5fc04db59c0d343f0e3b4097a0",
            "0x905794c5566184e642ef14fb0e72cf68ff8c79bf"
        ]

Low-Level Functionality
-----------------------

.. module:: boa.environment

.. class:: Env

    A wrapper class around py-evm which provides a "contract-centric" API.

    .. attribute:: eoa
        :type: str

        The account to use as ``msg.sender`` for top-level calls and ``tx.origin`` in the context of state mutating function calls.

    .. attribute:: chain
        :type: eth.abc.ChainAPI

        The global py-evm chain instance.

    .. method:: alias(address: str, name: str) -> None

        Associates an alias with an address. This is useful to make the address more human-readable in tracebacks.

        :param address: The address to alias.
        :param name: The alias to use for the address.

    .. method:: generate_address(alias: str | None = None) -> str

        Generate an address and optionally alias it.

        :param alias: The alias to use for the generated address.

        .. rubric:: Example

        .. code-block:: python

            >>> import boa
            >>> boa.env.generate_address()
            '0xd13f0Bd22AFF8176761AEFBfC052a7490bDe268E'

    .. method:: set_random_seed(seed: Any = None) -> None

        Set the random seed used by this ``Env`` to generate addresses. Useful in case you want to introduce some more randomization to how ``Env`` generates addresses.

        :param seed: The seed to pass to this ``Env``'s instance of ``random.Random``. Can be any value that ``random.Random()`` accepts.

        .. rubric:: Example

     .. code-block:: python

            >>> import boa
            >>> boa.env.set_random_seed(100)
            >>> boa.env.generate_address()
            '0x93944a25b3ADa3759918767471C5A3F3601652c5

    .. method:: set_balance(address: str, value: int)

        Set the ether balance of an account.

    .. method:: get_balance(address: str) -> int

        Get the ether balance of an account.

    .. method:: fork(provider: str, **kwargs: Any)

        Fork the state of an external node allowing local simulation of state mutations.

        :param provider: The URL of the node provider to fork the state of.
        :param block_identifier: The block identifier to fork the state at. The value may be an integer, bytes, a hexadecimal string or a pre-defined block identifier (``"earliest"`` , ``"latest"``, ``"pending"``, ``"safe"`` or ``"finalized"``). Defaults to ``"safe"``.

        .. rubric:: Example

        .. code-block:: python

            >>> import boa
            >>> boa.env.vm.state.block_number
            1
            >>> boa.env.fork("https://rpc.ankr.com/eth")
            >>> boa.env.vm.state.block_number
            16038471

    .. method:: anchor()

        A context manager which snapshots the state and the vm, and reverts to the snapshot on exit.

        .. rubric:: Example

        .. code-block:: python

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

    .. method:: prank(address: str)

        A context manager which temporarily sets :py:attr:`eoa` and resets it on exit.

        .. rubric:: Example

        .. code-block::

            >>> import boa
            >>> boa.env.eoa
            '0x0000000000000000000000000000000000000065'
            >>> with boa.env.prank("0x00000000000000000000000000000000000000ff"):
            ...     boa.env.eoa
            ...
            '0x00000000000000000000000000000000000000ff'
            >>> boa.env.eoa

    .. method:: deploy_code(at: str = "0x0000000000000000000000000000000000000000", sender: str | None = None, gas: int | None = None, value: int = 0, bytecode: bytes = b"", data: bytes = b"", pc: int = 0) -> bytes

        Deploy bytecode at a specific account.

        :param at: The account the deployment bytecode will run at.
        :param sender: The account to set as ``tx.origin`` for the execution context and ``msg.sender`` for the top-level call.
        :param gas: The gas limit provided for the execution (a.k.a. ``msg.gas``).
        :param value: The ether value to attach to the execution (a.k.a ``msg.value``).
        :param bytecode: The deployment bytecode.
        :param data: The data to attach to the execution (a.k.a. ``msg.data``).
        :param pc: The program counter to start the execution at.
        :returns: The return value from the top-level call (typically the runtime bytecode of a contract).

        .. rubric:: Example

        .. code-block:: python

            >>> import boa
            >>> code = bytes.fromhex("333452602034f3")  # simply returns the caller
            >>> boa.env.deploy_code(bytecode=code, sender="0x0000000022D53366457F9d5E68Ec105046FC4383").hex()
            '0000000000000000000000000000000022d53366457f9d5e68ec105046fc4383'
            >>> boa.env.vm.state.get_code(b"\x00" * 20).hex()
            '0000000000000000000000000000000022d53366457f9d5e68ec105046fc4383'

    .. method:: execute_code(at: str = "0x0000000000000000000000000000000000000000", sender: str | None = None, gas: int | None = None, value: int = 0, bytecode: bytes = b"", data: bytes = b"", pc: int = 0) -> bytes

        Execute bytecode at a specific account.

        :param at: The account to target.
        :param sender: The account to set as ``tx.origin`` for the execution context and ``msg.sender`` for the top-level call.
        :param gas: The gas limit provided for the execution (a.k.a. ``msg.gas``).
        :param value: The ether value to attach to the execution (a.k.a ``msg.value``).
        :param bytecode: The runtime bytecode.
        :param data: The data to attach to the execution (a.k.a. ``msg.data``).
        :param pc: The program counter to start the execution at.
        :returns: The return value from the top-level call.

    .. method:: raw_call(to_address: str, sender: str | None = None, gas: int | None = None, value: int = 0, data: bytes = b"") -> bytes

        Simple wrapper around `execute_code`, to execute as if the contract is being called from an EOA.

        :param to_address: The contract to target.
        :param sender: The account to set as ``tx.origin`` for the execution context and ``msg.sender`` for the top-level call.
        :param gas: The gas limit provided for the execution (a.k.a. ``msg.gas``).
        :param value: The ether value to attach to the execution (a.k.a ``msg.value``).
        :param data: The data to attach to the execution (a.k.a. ``msg.data``).
        :returns: The return value from the top-level call.

    .. method:: time_travel(seconds: int = None, blocks: int = None, block_delta: int = 12)

        Fast forward, increase the chain timestamp and block number.

        :param seconds: Change current timestamp by `seconds` seconds.
        :param blocks: Change block number by `blocks` blocks.
        :param block_delta: The time between two blocks. Set to 12 as default.

.. module:: boa.vyper.contract

.. class:: VyperDeployer

    Vyper contract factory.

    .. method:: at(address: str) -> VyperContract

        Return a :py:class:`VyperContract` instance for a contract deployed at the provided address.

        :param address: The address of the contract.
        :returns: A contract instance.

        .. rubric:: Example

        .. code-block:: python

            >>> import boa
            >>> src = """
            ... @external
            ... def main():
            ...     pass
            ... """
            >>> ContractFactory = boa.loads_partial(src, "Foo")
            >>> ContractFactory.at("0xD130B7E7F212ECADCfcCa3cecC89f85ce6465896")
            <Foo at 0xD130B7E7F212ECADCfcCa3cecC89f85ce6465896, compiled with ...>

    .. method:: deploy(*args: Any, **kwargs: Any) -> VyperContract

        Deploy a new contract.

        :param args: The contract constructor arguments.
        :param kwargs: Keyword arguments to pass to the :py:class:`VyperContract` ``__init__`` method.

        .. rubric:: Example

        .. code-block:: python

            >>> import boa
            >>> src = """
            ... @external
            ... def main():
            ...     pass
            ... """
            >>> ContractFactory = boa.loads_partial(src, "Foo")
            >>> ContractFactory.deploy()
            <Foo at 0x0000000000000000000000000000000000000066, compiled with ...>

    .. method:: deploy_as_blueprint(*args: Any, **kwargs: Any) -> VyperBlueprint

        Deploy a new :eip:`5202` blueprint instance.

        :param args: Positional arguments to pass to the :py:class:`VyperBlueprint` ``__init__`` method.
        :param kwargs: Keyword arguments to pass to the :py:class:`VyperBlueprint` ``__init__`` method.

        .. rubric:: Example

        .. code-block:: python

            >>> import boa
            >>> src = """
            ... @external
            ... def main():
            ...     pass
            ... """
            >>> ContractFactory = boa.loads_partial(src, "Foo")
            >>> ContractFactory.deploy_as_blueprint()
            <boa.vyper.contract.VyperBlueprint object at ...>

.. class:: VyperContract

    A contract instance.

    Internal and external contract functions are available as methods on :py:class:`VyperContract` instances.

    .. rubric:: Example

    .. code-block:: python

        >>> import boa
        >>> src = """
        ... @external
        ... def main():
        ...     pass
        ...
        ... @internal
        ... def foo() -> uint256:
        ...     return 123
        ... """
        >>> contract = boa.loads(src)
        >>> type(contract.main)
        <class 'boa.vyper.contract.VyperFunction'>
        >>> type(contract.foo)
        <class 'boa.vyper.contract.VyperInternalFunction'>
        >>> contract.internal.foo()
        123

    .. method:: eval(statement: str, value: int = 0, gas: int | None = None, sender: str | None = None) -> Any

        Evaluate a Vyper statement in the context of the contract.

        :param statement: A vyper statment.
        :param value: The ether value to attach to the statement evaluation (a.k.a ``msg.value``).
        :param gas: The gas limit provided for statement evaluation (a.k.a. ``msg.gas``).
        :param sender: The account which will be the ``tx.origin``, and ``msg.sender`` in the context of the evaluation.
        :returns: The result of the statement evaluation.

        .. rubric:: Example

        .. code-block:: python

            >>> import boa
            >>> src = "value: public(uint256)"
            >>> contract = boa.loads(src)
            >>> contract.value()
            0
            >>> contract.eval("self.value += 1")
            >>> contract.value()
            1

    .. property:: deployer
        :type: VyperDeployer

.. class:: VyperBlueprint

    Stub class for :eip:`5202` blueprints.

    .. property:: address
        :type: str

.. class:: VyperFunction

    .. .. method:: args_abi_type(nkwargs: int)

    ..     :param nkwargs: The number of keyword arguments to include when calculating the signature.
    ..     :returns: A tuple containing the function's method id and the ABI schema of the function's arguments.
    ..     :rtype: tuple[bytes, str]

    ..     .. rubric:: Example

    ..     .. code-block:: python

    ..         >>> import boa
    ..         >>> src = """
    ..         ... @external
    ..         ... def main(a: uint256, b: uint256 = 0) -> uint256:
    ..         ...     return a + b
    ..         ... """
    ..         >>> contract = boa.loads(src)
    ..         >>> contract.main.args_abi_type(0)
    ..         (b'\xab:\xe2U', '(uint256)')
    ..         >>> contract.main.args_abi_type(1)
    ..         (b'\xccW,\xf9', '(uint256,uint256)')

    .. method:: prepare_calldata(*args: Any, **kwargs: Any) -> bytes:
        Prepare the calldata that a function call would use.
        This is useful for saving calldata for use in a transaction later.

        :param args: The positional arguments of the contract function.
        :param kwargs: Keyword arguments of the contract function.

        :returns: The calldata that a call with a particular set of arguments would use, in bytes.

        .. rubric:: Example

        .. code-block:: python

            >>> import boa
            >>> src = """
            ... @external
            ... def main(a: uint256) -> uint256:
            ...     return 1 + a
            ... """
            >>> c = boa.loads(src)
            >>> contract.main.prepare_calldata(68)
            b'\xab:\xe2U\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x0D'


    .. method:: __call__(*args: Any, value: int = 0, gas: int | None = None, sender: str | None = None, **kwargs: Any) -> Any

        Execute the function.

        :param args: The positional arguments of the contract function.
        :param value: The ether value to attach to the execution of the function (a.k.a ``msg.value``).
        :param gas: The gas limit provided for function execution (a.k.a. ``msg.gas``).
        :param sender: The account which will be the ``tx.origin`` of the execution, and ``msg.sender`` of the top-level call.
        :param kwargs: Keyword arguments of the contract function.
        :returns: The result of the function.

        .. rubric:: Example

        .. code-block:: python

            >>> import boa
            >>> src = """
            ... @external
            ... def main(a: uint256) -> uint256:
            ...     return 1 + a
            ... """
            >>> contract = boa.loads(src)
            >>> contract.main(68)
            69

    .. attribute:: contract
        :type: VyperContract

        The :py:class:`VyperContract` instance this :py:class:`VyperFunction` instance is attached to.

    .. attribute:: env
        :type: boa.environment.Env

        The :py:class:`boa.environment.Env` instance of the :py:attr:`contract` attribute.

    .. attribute:: fn_ast
        :type: vyper.ast.nodes.FunctionDef

        The Vyper AST of this function.

    .. property:: assembly
        :type: list[str]

        The function's runtime bytecode as a list of mnemonics.

    .. property:: bytecode
        :type: bytes

        The function's runtime bytecode in bytes form.

    .. property:: fn_signature
        :type: vyper.ast.signatures.function_signature.FunctionSignature

        The internal Vyper representation of the function's signature.

    .. property:: opcodes
        :type: str

        The function's runtime bytecode as a string of mnemonics.

    .. property:: ir
        :type: vyper.codegen.ir_node.IRnode

        The internal representation of the function (a.k.a. VenomIR).

.. class:: VyperInternalFunction

    Internal contract functions are exposed by wrapping it with a dummy external contract function, appending the wrapper's ast at the top of the contract and then generating bytecode to run internal methods (as external methods). Therefore, they share the same API as :py:class:`boa.vyper.contract.VyperFunction`. Internal functions can be accessed using the `internal` namespace of a :py:class:`VyperContract`.

    .. code-block:: python

        >>> import boa
        >>> src = """
        ... @internal
        ... def main(a: uint256) -> uint256:
        ...     return 1 + a
        ... """
        >>> contract = boa.loads(src)
        >>> contract.internal.main(68)
        69


Exceptions
----------

.. currentmodule:: boa

.. exception:: BoaError

    Raised when an error occurs during contract execution.
