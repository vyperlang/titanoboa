import boa

import time

_t = time.time()

def timeit(msg):
    global _t
    t = time.time()
    print(f"{msg} took {t - _t}s")
    _t = time.time()


def format_addr(t):
    if isinstance(t, str):
        t = t.encode("utf-8")
    return t.rjust(20, b"\x00")

BUNNY = format_addr("bunny")
MILKY = format_addr("milky")
DOGGIE = format_addr("doggie")
POOLPI = format_addr("poolpi")

parties = [BUNNY, MILKY, DOGGIE, POOLPI]

boa.env.eoa = BUNNY

START_TIME = 1641013200  # jan 1 2022
boa.env.vm.patch.timestamp = START_TIME

# MAX_LOCK_DURATION - constant in veYFI, boa does not expose contract constants (yet)
DAY = 86400
WEEK = 7 * DAY
YEAR = 365 * DAY
MAX_LOCK_DURATION = 4 * YEAR

YFI = boa.load("tests/ERC20.vy", "yfi token", "YFI", 18, 0, override_address = format_addr("YFI"))
timeit("load YFI")
_rewards_pool_address = format_addr("rewards_pool")

veYFI = boa.load("tests/veYFI.vy", YFI.address, _rewards_pool_address, override_address=format_addr("veYFI"))
timeit("load veYFI")
rewards_pool = boa.load("tests/RewardPool.vy", veYFI.address, START_TIME, override_address=_rewards_pool_address)
timeit("load rewards pool")


YFI.mint(BUNNY, 10 ** 21)
# YFI.mint('veyfi', 10 ** 21)
YFI.mint(MILKY, 10 ** 21)
YFI.transfer(DOGGIE, 10 ** 18)
YFI.transfer(MILKY, 3 * 10 ** 18)
YFI.transfer(POOLPI, 10 ** 18)

timeit("set up balances")

for t in parties:
    with boa.env.prank(t):
        print(f"approving {YFI.balanceOf(t)} for {t}")
        YFI.approve(veYFI.address, YFI.balanceOf(t))

timeit("approve YFI")

# normal 4y lock
veYFI.modify_lock(10 ** 18, boa.env.vm.patch.timestamp + MAX_LOCK_DURATION, BUNNY)

# extended 6y lock
with boa.env.prank(MILKY):
    veYFI.modify_lock(10 ** 18, int(boa.env.vm.patch.timestamp + MAX_LOCK_DURATION / 4 * 6), MILKY)

# 4y lock with early exit after 1y
with boa.env.prank(POOLPI):
    veYFI.modify_lock(10 ** 18, int(boa.env.vm.patch.timestamp + MAX_LOCK_DURATION / 4 * 3), POOLPI)

with boa.env.prank(DOGGIE):
    # shorter 2y lock
    veYFI.modify_lock(10 ** 18, boa.env.vm.patch.timestamp + MAX_LOCK_DURATION // 2, DOGGIE)

timeit("lock veYFI")

def warp_week(n=1):
    boa.env.vm.patch.timestamp += WEEK * n
    boa.env.vm.patch.block_number += 40_000 * n

for i in range(START_TIME, int(START_TIME + YEAR * 1.2), WEEK):
    warp_week()
    veYFI.checkpoint()
    # for user in veyfi.locked:
    #     veyfi.checkpoint_user(user)
    # Locked:
    #   amount: uint256
    #   end: uint256
    if veYFI.locked(POOLPI)[1] != 0 and i > START_TIME + MAX_LOCK_DURATION // 4:
        with boa.env.prank(POOLPI):
            veYFI.withdraw()
    if veYFI.locked(MILKY)[0] == 10 ** 18 and i > int(START_TIME + YEAR * .5):
        with boa.env.prank(MILKY):
            veYFI.modify_lock(10 ** 18, START_TIME + YEAR * 5)

timeit("simulation")

print({t: veYFI.balanceOf(t) for t in parties})
assert {t: veYFI.balanceOf(t) for t in parties} == {BUNNY: 693692922292074000, MILKY: 1891495433795992400, DOGGIE: 195062785364970000, POOLPI: 0}

