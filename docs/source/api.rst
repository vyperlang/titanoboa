API Reference
=============

.. module:: boa

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
