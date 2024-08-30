from typing import Any

import boa
from boa.util.abi import Address
from boa.vm.utils import to_int

SLOAD_OPCODE = 0x54


class SloadTracer:
    def __init__(self, super_fn):
        self.super_fn = super_fn
        self.trace = []

    def __call__(self, computation):
        slot = to_int(computation._stack.values[-1])
        self.super_fn(computation)
        self.trace.append(slot)


def update_storage_slot(contract, fn_name, mk_new_value: Any, args: Any):
    tmp = boa.vm.py_evm._opcode_overrides

    try:
        # clean opcode overrides in case there is user-stuff in there - we
        # don't want to trip user-overridden opcodes, since this is a
        # "system" operation.
        boa.vm.py_evm._opcode_overrides = {}
        opcodes = boa.env.evm.vm.state.computation_class.opcodes
        sload_tracer = SloadTracer(opcodes[SLOAD_OPCODE])
        boa.patch_opcode(SLOAD_OPCODE, sload_tracer)

        return _update_storage_slot(contract, fn_name, mk_new_value, sload_tracer, args)

    finally:
        # restore
        boa.vm.py_evm._opcode_overrides = tmp


def _get_func(contract, fn_name):
    try:
        return getattr(contract, fn_name)
    except AttributeError:
        raise ValueError(f"Function {fn_name} not found in {contract}")


def _update_storage_slot(contract, fn_name, mk_new_value: Any, sload_tracer, args):
    fn = _get_func(contract, fn_name)
    result = fn(*args)

    # we iterate over all the storage slots accessed by the SLOAD opcode
    # until we find the one that contains the result of the function call
    for slot in sload_tracer.trace:
        slot_value = boa.env.get_storage(contract.address, slot)

        # perf: don't bother checking the slot if it doesn't match the expected result
        if slot_value != result:
            continue

        # double check we have the right slot -- modifying the value should
        # yield the expected value on calling the view function again
        with boa.env.anchor():
            poison = (result + 1) % 2**256
            boa.env.set_storage(contract.address, slot, poison)
            if fn(*args) != poison:
                continue

        # we found the slot. update it
        new_value = mk_new_value(slot_value)
        boa.env.set_storage(contract.address, slot, new_value)

        # sanity check
        if fn(*args) != new_value:
            # very unlikely, but this means the ERC20 implementation is totally weird
            raise RuntimeError("new value does not match, unknown ERC20 implementation")

        break

    else:
        msg = f"Could not find the target slot for {fn_name}"
        msg += ", this is expected if the token packs storage slots or"
        msg += " computes the value on the fly"
        raise ValueError(msg)


def deal(token, amount: int, receiver: Address):
    """
    Mints `amount` of tokens to `receiver` and adjusts the total supply if `adjust_supply` is True.
    Inspired by https://github.com/foundry-rs/forge-std/blob/07263d193d/src/StdCheats.sol#L728
    """
    new_balance = lambda balance: balance + amount  # noqa: E731
    update_storage_slot(token, "balanceOf", new_balance, (receiver,))

    new_supply = lambda totalSupply: totalSupply + amount  # noqa: E731
    update_storage_slot(token, "totalSupply", new_supply, ())
