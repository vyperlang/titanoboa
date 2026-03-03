from functools import cached_property

import coverage
import coverage.plugin
import vyper.ast as vy_ast
from vyper.ast.parse import parse_to_ast

from boa.contracts.vyper.ast_utils import get_fn_ancestor_from_node

# boa.environment imports from this module, so we can't import Env at
# the top level.  import it lazily where needed to avoid the cycle.
# (environment.py is the lower-level module; coverage.py is the plugin.)

_JUMPI = 0x57


def coverage_init(registry, options):
    from boa.environment import Env

    plugin = TitanoboaPlugin(options)
    registry.add_file_tracer(plugin)
    registry.add_configurer(plugin)

    # set on the class so that reset_env() doesn't disable tracing
    Env._coverage_enabled = True


class TitanoboaPlugin(coverage.plugin.CoveragePlugin):
    def __init__(self, options):
        pass

    def configure(self, config):
        # In branch mode line_number_range returns (-1,-1) to suppress
        # pytracer arc generation, so boa.environment would show as
        # "not measured" and trigger warnings.  Only register it for
        # line-only mode where pytracer line hits are the data path.
        if not config.get_option("run:branch"):
            config.get_option("run:source_pkgs").append("boa.environment")

    def file_tracer(self, filename):
        if filename.endswith("boa/environment.py"):
            return TitanoboaTracer()

    def file_reporter(self, filename):
        if filename.endswith(".vy"):
            return TitanoboaReporter(filename)


class TitanoboaTracer(coverage.plugin.FileTracer):
    def __init__(self):
        pass

    # coverage.py requires us to inspect the python call frame to
    # see what line number to produce. we hook into specially crafted
    # Env._trace_cov which is called for every unique pc if coverage is
    # enabled, and then back out the contract and lineno information
    # from there.

    def _valid_frame(self, frame):
        from boa.environment import Env

        if hasattr(frame.f_code, "co_qualname"):
            # Python>=3.11
            code_qualname = frame.f_code.co_qualname
            return code_qualname == Env._trace_cov.__qualname__

        else:
            # in Python<3.11 we don't have co_qualname, so try hard to
            # find a match anyways. (this might fail if for some reason
            # the executing env has a monkey-patched _trace_cov
            # or something)
            env = Env.get_singleton()
            return frame.f_code == env._trace_cov.__code__

    def dynamic_source_filename(self, filename, frame):
        if not self._valid_frame(frame):
            return None
        ret = frame.f_locals["filename"]
        if ret is not None and not ret.endswith(".vy"):
            return None
        return ret

    def has_dynamic_source_filename(self):
        return True

    # https://coverage.rtfd.io/en/stable/api_plugin.html#coverage.FileTracer.line_number_range
    def line_number_range(self, frame):
        if not self._valid_frame(frame):
            return (-1, -1)

        # when branch coverage is active, suppress the pytracer's arc
        # generation — we record branch arcs directly from the EVM trace.
        if _get_branch_cov() is not None:
            return (-1, -1)

        ast_node = frame.f_locals["node"]

        start_lineno = ast_node.lineno
        end_lineno = ast_node.end_lineno
        if end_lineno is None:
            end_lineno = start_lineno
        return start_lineno, end_lineno

    # XXX: dynamic context. return function name or something
    def dynamic_context(self, frame):
        pass


# helper function. null returns get optimized directly into a jump
# to function cleanup which maps to the parent FunctionDef ast.
def _is_null_return(ast_node):
    match ast_node:
        case vy_ast.Return(value=None):
            return True
    return False


def _branch_arcs_for_if(if_node, fn_node):
    """Compute (arc_true, arc_false) line targets for an If node."""
    arc_true = if_node.body[0].lineno
    if _is_null_return(if_node.body[0]):
        arc_true = fn_node.lineno

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
        if isinstance(parent, vy_ast.For):
            arc_false = parent.lineno
        else:
            arc_false = parent.end_lineno + 1

    if if_node.orelse:
        arc_false = if_node.orelse[0].lineno
    if arc_false > fn_node.end_lineno:
        arc_false = fn_node.lineno
    if if_node.orelse and _is_null_return(if_node.orelse[0]):
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


def _record_coverage(bytecode, raw_trace, ast_map, skip_arcs=False):
    """Walk raw_trace, record line hits and branch arcs.

    Branch arc resolution requires unoptimized bytecode where every
    JUMPI maps directly to its If node and polarity is always:
    fallthrough (pc+1) = true branch, taken = false branch.
    Callers should set skip_arcs=True for optimized contracts.
    """
    lines_by_file: dict[str, set] = {}
    arcs_by_file: dict[str, set] = {}

    if skip_arcs:
        for pc in raw_trace:
            node = ast_map.get(pc)
            if node is not None:
                filename = node.module_node.resolved_path
                if filename.endswith(".vy"):
                    lines_by_file.setdefault(filename, set()).add(node.lineno)
        return lines_by_file, arcs_by_file

    resolved: dict[int, tuple[str, int, int, int] | None] = {}

    for i, pc in enumerate(raw_trace):
        node = ast_map.get(pc)
        if node is not None:
            filename = node.module_node.resolved_path
            if filename.endswith(".vy"):
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
            if not filename.endswith(".vy"):
                resolved[pc] = None
                continue
            arc_true, arc_false = _branch_arcs_for_if(node, fn_node)
            resolved[pc] = (filename, node.lineno, arc_true, arc_false)

        info = resolved[pc]
        if info is None:
            continue

        filename, if_lineno, arc_true, arc_false = info

        # fallthrough (pc+1) = true branch, taken = false branch
        fell_through = i + 1 < len(raw_trace) and raw_trace[i + 1] == pc + 1
        arcs = arcs_by_file.setdefault(filename, set())
        if fell_through:
            arcs.add((if_lineno, arc_true))
        else:
            arcs.add((if_lineno, arc_false))

    return lines_by_file, arcs_by_file


def _get_branch_cov():
    """Return the active Coverage instance if branch mode is on, else None."""
    cov = coverage.Coverage.current()
    if cov is not None and cov.config.branch:
        return cov
    return None


def _flush_coverage(cov, lines_by_file, arcs_by_file):
    """Write line and branch arcs to the active coverage instance."""
    merged: dict[str, set] = {}
    for filename, lines in lines_by_file.items():
        merged.setdefault(filename, set()).update((-1, ln) for ln in lines)
    for filename, arcs in arcs_by_file.items():
        merged.setdefault(filename, set()).update(arcs)
    if merged:
        cov.get_data().add_arcs(merged)


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
