from functools import cached_property

import coverage
import coverage.plugin
import vyper.ast as vy_ast
from vyper.ast.parse import parse_to_ast
from vyper.compiler.settings import OptimizationLevel

from boa.contracts.vyper.ast_utils import get_fn_ancestor_from_node
from boa.environment import Env

_JUMPI = 0x57


class CoverageTracer:
    @staticmethod
    def on_computation(computation, contract):
        cov = coverage.Coverage.current()
        if cov is None:
            return
        ast_map = contract.source_map["pc_raw_ast_map"]
        raw_trace = computation.code._trace

        if not cov.config.branch:
            lines = _record_line_coverage(raw_trace, ast_map)
            _flush_coverage(cov, lines, {})
            return

        bytecode = computation.code._raw_code_bytes
        settings = getattr(getattr(contract, "compiler_data", None), "settings", None)
        optimize = getattr(settings, "optimize", None)
        skip_arcs = optimize != OptimizationLevel.NONE
        jumpi_conditions = computation.code._jumpi_conditions
        lines, arcs = _record_coverage(
            bytecode, raw_trace, ast_map, skip_arcs, jumpi_conditions=jumpi_conditions
        )
        _flush_coverage(cov, lines, arcs)


def coverage_init(registry, options):
    plugin = TitanoboaPlugin(options)
    registry.add_file_tracer(plugin)

    # set on the class so that reset_env() doesn't disable tracing
    Env._coverage_enabled = True
    Env._coverage_tracer = CoverageTracer()

    # install JUMPI tracer on the existing singleton (if any),
    # since its _init_vm ran before _coverage_enabled was set.
    from boa.vm.py_evm import JumpiTracer

    if Env._singleton is not None:
        c = Env._singleton.evm.vm.state.computation_class
        if not isinstance(c.opcodes[_JUMPI], JumpiTracer):
            c.opcodes[_JUMPI] = JumpiTracer(c.opcodes[_JUMPI])


class TitanoboaPlugin(coverage.plugin.CoveragePlugin):
    def __init__(self, options):
        pass

    def file_reporter(self, filename):
        if filename.endswith(".vy"):
            return TitanoboaReporter(filename)


# helper function. null returns get optimized directly into a jump
# to function cleanup which maps to the parent FunctionDef ast.
def _is_null_return(ast_node):
    match ast_node:
        case vy_ast.Return(value=None):
            return True
    return False


def _branch_target(stmts, fn_node):
    stmt = stmts[0]
    return fn_node.lineno if _is_null_return(stmt) else stmt.lineno


def _branch_arcs_for_if(if_node, fn_node):
    """Compute (arc_true, arc_false) line targets for an If node."""
    arc_true = _branch_target(if_node.body, fn_node)

    # else/elif path is direct, no sibling search needed.
    if if_node.orelse:
        return arc_true, _branch_target(if_node.orelse, fn_node)

    parent = if_node._parent
    if hasattr(parent, "orelse") and any(s is if_node for s in parent.orelse):
        siblings = parent.orelse
    else:
        siblings = parent.body

    for node, next_ in zip(siblings, siblings[1:]):
        if node is if_node:
            arc_false = next_.lineno
            break
    else:
        arc_false = (
            parent.lineno if isinstance(parent, vy_ast.For) else parent.end_lineno + 1
        )

    if arc_false > fn_node.end_lineno:
        arc_false = fn_node.lineno

    return arc_true, arc_false


def _is_noop_body(body):
    """Return True if body compiles to nothing (pass, assert True)."""
    if len(body) != 1:
        return False
    stmt = body[0]
    if isinstance(stmt, vy_ast.Pass):
        return True
    if isinstance(stmt, vy_ast.Assert):
        if isinstance(stmt.test, vy_ast.NameConstant) and stmt.test.value is True:
            return True
    return False


def _is_noop_branch(if_node):
    """``if cond: pass`` without else compiles away — not a real branch."""
    if if_node.orelse:
        return False
    return _is_noop_body(if_node.body)


def _record_line_coverage(raw_trace, ast_map):
    """Walk raw_trace and record line hits only (no branch work)."""
    lines_by_file: dict[str, set] = {}
    for pc in raw_trace:
        node = ast_map.get(pc)
        if node is not None:
            filename = node.module_node.resolved_path
            if filename is not None and filename.endswith(".vy"):
                lines_by_file.setdefault(filename, set()).add(node.lineno)
    return lines_by_file


