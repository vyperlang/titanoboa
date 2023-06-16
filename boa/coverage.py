"""The titanoboa coverage plugin."""

from functools import cached_property
import os.path
import coverage.plugin

import vyper.ast as vy_ast
from vyper.ir import compile_ir

from boa.environment import Env, TracingCodeStream
import boa.interpret


def coverage_init(registry, options):
    registry.add_file_tracer(TitanoboaPlugin(options))


class TitanoboaPlugin(coverage.plugin.CoveragePlugin):
    def __init__(self, options):
        pass

    def file_tracer(self, filename):
        if filename.endswith("boa/environment.py"):
            return TitanoboaTracer()

    def file_reporter(self, filename):
        if filename.endswith(".vy"):
            return TitanoboaReporter(filename)


class TitanoboaTracer(coverage.plugin.FileTracer):
    def __init__(self, env=None):
        self.env = env or Env.get_singleton()

    def _contract_for_frame(self, frame):
        if frame.f_code.co_qualname != TracingCodeStream.__iter__.__qualname__:
            return None
        return frame.f_locals["self"]._contract

    def dynamic_source_filename(self, filename, frame):
        contract = self._contract_for_frame(frame)
        if contract is None:
            return None

        return contract.filename

    def has_dynamic_source_filename(self):
        return True

    def line_number_range(self, frame):
        contract = self._contract_for_frame(frame)
        if contract is None:
            return super().line_number_range(frame)

        pc = frame.f_locals["self"].program_counter
        pc_map = contract.source_map["pc_pos_map"]

        if (src_loc := pc_map.get(pc)) is None:
            return (-1, -1)

        (start_lineno, _, end_lineno, _) = src_loc
        return start_lineno, end_lineno


class TitanoboaReporter(coverage.plugin.FileReporter):
    def __init__(self, filename, env=None):
        super().__init__(filename)

    def lines(self):
        ret = set()
        c = boa.interpret.compiler_data(self.source(), self.filename)

        # source_map should really be in CompilerData
        _, source_map = compile_ir.assembly_to_evm(c.assembly_runtime)

        for _, v in source_map["pc_pos_map"].items():
            if v is None:
                continue
            (start_lineno, _, end_lineno, _) = v
            for i in range(start_lineno, end_lineno + 1):
                ret.add(i)

        return ret
