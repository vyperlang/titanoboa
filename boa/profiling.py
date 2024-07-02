import os
import statistics
from dataclasses import dataclass
from functools import cached_property
from textwrap import dedent

from eth_utils import to_checksum_address
from rich.table import Table

from boa.contracts.vyper.ast_utils import get_fn_name_from_lineno, get_line
from boa.environment import Env


@dataclass(unsafe_hash=True)
class LineInfo:
    address: str
    contract_path: str
    lineno: int
    line_src: str
    fn_name: str


@dataclass(unsafe_hash=True)
class ContractMethodInfo:
    address: str
    contract_path: str
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

    def compute_stats(self, typ: str = "net_gas") -> None:
        gas_data = getattr(self, typ)
        setattr(self, typ + "_stats", Stats(gas_data))

    def merge_gas_data(self, net_gas: int, net_tot_gas: int) -> None:
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
        source_map = self.contract.source_map["pc_raw_ast_map"]
        current_line = None
        seen = set()
        for pc in self.computation.code._trace:
            if (node := source_map.get(pc)) is not None:
                current_line = node.lineno

            # NOTE: do we still need the `current_line is not None` guard?
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
            x = f"{contract.address}:{contract.compiler_data.contract_path}:{line} {data}"
            tmp.append((x, line_src))

        just = max(len(t[0]) for t in tmp)
        ret = [f"{l.ljust(just)}  {r.strip()}" for (l, r) in tmp]
        return _String("\n".join(ret))

    def get_line_data(self):
        raw_summary = self.raw_summary()
        raw_summary.sort(reverse=True, key=lambda x: x[1].net_gas)

        line_gas_data = {}
        for (contract, line), datum in raw_summary:
            fn_name = get_fn_name_from_lineno(contract.source_map, line)

            # here we use net_gas to include child computation costs:
            line_info = LineInfo(
                address=contract.address,
                contract_path=contract.compiler_data.contract_path,
                lineno=line,
                line_src=get_line(contract.compiler_data.source_code, line),
                fn_name=fn_name,
            )

            line_gas_data[line_info] = datum.net_gas

        return line_gas_data


# stupid class whose __str__ method doesn't escape (good for repl)
class _String(str):
    def __repr__(self):
        return self


# cache gas_used for all computation (including children)
def cache_gas_used_for_computation(contract, computation):
    profile = contract.line_profile(computation)
    env = contract.env
    contract_path = contract.compiler_data.contract_path

    # -------------------- CACHE CALL PROFILE --------------------
    # get gas used. We use Datum().net_gas here instead of Datum().net_tot_gas
    # because a call's profile includes children call costs.
    # There will be double counting, but that is by choice.

    sum_net_gas = sum([i.net_gas for i in profile.profile.values()])
    sum_net_tot_gas = sum([i.net_tot_gas for i in profile.profile.values()])

    fn = contract._get_fn_from_computation(computation)
    if fn is None:
        fn_name = "unnamed"
    else:
        fn_name = fn.name

    fn = ContractMethodInfo(
        contract_path=contract_path,
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
    line_profile = profile.get_line_data()

    for line, gas_used in line_profile.items():
        env._cached_line_profiles.setdefault(line, []).append(gas_used)

    # ------------------------- RECURSION -------------------------

    # recursion for child computations
    for _computation in computation.children:
        child_contract = env.lookup_contract(_computation.msg.code_address)

        # ignore black box contracts
        if child_contract is not None:
            cache_gas_used_for_computation(child_contract, _computation)


def _create_table(for_line_profile: bool = False) -> Table:
    table = Table(title="\n")

    if not for_line_profile:
        table.add_column(
            "Contract", justify="left", style="cyan", no_wrap=True, width=30
        )
        table.add_column("Address", justify="left", style="cyan", no_wrap=True)
        table.add_column(
            "Computation", justify="left", style="cyan", no_wrap=True, width=30
        )
    else:
        table.add_column(
            "Contract", justify="left", style="cyan", no_wrap=True, width=52
        )
        table.add_column(
            "Computation", justify="left", style="cyan", no_wrap=True, width=79
        )

    table.add_column("Count", style="magenta")
    table.add_column("Mean", style="magenta")
    table.add_column("Median", style="magenta")
    table.add_column("Stdev", style="magenta")
    table.add_column("Min", style="magenta")
    table.add_column("Max", style="magenta")

    return table


def get_call_profile_table(env: Env) -> Table:
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
    sort_gas = sorted(contract_vs_mean_gas, key=lambda x: x[0], reverse=True)
    sorted_addresses = list(set([x[1] for x in sort_gas]))

    # --------------- POPULATE TABLE -----------------

    for address in sorted_addresses:
        fn_vs_mean_gas = []
        for profile in cached_contracts[address]:
            fn_vs_mean_gas.append((cache[profile].net_gas_stats.avg_gas, profile))

        # arrange from most to least expensive contracts:
        fn_vs_mean_gas = sorted(fn_vs_mean_gas, key=lambda x: x[0], reverse=True)

        for c, (_, profile) in enumerate(fn_vs_mean_gas):
            stats = cache[profile]

            # only first line should be populated for name and address
            cname = ""
            caddr = ""
            if c == 0:
                cname = str(profile.contract_path)
                caddr = address
            fn_name = profile.fn_name
            table.add_row(cname, caddr, fn_name, *stats.net_gas_stats.get_str_repr())

        table.add_section()

    return table


def get_line_profile_table(env: Env) -> Table:
    contracts: dict = {}
    for lp, gas_data in env._cached_line_profiles.items():
        contract_uid = (lp.contract_path, lp.address)

        # add spaces so numbers take up equal space
        lineno = str(lp.lineno).rjust(3)
        gas_data = (lineno + ": " + dedent(lp.line_src), gas_data)

        contracts.setdefault(contract_uid, {}).setdefault(lp.fn_name, []).append(
            gas_data
        )

    table = _create_table(for_line_profile=True)
    for (contract_path, contract_address), fn_data in contracts.items():
        contract_file_path = os.path.split(contract_path)
        contract_data_str = (
            f"Path: {contract_file_path[0]}\n"
            f"Name: {contract_file_path[1]}\n"
            f"Address: {contract_address}\n"
            f"{'-'*52}"
        )

        table.add_row(
            contract_data_str,
            "\n\n\n" + "-" * 74,
            "\n\nCount\n-----",
            "\n\nMean\n-----",
            "\n\nMedian\n-----",
            "\n\nStdev\n-----",
            "\n\nMin\n-----",
            "\n\nMax\n-----",
        )

        num_fn = 0
        for fn_name, _data in fn_data.items():
            l_profile = []
            for code, gas_used in _data:
                if code.endswith("\n"):
                    code = code[:-1]
                stats = Stats(gas_used)
                data = (contract_path, fn_name, code, *stats.get_str_repr())
                l_profile.append(data)

            # sorted by mean (x[4]):
            l_profile = sorted(l_profile, key=lambda x: int(x[4]), reverse=True)

            for c, profile in enumerate(l_profile):
                cname = ""
                if c == 0:
                    cname = f"Function: {fn_name}"
                table.add_row(cname, *profile[2:])

            if not num_fn + 1 == len(fn_data):
                table.add_row("-" * 52, "-" * 74, *["-----"] * (len(profile[2:]) - 1))
                num_fn += 1

        table.add_section()

    return table
