API Reference
=============

High-Level Functionality
------------------------

.. module:: boa

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

.. function:: register_precompile(address: str, fn: Callable[[eth.vm.computation.BaseComputation], None], force: bool = False)

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

.. function:: patch_opcode(opcode: int, fn: Callable[[eth.vm.computation.BaseComputation], None])

    Patch an opcode.

    :param opcode: The opcode to patch.
    :param fn: The function implementing the desired opcode functionality.

    .. note::

        The function provided as an argument should be defined with a single keyword parameter, ``computation``, like so:

        .. code-block:: python

            def baz(computation: eth.vm.computation.BaseComputation):
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

    .. attribute:: chain
        :type: eth.abc.ChainAPI

    .. attribute:: eoa
        :type: str

        The account to use as ``tx.origin`` when performing state mutating contract operations.

Exceptions
----------

.. currentmodule:: boa

.. exception:: BoaError

    Raised when an error occurs during contract execution.
