import statistics
from dataclasses import dataclass
from functools import cached_property
from textwrap import dedent

from eth_utils import to_checksum_address
from rich.table import Table

from boa.environment import Env
from boa.vyper.ast_utils import get_line


@dataclass(unsafe_hash=True)
class LineInfo:
    address: str
    contract_name: str
    lineno: int
    line_src: str
    fn_name: str = ""


@dataclass(unsafe_hash=True)
class ContractMethodInfo:
    address: str
    contract_name: str
    fn_name: str


@dataclass
class Stats:
    count: int = 0
    avg_gas: int = 0
    median_gas: int = 0
    stdev_gas: int = 0
    min_gas: int = 0
    max_gas: int = 0

    def __init__(self, gas_data):

        self.count = len(gas_data)
        self.avg_gas = int(statistics.mean(gas_data))
        self.median_gas = int(statistics.median(gas_data))
        self.stdev_gas = int(statistics.stdev(gas_data) if self.count > 1 else 0)
        self.min_gas = min(gas_data)
        self.max_gas = max(gas_data)

    def get_str_repr(self):
        return iter(
            [
                str(self.count),
                str(self.avg_gas),
                str(self.median_gas),
                str(self.stdev_gas),
                str(self.min_gas),
                str(self.max_gas),
            ]
        )


class CallGasStats:
    def __init__(self):
        self.net_gas = []
        self.net_tot_gas = []

    def compute_stats(self, typ: str = "net_gas"):

        gas_data = getattr(self, typ)
        setattr(self, typ + "_stats", Stats(gas_data))

    def merge_gas_data(self, net_gas: int, net_tot_gas: int):
        self.net_gas.append(net_gas)
        self.net_tot_gas.append(net_tot_gas)


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
        raw_summary.sort(reverse=True, key=lambda x: getattr(x[1], "net_gas"))

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
    # get gas used. We use Datum().net_gas here instead of Datum().net_tot_gas
    # because a call's profile includes children call costs.
    # There will be double counting, but that is by choice.

    sum_net_gas = sum([i.net_gas for i in profile.profile.values()])
    sum_net_tot_gas = sum([i.net_tot_gas for i in profile.profile.values()])

    try:
        fn_name = contract._get_fn_from_computation(computation).name
    except AttributeError:
        # TODO: remove this once vyper PR 3202 is merged
        # https://github.com/vyperlang/vyper/pull/3202
        # and new vyper is released (so update vyper requirements
        # in pyproject.toml)
        fn_name = "unnamed"

    fn = ContractMethodInfo(
        contract_name=contract.compiler_data.contract_name,
        address=to_checksum_address(contract.address),
        fn_name=fn_name,
    )

    env._cached_call_profiles.setdefault(fn, CallGasStats()).merge_gas_data(
        sum_net_gas, sum_net_tot_gas
    )

    s = env._profiled_contracts.setdefault(fn.address, [])
    if fn not in env._profiled_contracts[fn.address]:
        s.append(fn)

    # -------------------- CACHE LINE PROFILE --------------------

    for line, gas_used in line_profile.items():
        line.fn_name = fn_name
        env._cached_line_profiles.setdefault(line, []).append(gas_used)

    # ------------------------- RECURSION -------------------------

    # recursion for child computations
    for _computation in computation.children:
        child_contract = env.lookup_contract(_computation.msg.code_address)
        # ignore black box contracts
        if child_contract is not None:
            cache_gas_used_for_computation(child_contract, _computation)


def _create_table(show_contract: bool = True):

    table = Table(title="\n")

    table.add_column("Contract", justify="right", style="cyan", no_wrap=True)
    if show_contract:
        table.add_column("Address", justify="left", style="cyan", no_wrap=True)
    table.add_column("Computation", justify="left", style="cyan", no_wrap=True)
    table.add_column("Count", style="magenta")
    table.add_column("Mean", style="magenta")
    table.add_column("Median", style="magenta")
    table.add_column("Stdev", style="magenta")
    table.add_column("Min", style="magenta")
    table.add_column("Max", style="magenta")

    return table


def get_call_profile_table(env: Env):

    table = _create_table()

    cache = env._cached_call_profiles
    cached_contracts = env._profiled_contracts
    contract_vs_mean_gas = []
    for profile in cache:
        cache[profile].compute_stats()
        contract_vs_mean_gas.append(
            (cache[profile].net_gas_stats.avg_gas, profile.address)
        )

    # arrange from most to least expensive contracts:
    sort_gas = sorted(contract_vs_mean_gas, reverse=True)

    # --------------- POPULATE TABLE -----------------

    for (_, address) in sort_gas:

        fn_vs_mean_gas = []
        for profile in cached_contracts[address]:
            fn_vs_mean_gas.append((cache[profile].net_gas_stats.avg_gas, profile))

        # arrange from most to least expensive contracts:
        sort_gas = sorted(fn_vs_mean_gas, reverse=True)

        for c, (_, profile) in enumerate(sort_gas):

            stats = cache[profile]

            # only first line should be populated for name and address
            cname = ""
            caddr = ""
            if c == 0:
                cname = profile.contract_name
                caddr = address

            fn_name = profile.fn_name

            if len(cname) > 25:
                cname = "..." + cname[-10:]

            if len(fn_name) > 10:
                fn_name = fn_name[:5] + "..."

            table.add_row(cname, caddr, fn_name, *stats.net_gas_stats.get_str_repr())

        table.add_section()

    return table


def get_line_profile_table(env: Env):

    contracts = {}
    for lp, gas_data in env._cached_line_profiles.items():

        contract_uid = (lp.contract_name, lp.address)

        # add spaces so numbers take up equal space
        lineno = str(lp.lineno).rjust(3)
        gas_data = (lineno + ": " + dedent(lp.line_src), gas_data)

        contracts.setdefault(contract_uid, {}).setdefault(lp.fn_name, []).append(
            gas_data
        )

    table = _create_table(show_contract=False)
    for (contract_name, _), fn_data in contracts.items():

        for fn_name, _data in fn_data.items():

            l_profile = []
            for code, gas_used in _data:

                if code.endswith("\n"):
                    code = code[:-1]

                if len(code) > 50:
                    code = code[:60] + " ..."

                stats = Stats(gas_used)
                data = (contract_name, fn_name, code, *stats.get_str_repr())
                l_profile.append(data)

            # sorted by mean (x[4]):
            l_profile = sorted(l_profile, key=lambda x: int(x[4]), reverse=True)

            for c, profile in enumerate(l_profile):

                cname = ""
                if c == 0:

                    if len(contract_name) > 20:
                        contract_name = "..." + contract_name[-10:]

                    if len(fn_name) > 15:
                        fn_name = fn_name[:5] + "..."

                    cname = contract_name + f"({fn_name})"

                table.add_row(cname, *profile[2:])

        table.add_section()

    return table