def _record_coverage(
    bytecode, raw_trace, ast_map, skip_arcs=False, jumpi_conditions=None
):
    """Walk raw_trace, record line hits and branch arcs.

    Branch arc resolution requires unoptimized bytecode where every
    JUMPI maps directly to its If node.  Branch direction comes from
    jumpi_conditions (populated by JumpiTracer); polarity is:
    jump not taken = true branch, jump taken = false branch
    (Vyper emits ISZERO before JUMPI, inverting the source condition).
    Callers should set skip_arcs=True for optimized contracts.
    """
    arcs_by_file: dict[str, set] = {}

    if skip_arcs:
        return _record_line_coverage(raw_trace, ast_map), arcs_by_file

    lines_by_file: dict[str, set] = {}
    resolved: dict[int, tuple[str, int, int, int] | None] = {}

    for i, pc in enumerate(raw_trace):
        node = ast_map.get(pc)
        if node is not None:
            filename = node.module_node.resolved_path
            if filename is not None and filename.endswith(".vy"):
                lines_by_file.setdefault(filename, set()).add(node.lineno)

        if bytecode[pc] != _JUMPI:
            continue

        if pc not in resolved:
            if not isinstance(node, vy_ast.If):
                resolved[pc] = None
                continue
            fn_node = get_fn_ancestor_from_node(node)
            if fn_node is None:
                resolved[pc] = None
                continue
            filename = node.module_node.resolved_path
            if filename is None or not filename.endswith(".vy"):
                resolved[pc] = None
                continue
            arc_true, arc_false = _branch_arcs_for_if(node, fn_node)
            resolved[pc] = (filename, node.lineno, arc_true, arc_false)

        info = resolved[pc]
        if info is None:
            continue

        filename, if_lineno, arc_true, arc_false = info

        # fallthrough (jump_taken=False) = true branch, taken = false branch
        jump_taken = jumpi_conditions[i]
        arcs = arcs_by_file.setdefault(filename, set())
        if jump_taken:
            arcs.add((if_lineno, arc_false))
        else:
            arcs.add((if_lineno, arc_true))

    return lines_by_file, arcs_by_file


def _flush_coverage(cov, lines_by_file, arcs_by_file):
    """Write line and branch arcs to the active coverage instance."""
    is_branch = cov.config.branch

    if is_branch:
        merged: dict[str, set] = {}
        for filename, lines in lines_by_file.items():
            merged.setdefault(filename, set()).update((-1, ln) for ln in lines)
        for filename, arcs in arcs_by_file.items():
            merged.setdefault(filename, set()).update(arcs)
        if merged:
            data = cov.get_data()
            data.add_arcs(merged)
            data.add_file_tracers(
                {f: "boa.coverage.TitanoboaPlugin" for f in merged if f.endswith(".vy")}
            )
    else:
        if lines_by_file:
            data = cov.get_data()
            data.add_lines(lines_by_file)
            data.add_file_tracers(
                {
                    f: "boa.coverage.TitanoboaPlugin"
                    for f in lines_by_file
                    if f.endswith(".vy")
                }
            )


class TitanoboaReporter(coverage.plugin.FileReporter):
    def __init__(self, filename, env=None):
        super().__init__(filename)

    @cached_property
    def _ast(self):
        return parse_to_ast(self.source())

    def arcs(self):
        ret = set()
        for if_node in self._ast.get_descendants(vy_ast.If):
            if _is_noop_branch(if_node):
                continue
            fn_node = get_fn_ancestor_from_node(if_node)
            arc_true, arc_false = _branch_arcs_for_if(if_node, fn_node)
            ret.add((if_node.lineno, arc_true))
            ret.add((if_node.lineno, arc_false))
        return ret

    def exit_counts(self):
        ret = {}
        for if_node in self._ast.get_descendants(vy_ast.If):
            if _is_noop_branch(if_node):
                continue
            ret[if_node.lineno] = 2
        return ret

    @cached_property
    def _lines(self):
        ret = set()

        functions = self._ast.get_children(vy_ast.FunctionDef)

        for f in functions:
            for stmt in f.body:
                ret.add(stmt.lineno)
                for node in stmt.get_descendants():
                    if isinstance(node, vy_ast.AnnAssign) and isinstance(
                        node.parent, vy_ast.For
                    ):
                        # tokenizer bug with vyper parser, just ignore it
                        continue
                    ret.add(node.lineno)

        return ret

    # OVERRIDES
    def lines(self):
        return self._lines
