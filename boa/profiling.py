import statistics
from collections import namedtuple
from dataclasses import dataclass
from functools import cached_property

from eth_utils import to_checksum_address
from rich.table import Table

from boa.environment import Env
from boa.vyper.ast_utils import get_line

# simple dataclass for fn
CallInfo = namedtuple("SelectorInfo", ["fn_name", "contract_name", "address"])
LineInfo = namedtuple(
    "LineGasUsedInfo", ["address", "contract_name", "lineno", "line_src"]
)


@dataclass
class Datum:
    gas_used: int = 0
    gas_refunded: int = 0
    # child gas usage might be useful for
    child_gas_used: int = 0
    child_gas_refunded: int = 0

    @property
    def net_gas(self):
        return self.gas_used - self.gas_refunded

    @property
    def net_tot_gas(self):
        return (
            self.gas_used
            - self.child_gas_used
            - self.gas_refunded
            + self.child_gas_refunded
        )

    def merge(self, other):
        for s in self.__dict__:
            self.__dict__[s] += other.__dict__[s]

    def adjust_child(self, child_computation):
        # adjust a Datum for gas used by child computation
        # generally if it's a vyper contract, we adjust the gas (since
        # that will show up elsewhere in the profile), and if it's some
        # black box contract, back out the adjustment.
        self.gas_used -= child_computation.get_gas_used()
        self.gas_refunded -= child_computation.get_gas_refund()
        self.child_gas_used += child_computation.get_gas_used()
        self.child_gas_refunded += child_computation.get_gas_refund()


# profile for a single call
class _SingleComputation:
    def __init__(self, contract, computation):
        self.contract = contract
        self.computation = computation

    @cached_property
    def by_pc(self):
        ret = {}
        for pc, gas in self.computation._gas_meter._gas_used_of.items():
            ret[pc] = Datum(gas_used=gas)

        for pc, gas in self.computation._gas_meter._gas_refunded_of.items():
            ret.setdefault(pc, Datum()).merge(Datum(gas_refunded=gas))

        for pc, child in zip(self.computation._child_pcs, self.computation.children):
            ret[pc].adjust_child(child)

        for pc in self.computation.code._trace:
            # in py-evm, STOP, RETURN and REVERT do not call consume_gas.
            # so, we need to zero them manually.
            ret.setdefault(pc, Datum())

        return ret

    @cached_property
    def by_line(self):
        ret = {}
        line_map = self.contract.source_map["pc_pos_map"]
        current_line = None
        seen = set()
        for pc in self.computation.code._trace:
            if line_map.get(pc) is not None:
                current_line, _, _, _ = line_map[pc]

            if current_line is not None and pc not in seen:
                ret.setdefault(current_line, Datum())
                ret[current_line].merge(self.by_pc[pc])
                seen.add(pc)

        return ret


# line profile. mergeable across contracts
class LineProfile:
    def __init__(self):
        self.profile = {}

    @classmethod
    def from_single(cls, contract, computation):
        ret = cls()
        ret.merge_single(_SingleComputation(contract, computation))
        return ret

    def raw_summary(self):
        return list(self.profile.items())

    def merge_single(self, single: _SingleComputation) -> None:
        for line, datum in single.by_line.items():
            self.profile.setdefault((single.contract, line), Datum()).merge(datum)

    def merge(self, other: "LineProfile") -> None:
        for (contract, line), datum in other.profile.items():
            self.profile.setdefault((contract, line), Datum()).merge(datum)

    def summary(
        self, display_columns=("net_tot_gas",), sortkey="net_tot_gas", limit=10
    ):
        raw_summary = self.raw_summary()

        if sortkey is not None:
            raw_summary.sort(reverse=True, key=lambda x: getattr(x[1], sortkey))
        if limit is not None and limit > 0:
            raw_summary = raw_summary[:limit]

        tmp = []
        for (contract, line), datum in raw_summary:
            data = ", ".join(f"{c}: {getattr(datum, c)}" for c in display_columns)
            line_src = get_line(contract.compiler_data.source_code, line)
            x = f"{contract.address}:{contract.compiler_data.contract_name}:{line} {data}"
            tmp.append((x, line_src))

        just = max(len(t[0]) for t in tmp)
        ret = [f"{l.ljust(just)}  {r.strip()}" for (l, r) in tmp]
        return _String("\n".join(ret))

    def get_line_data(self):
        raw_summary = self.raw_summary()

        line_gas_data = {}
        for (contract, line), datum in raw_summary:

            # here we use net_gas to include child computation costs:
            line_info = LineInfo(
                address=contract.address,
                contract_name=contract.compiler_data.contract_name,
                lineno=line,
                line_src=get_line(contract.compiler_data.source_code, line),
            )
            line_gas_data[line_info] = getattr(datum, "net_gas")
        return line_gas_data


# stupid class whose __str__ method doesn't escape (good for repl)
class _String(str):
    def __repr__(self):
        return self


