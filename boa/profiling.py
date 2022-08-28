from dataclasses import dataclass
from functools import cached_property

from boa.vyper.ast_utils import get_line


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

    def merge_single(self, single: _SingleComputation) -> None:
        for line, datum in single.by_line.items():
            self.profile.setdefault((single.contract, line), Datum()).merge(datum)

    def merge(self, other: "LineProfile") -> None:
        for (contract, line), datum in other.profile.items():
            self.profile.setdefault((contract, line), Datum()).merge(datum)

    def raw_summary(self):
        return list(self.profile.items())

    def summary(
        self, display_columns=("net_tot_gas",), sortkey="net_tot_gas", limit=10
    ):
        s = self.raw_summary()

        if sortkey is not None:
            s.sort(reverse=True, key=lambda x: getattr(x[1], sortkey))
        if limit is not None and limit > 0:
            s = s[:limit]

        tmp = []
        for (contract, line), datum in s:
            data = ", ".join(f"{c}: {getattr(datum, c)}" for c in display_columns)
            line_src = get_line(contract.compiler_data.source_code, line)
            x = f"{contract.address}:{contract.compiler_data.contract_name}:{line} {data}"
            tmp.append((x, line_src))

        just = max(len(t[0]) for t in tmp)

        ret = [f"{l.ljust(just)}  {r.strip()}" for (l, r) in tmp]

        return _String("\n".join(ret))


# stupid class whose __str__ method doesn't escape (good for repl)
class _String(str):
    def __repr__(self):
        return self
