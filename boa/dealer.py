import boa
from boa.util.abi import Address

SLOAD_OPCODE = 0x54


class SloadTracer:
    def __init__(self, super_fn):
        self.super_fn = super_fn
        self.trace = []

    def __call__(self, computation):
        # TODO find a way to peak instead of pop/repush
        slot = computation.stack_pop1_int()
        computation.stack_push_int(slot)
        self.super_fn(computation)
        self.trace.append(slot)


def find_storage_slot(token, function_selector, *args):
    sload_tracer = SloadTracer(
        boa.env.evm.vm.state.computation_class.opcodes[SLOAD_OPCODE]
    )
    boa.patch_opcode(SLOAD_OPCODE, sload_tracer)

    try:
        result = getattr(token, function_selector)(*args)
    except AttributeError:
        raise ValueError(
            f"Invalid erc20 contract, function {function_selector} not found"
        )

    target_slot = None
    for slot in sload_tracer.trace:
        slot_value = boa.env.get_storage(token.address, slot)

        if slot_value == result:
            with boa.env.anchor():
                boa.env.set_storage(token.address, slot, 123456789)
                if getattr(token, function_selector)(*args) != 123456789:
                    continue

            target_slot = slot
            break

    # TODO unpatch opcode

    if target_slot is None:
        raise ValueError(
            f"Could not find the target slot for {function_selector}, this is expected if the token"
            " packs storage slots or computes the value on the fly"
        )

    return target_slot


def deal(token, amount: int, receiver: Address, adjust_supply: bool = True):
    # find the storage slot for the balance of the receiver
    balance_slot = find_storage_slot(token, "balanceOf", receiver)

    # backup the current balance to adjust the total supply later
    old_balance = boa.env.get_storage(token.address, balance_slot)

    # overwrite the old balance with the new one
    boa.env.set_storage(token.address, balance_slot, amount)

    assert token.balanceOf(receiver) == amount, "balance update failed, this is a bug"

    if adjust_supply:
        # find the storage slot for the total supply
        supply_slot = find_storage_slot(token, "totalSupply")

        # compute the new total supply
        old_supply = boa.env.get_storage(token.address, supply_slot)
        new_supply = old_supply + (amount - old_balance)

        # overwrite the old total supply with the new one
        boa.env.set_storage(token.address, supply_slot, new_supply)

        assert (
            token.totalSupply() == new_supply
        ), "total supply update failed, this is a bug"
