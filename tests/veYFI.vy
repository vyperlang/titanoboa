# @version 0.3.4
"""
@title Voting YFI
@author Curve Finance, Yearn Finance
@license MIT
@notice
    Votes have a weight depending on time, so that users are
    committed to the future of whatever they are voting for.
@dev
    The voting power is capped at 4 years, but the lock can exceed that duration.
    Vote weight decays linearly over time.
    A user can unlock funds early incurring a penalty.
"""
from vyper.interfaces import ERC20

interface RewardPool:
    def burn(amount: uint256) -> bool: nonpayable

struct Point:
    bias: int128
    slope: int128  # - dweight / dt
    ts: uint256
    blk: uint256  # block

struct LockedBalance:
    amount: uint256
    end: uint256

struct Kink:
    slope: int128
    ts: uint256

struct Withdrawn:
    amount: uint256
    penalty: uint256

event ModifyLock:
    sender: indexed(address)
    user: indexed(address)
    amount: uint256
    locktime: uint256
    ts: uint256

event Withdraw:
    user: indexed(address)
    amount: uint256
    ts: uint256

event Penalty:
    user: indexed(address)
    amount: uint256
    ts: uint256

event Supply:
    old_supply: uint256
    new_supply: uint256
    ts: uint256

event Initialized:
    token: ERC20
    reward_pool: RewardPool

YFI: immutable(ERC20)
REWARD_POOL: immutable(RewardPool)

DAY: constant(uint256) = 86400
WEEK: constant(uint256) = 7 * 86400  # all future times are rounded by week
MAX_LOCK_DURATION: constant(uint256) = 4 * 365 * 86400  # 4 years
SCALE: constant(uint256) = 10 ** 18
MAX_PENALTY_RATIO: constant(uint256) = SCALE * 3 / 4  # 75% for early exit of max lock

supply: public(uint256)
locked: public(HashMap[address, LockedBalance])
# history
epoch: public(HashMap[address, uint256])
point_history: public(HashMap[address, HashMap[uint256, Point]])  # epoch -> unsigned point
slope_changes: public(HashMap[address, HashMap[uint256, int128]])  # time -> signed slope change


@external
def __init__(token: ERC20, reward_pool: RewardPool):
    """
    @notice Contract constructor
    @param token YFI token address
    @param reward_pool Pool for early exit penalties
    """
    YFI = token
    REWARD_POOL = reward_pool
    self.point_history[self][0].blk = block.number
    self.point_history[self][0].ts = block.timestamp

    log Initialized(token, reward_pool)


@view
@external
def get_last_user_point(addr: address) -> Point:
    """
    @notice Get the most recently recorded point for a user
    @param addr Address of the user wallet
    @return Last recorded point
    """
    epoch: uint256 = self.epoch[addr]
    return self.point_history[addr][epoch]


@pure
@internal
def round_to_week(ts: uint256) -> uint256:
    return ts / WEEK * WEEK


@view
@internal
def lock_to_point(lock: LockedBalance) -> Point:
    point: Point = Point({bias: 0, slope: 0, ts: block.timestamp, blk: block.number})
    if lock.amount > 0:
        # the lock is longer than the max duration
        if lock.end > block.timestamp + MAX_LOCK_DURATION:
            point.slope = 0
            point.bias = convert(lock.amount, int128)
        # the lock ends in the future but shorter than max duration
        elif lock.end > block.timestamp:
            point.slope = convert(lock.amount / MAX_LOCK_DURATION, int128)
            point.bias = point.slope * convert(lock.end - block.timestamp, int128)

    return point


@view
@internal
def lock_to_kink(lock: LockedBalance) -> Kink:
    kink: Kink = empty(Kink)
    # the lock is longer than the max duration
    if lock.amount > 0 and lock.end > self.round_to_week(block.timestamp + MAX_LOCK_DURATION):
        kink.ts = self.round_to_week(lock.end - MAX_LOCK_DURATION)
        kink.slope = convert(lock.amount / MAX_LOCK_DURATION, int128)

    return kink