# cache gas_used for all computation (including children)
def cache_gas_used_for_computation(contract, computation):

    profile = contract.line_profile(computation)
    env = contract.env

    line_profile = profile.get_line_data()

    # -------------------- CACHE CALL PROFILE --------------------
    # TODO: looks a bit unkempt, can we refactor most of it to LineProfile?

    # get gas used. We use Datum().net_gas here instead of Datum().net_tot_gas
    # because a call's profile includes children call costs.
    # There will be double counting, but that is by choice.
    gas_used = sum([i.net_gas for i in profile.profile.values()])

    try:
        fn_name = contract._get_fn_from_computation(computation).name
    except AttributeError:
        # TODO: remove this once vyper PR 3202 is merged
        # https://github.com/vyperlang/vyper/pull/3202
        fn_name = "unnamed"

    fn = CallInfo(
        fn_name=fn_name,
        contract_name=contract.compiler_data.contract_name,
        address=to_checksum_address(contract.address),
    )

    if fn not in env._cached_call_profiles.keys():
        env._cached_call_profiles[fn] = [gas_used]
    else:
        env._cached_call_profiles[fn].append(gas_used)
    # ------------------------------------------------------------

    # -------------------- CACHE LINE PROFILE --------------------

    for line, gas_used in line_profile.items():
        if line not in env._cached_line_profiles.keys():
            env._cached_line_profiles[line] = [gas_used]
        else:
            env._cached_line_profiles[line].append(gas_used)

    # ------------------------------------------------------------

    # recursion for child computations
    for _computation in computation.children:
        child_contract = env.lookup_contract(_computation.msg.code_address)
        # ignore black box contracts
        if child_contract:
            cache_gas_used_for_computation(child_contract, _computation)


def _create_table():

    table = Table(title="\n")

    table.add_column("Contract", justify="right", style="blue", no_wrap=True)
    table.add_column("Address", justify="left", style="blue", no_wrap=True)
    table.add_column("Code", justify="left", style="blue", no_wrap=True)
    table.add_column("Count", style="magenta")
    table.add_column("Mean", style="magenta")
    table.add_column("Median", style="magenta")
    table.add_column("Stdev", style="magenta")
    table.add_column("Min", style="magenta")
    table.add_column("Max", style="magenta")

    return table


def get_call_profile_table(env: Env):

    table = _create_table()

    profiled_contracts = []
    for key in env._cached_call_profiles.keys():
        if key.address not in profiled_contracts:
            profiled_contracts.append(key.address)

    contract_profiles = {}
    max_avg_gas = []
    for contract in profiled_contracts:

        profiled_calls = {}
        for profile in env._cached_call_profiles.keys():
            if contract == profile.address:
                contract_name = profile.contract_name
                fn_name = profile.fn_name
                profiled_calls[fn_name] = env._cached_call_profiles[profile]

        # generate means, stds for each
        call_profiles = {}
        average_gas_costs = []
        for key, gas_used in profiled_calls.items():
            call_profile = {}
            call_profile["contract_name"] = contract_name
            call_profile["count"] = len(gas_used)
            call_profile["mean"] = int(statistics.mean(gas_used))
            call_profile["median"] = int(statistics.median(gas_used))
            call_profile["min"] = min(gas_used)
            call_profile["max"] = max(gas_used)
            if len(gas_used) == 1:
                call_profile["stdev"] = 0
            else:
                call_profile["stdev"] = int(statistics.stdev(gas_used))
            call_profiles[key] = call_profile
            average_gas_costs.append(call_profile["mean"])

        contract_profiles[contract] = call_profiles
        max_avg_gas.append(max(average_gas_costs))

    # arrange from most to least expensive contracts:
    sort_gas = sorted(zip(max_avg_gas, profiled_contracts), reverse=True)
    sorted_contracts = [x for _, x in sort_gas]

    for contract in sorted_contracts:
        call_profiles = contract_profiles[contract]
        c = 0
        for key in call_profiles.keys():
            profile = call_profiles[key]
            cname = ""
            caddr = ""
            if c == 0:
                cname = profile["contract_name"]
                caddr = contract
            table.add_row(
                cname,
                caddr,
                key,
                str(profile["count"]),
                str(profile["mean"]),
                str(profile["median"]),
                str(profile["stdev"]),
                str(profile["min"]),
                str(profile["max"]),
            )
            c += 1

        table.add_section()

    return table


def get_line_profile_table(env: Env):

    contracts = {}
    for lp, gas_data in env._cached_line_profiles.items():
        contract_uid = (lp.contract_name, lp.address)
        gas_data = (str(lp.lineno) + ": " + lp.line_src, gas_data)
        if contract_uid not in contracts:
            contracts[contract_uid] = [gas_data]
        else:
            contracts[contract_uid].append(gas_data)

    table = _create_table()

    for (contract_name, address), _data in contracts.items():

        c = 0
        for code, gas_used in _data:

            if len(gas_used) == 1:
                stdev = 0
            else:
                stdev = int(statistics.stdev(gas_used))

            if code.endswith("\n"):
                code = code[:-1]

            cname = ""
            caddr = ""
            if c == 0:
                cname = contract_name
                caddr = address

            table.add_row(
                cname,
                caddr,
                code,
                str(len(gas_used)),
                str(int(statistics.mean(gas_used))),
                str(int(statistics.median(gas_used))),
                str(stdev),
                str(min(gas_used)),
                str(max(gas_used)),
            )

            c += 1

        table.add_section()

    return table
