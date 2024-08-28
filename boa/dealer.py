import boa
from boa import BoaError
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


# TODO what's the correct type annotation for token (not only VyperContract)
def deal(token, amount: int, receiver: Address):
    # we need to trace all sloads to find the
    # slot containing the balance of the target
    sload_tracer = SloadTracer(
        boa.env.evm.vm.state.computation_class.opcodes[SLOAD_OPCODE]
    )
    boa.patch_opcode(SLOAD_OPCODE, sload_tracer)

    # since we have patched sload opcode,
    # we can now trace the slot that contains
    # the balance of the receiver.
    # TODO handle custom signatures (i.e. `scaledBalanceOf`) for aTokens
    try:
        target_balance = token.balanceOf(receiver)
    except BoaError:
        raise ValueError("Invalid token contract, are you sure it's an ERC20?")

    # we iteratively look for the slot that contains
    # the balance of the receiver among all the slots accessed
    # during the `balanceOf` call.

    # This approach works on any memory layout as long as:
    # 1. the balance is stored in a single unpacked slot.
    # 2. the balance is not computed on the fly.
    target_slot = None
    for slot in sload_tracer.trace:
        slot_value = boa.env.get_storage(token.address, slot)

        # TODO handle balanceOf value collision with other storage slots
        # containing the same value (very common if balance is 0)
        if slot_value == target_balance:
            target_slot = slot
            break

    assert target_slot is not None

    boa.env.set_storage(token.address, target_slot, amount)

    assert token.balanceOf(receiver) == amount

    # TODO unpatch opcode