@internal
def _checkpoint_user(user: address, old_lock: LockedBalance, new_lock: LockedBalance) -> Point[2]:
    old_point: Point = self.lock_to_point(old_lock)
    new_point: Point = self.lock_to_point(new_lock)

    old_kink: Kink = self.lock_to_kink(old_lock)
    new_kink: Kink = self.lock_to_kink(new_lock)

    # schedule slope changes for the lock end
    if old_point.slope != 0 and old_lock.end > block.timestamp:
        self.slope_changes[self][old_lock.end] += old_point.slope
        self.slope_changes[user][old_lock.end] += old_point.slope
    if new_point.slope != 0 and new_lock.end > block.timestamp:
        self.slope_changes[self][new_lock.end] -= new_point.slope
        self.slope_changes[user][new_lock.end] -= new_point.slope

    # schedule kinks for locks longer than max duration
    if old_kink.slope != 0:
        self.slope_changes[self][old_kink.ts] -= old_kink.slope
        self.slope_changes[user][old_kink.ts] -= old_kink.slope
    if new_kink.slope != 0:
        self.slope_changes[self][new_kink.ts] += new_kink.slope
        self.slope_changes[user][new_kink.ts] += new_kink.slope

    self.epoch[user] += 1
    self.point_history[user][self.epoch[user]] = new_point

    return [old_point, new_point]

@internal
def _checkpoint_global() -> Point:
    last_point: Point = Point({bias: 0, slope: 0, ts: block.timestamp, blk: block.number})
    epoch: uint256 = self.epoch[self]
    if epoch > 0:
        last_point = self.point_history[self][epoch]
    last_checkpoint: uint256 = last_point.ts
    # initial_last_point is used for extrapolation to calculate block number
    initial_last_point: Point = last_point
    block_slope: uint256 = 0  # dblock/dt
    if block.timestamp > last_point.ts:
        block_slope = SCALE * (block.number - last_point.blk) / (block.timestamp - last_point.ts)
    
    # apply weekly slope changes and record weekly global snapshots
    t_i: uint256 = self.round_to_week(last_checkpoint)
    for i in range(255):
        t_i = min(t_i + WEEK, block.timestamp)
        last_point.bias -= last_point.slope * convert(t_i - last_checkpoint, int128)
        last_point.slope += self.slope_changes[self][t_i]  # will read 0 if not aligned to week
        last_point.bias = max(0, last_point.bias)  # this can happen
        last_point.slope = max(0, last_point.slope)  # this shouldn't happen
        last_checkpoint = t_i
        last_point.ts = t_i
        last_point.blk = initial_last_point.blk + block_slope * (t_i - initial_last_point.ts) / SCALE
        epoch += 1
        if t_i < block.timestamp:
            self.point_history[self][epoch] = last_point
        # skip last week
        else:
            last_point.blk = block.number
            break

    self.epoch[self] = epoch
    return last_point


@internal
def _checkpoint(user: address, old_lock: LockedBalance, new_lock: LockedBalance):
    """
    @notice Record global and per-user data to checkpoint
    @param user User's wallet address. No user checkpoint if 0x0
    @param old_lock Pevious locked amount / end lock time for the user
    @param new_lock New locked amount / end lock time for the user
    """
    user_points: Point[2] = empty(Point[2])

    if user != ZERO_ADDRESS:
        user_points = self._checkpoint_user(user, old_lock, new_lock)

    # fill point_history until t=now
    last_point: Point = self._checkpoint_global()
    
    # only affects the last checkpoint at t=now
    if user != ZERO_ADDRESS:
        # If last point was in this block, the slope change has been applied already
        # But in such case we have 0 slope(s)
        last_point.slope += (user_points[1].slope - user_points[0].slope)
        last_point.bias += (user_points[1].bias - user_points[0].bias)
        last_point.slope = max(0, last_point.slope)
        last_point.bias = max(0, last_point.bias)

    # Record the changed point into history
    epoch: uint256 = self.epoch[self]
    self.point_history[self][epoch] = last_point


@external
def checkpoint():
    """
    @notice Record global data to checkpoint
    """
    self._checkpoint(ZERO_ADDRESS, empty(LockedBalance), empty(LockedBalance))


