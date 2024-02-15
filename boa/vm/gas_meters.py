from eth.vm.gas_meter import GasMeter


class NoGasMeter:
    """
    A trivial gas meter, which does not meter gas usage.
    Improves EVM runtime performance by about 10%.
    Useful if you don't care about gas usage but want a
    performance boost.
    """

    def __init__(self, start_gas, *args, **kwargs):
        pass

    def consume_gas(self, amount, reason):
        pass

    def refund_gas(self, amount):
        pass

    def return_gas(self, amount):
        pass


class ProfilingGasMeter(GasMeter):
    """
    A gas meter which tracks the gas usage of every single PC.
    Used for profiling (users can back out opcode, line or function
    gas usage).
    """

    def __init__(self, start_gas, *args, **kwargs):
        super().__init__(start_gas, *args, **kwargs)
        self._gas_used_of = {}  # mapping from PCs to gas used
        self._gas_refunded_of = {}  # mapping from PCs to gas refunded

    def _set_code(self, code):
        self._code = code

    @property
    def _pc(self):
        # at the time that gas is refunded, pc is = to real pc + 1
        # (due to implementation detail of py-evm CodeStream.)
        return self._code.program_counter - 1

    def consume_gas(self, amount: int, reason: str) -> None:
        super().consume_gas(amount, reason)
        self._gas_used_of.setdefault(self._pc, 0)
        self._gas_used_of[self._pc] += amount

    def return_gas(self, amount: int) -> None:
        super().return_gas(amount)
        self._gas_used_of.setdefault(self._pc, 0)
        self._gas_used_of[self._pc] -= amount

    def refund_gas(self, amount: int) -> None:
        super().refund_gas(amount)
        self._gas_refunded_of.setdefault(self._pc, 0)
        self._gas_refunded_of[self._pc] += amount