@external
def modify_lock(amount: uint256, unlock_time: uint256, user: address = msg.sender) -> LockedBalance:
    """
    @notice Create or modify a lock for a user. Support deposits on behalf of a user.
    @dev
        Minimum deposit to create a lock is 1 YFI.
        You can lock for longer than 4 years, but the max voting power is capped at 4 years.
        You can only increase lock duration if it has less than 4 years remaining.
        You can decrease lock duration if it has more than 4 years remaining.
    @param amount YFI amount to add to a lock. 0 to not modify.
    @param unlock_time Unix timestamp when the lock ends, must be in the future. 0 to not modify.
    @param user A user to deposit to. If different from msg.sender, unlock_time has no effect
    """
    old_lock: LockedBalance = self.locked[user]
    new_lock: LockedBalance = old_lock
    new_lock.amount += amount

    unlock_week: uint256 = 0
    # only a user can modify their own unlock time
    if msg.sender == user:
        if unlock_time != 0:
            unlock_week = self.round_to_week(unlock_time)  # locktime is rounded down to weeks
            assert unlock_week > block.timestamp  #  dev: unlock time must be in the future
            if unlock_week - block.timestamp < MAX_LOCK_DURATION:
                assert unlock_week > old_lock.end  # dev: can only increase lock duration
            else:
                assert unlock_week > block.timestamp + MAX_LOCK_DURATION  # dev: can only decrease to ≥4 years
            new_lock.end = unlock_week

    # create lock
    if old_lock.amount == 0 and old_lock.end == 0:
        assert msg.sender == user  # dev: you can only create a lock for yourself
        assert amount >= 10 ** 18  # dev: minimum amount is 1 YFI
        assert unlock_week != 0  # dev: must specify unlock time in the future
    # modify lock
    else:
        assert old_lock.end > block.timestamp  # dev: lock expired

    supply_before: uint256 = self.supply
    self.supply = supply_before + amount
    self.locked[user] = new_lock
    
    self._checkpoint(user, old_lock, new_lock)

    if amount > 0:
        assert YFI.transferFrom(msg.sender, self, amount)

    log Supply(supply_before, supply_before + amount, block.timestamp)
    log ModifyLock(msg.sender, user, new_lock.amount, new_lock.end, block.timestamp)

    return new_lock


@external
def withdraw() -> Withdrawn:
    """
    @notice Withdraw lock for a sender
    @dev
        If a lock has expired, sends a full amount to the sender.
        If a lock is still active, the sender pays a 75% penalty during the first year
        and a linearly decreasing penalty from 75% to 0 based on the remaining lock time.
    """
    old_locked: LockedBalance = self.locked[msg.sender]
    assert old_locked.amount > 0  # dev: create a lock first to withdraw
    
    time_left: uint256 = 0
    penalty: uint256 = 0

    if old_locked.end > block.timestamp:
        time_left = min(old_locked.end - block.timestamp, MAX_LOCK_DURATION)
        penalty_ratio: uint256 = min(time_left * SCALE / MAX_LOCK_DURATION, MAX_PENALTY_RATIO)
        penalty = old_locked.amount * penalty_ratio / SCALE

    zero_locked: LockedBalance = empty(LockedBalance)
    self.locked[msg.sender] = zero_locked

    supply_before: uint256 = self.supply
    self.supply = supply_before - old_locked.amount

    self._checkpoint(msg.sender, old_locked, zero_locked)

    assert YFI.transfer(msg.sender, old_locked.amount - penalty)
    
    if penalty > 0:
        assert YFI.approve(REWARD_POOL.address, penalty)
        assert REWARD_POOL.burn(penalty)

        log Penalty(msg.sender, penalty, block.timestamp)
    
    log Withdraw(msg.sender, old_locked.amount - penalty, block.timestamp)
    log Supply(supply_before, supply_before - old_locked.amount, block.timestamp)

    return Withdrawn({amount: old_locked.amount - penalty, penalty: penalty})


@view
@internal
def find_epoch_by_block(user: address, height: uint256, max_epoch: uint256) -> uint256:
    """
    @notice Binary search to estimate timestamp for height number
    @param height Block to find
    @param max_epoch Don't go beyond this epoch
    @return Epoch the block is in
    """
    _min: uint256 = 0
    _max: uint256 = max_epoch
    for i in range(128):  # Will be always enough for 128-bit numbers
        if _min >= _max:
            break
        _mid: uint256 = (_min + _max + 1) / 2
        if self.point_history[user][_mid].blk <= height:
            _min = _mid
        else:
            _max = _mid - 1
    return _min


@view
@internal
def find_epoch_by_timestamp(user: address, ts: uint256, max_epoch: uint256) -> uint256:
    """
    @notice Binary search to estimate timestamp for height number
    @param ts Timestamp to find
    @param max_epoch Don't go beyond this epoch
    @return Epoch the timestamp is in
    """
    _min: uint256 = 0
    _max: uint256 = max_epoch
    for i in range(128):  # Will be always enough for 128-bit numbers
        if _min >= _max:
            break
        _mid: uint256 = (_min + _max + 1) / 2
        if self.point_history[user][_mid].ts <= ts:
            _min = _mid
        else:
            _max = _mid - 1
    return _min


@view
@internal
def replay_slope_changes(user: address, point: Point, ts: uint256) -> Point:
    upoint: Point = point
    t_i: uint256 = self.round_to_week(upoint.ts)

    for i in range(500):
        t_i += WEEK
        d_slope: int128 = 0
        if t_i > ts:
            t_i = ts
        else:
            d_slope = self.slope_changes[user][t_i]
        upoint.bias -= upoint.slope * convert(t_i - upoint.ts, int128)
        if t_i == ts:
            break
        upoint.slope += d_slope
        upoint.ts = t_i
    
    upoint.bias = max(0, upoint.bias)
    return upoint


@view
@external
def balanceOf(user: address, ts: uint256 = block.timestamp) -> uint256:
    """
    @notice Get the current voting power for `msg.sender`
    @param user User wallet address
    @param ts Epoch time to return voting power at
    @return User voting power
    """
    epoch: uint256 = self.epoch[user]
    if epoch == 0:
        return 0

    epoch = self.find_epoch_by_timestamp(user, ts, epoch)
    upoint: Point = self.point_history[user][epoch]
    
    upoint = self.replay_slope_changes(user, upoint, ts)

    return convert(upoint.bias, uint256)


@view
@external
def getPriorVotes(user: address, height: uint256) -> uint256:
    """
    @notice Measure voting power of `user` at block height `height`
    @dev Compatible with GovernorAlpha
    @param user User's wallet address
    @param height Block to calculate the voting power at
    @return Voting power
    """
    assert height <= block.number

    uepoch: uint256 = self.epoch[user]
    uepoch = self.find_epoch_by_block(user, height, uepoch)
    upoint: Point = self.point_history[user][uepoch]

    max_epoch: uint256 = self.epoch[self]
    epoch: uint256 = self.find_epoch_by_block(self, height, max_epoch)
    point_0: Point = self.point_history[self][epoch]
    d_block: uint256 = 0
    d_t: uint256 = 0
    if epoch < max_epoch:
        point_1: Point = self.point_history[self][epoch + 1]
        d_block = point_1.blk - point_0.blk
        d_t = point_1.ts - point_0.ts
    else:
        d_block = block.number - point_0.blk
        d_t = block.timestamp - point_0.ts
    block_time: uint256 = point_0.ts
    if d_block != 0:
        block_time += d_t * (height - point_0.blk) / d_block

    upoint.bias -= upoint.slope * convert(block_time - upoint.ts, int128)
    if upoint.bias >= 0:
        return convert(upoint.bias, uint256)
    else:
        return 0


@view
@external
def totalSupply(ts: uint256 = block.timestamp) -> uint256:
    """
    @notice Calculate total voting power
    @dev Adheres to the ERC20 `totalSupply` interface for Aragon compatibility
    @return Total voting power
    """
    epoch: uint256 = self.epoch[self]
    last_point: Point = self.point_history[self][epoch]
    last_point = self.replay_slope_changes(self, last_point, ts)
    return convert(last_point.bias, uint256)


@view
@external
def totalSupplyAt(height: uint256) -> uint256:
    """
    @notice Calculate total voting power at some point in the past
    @param height Block to calculate the total voting power at
    @return Total voting power at `height`
    """
    assert height <= block.number
    epoch: uint256 = self.epoch[self]
    target_epoch: uint256 = self.find_epoch_by_block(self, height, epoch)

    point: Point = self.point_history[self][target_epoch]
    dt: uint256 = 0
    if target_epoch < epoch:
        point_next: Point = self.point_history[self][target_epoch + 1]
        if point.blk != point_next.blk:
            dt = (height - point.blk) * (point_next.ts - point.ts) / (point_next.blk - point.blk)
    else:
        if point.blk != block.number:
            dt = (height - point.blk) * (block.timestamp - point.ts) / (block.number - point.blk)

    # Now dt contains info on how far are we beyond point
    point = self.replay_slope_changes(self, point, point.ts + dt)
    return convert(point.bias, uint256)


@view
@external
def token() -> ERC20:
    return YFI


@view
@external
def reward_pool() -> RewardPool:
    return REWARD_POOL


@view
@external
def name() -> String[10]:
    return "Voting YFI"


@view
@external
def symbol() -> String[5]:
    return "veYFI"


@view
@external
def decimals() -> uint8:
    return 18
