from functools import cached_property

import coverage.plugin
import vyper.ast as vy_ast
from vyper.ast.parse import parse_to_ast

from boa.contracts.vyper.ast_utils import get_fn_ancestor_from_node
from boa.environment import Env


def coverage_init(registry, options):
    plugin = TitanoboaPlugin(options)
    registry.add_file_tracer(plugin)
    registry.add_configurer(plugin)

    # set on the class so that reset_env() doesn't disable tracing
    Env._coverage_enabled = True


class TitanoboaPlugin(coverage.plugin.CoveragePlugin):
    def __init__(self, options):
        pass

    def configure(self, config):
        config.get_option("run:source_pkgs").append("boa.environment")

    def file_tracer(self, filename):
        if filename.endswith("boa/environment.py"):
            return TitanoboaTracer()

    def file_reporter(self, filename):
        if filename.endswith(".vy"):
            return TitanoboaReporter(filename)


class TitanoboaTracer(coverage.plugin.FileTracer):
    # _trace_cov layout (see Env._trace_cov):
    #   def _trace_cov(self, filename, nodes):   # +0
    #       node = None                           # +1
    #       for node in nodes:                    # +2
    #           filename  # noqa: B018            # +3  <-- body line
    #
    # We only want line events from the body expression (+3) where
    # `node` in f_locals holds the current loop value. The for-header
    # (+2) fires with a stale `node` from the previous iteration which
    # would produce spurious arcs.
    _BODY_LINE_OFFSET = 3

    def __init__(self):
        self._body_line = None

    # coverage.py requires us to inspect the python call frame to
    # see what line number to produce. we hook into specially crafted
    # Env._trace_cov which is called for every unique pc if coverage is
    # enabled, and then back out the contract and lineno information
    # from there.

    def _get_body_line(self):
        if self._body_line is None:
            import dis

            code = Env._trace_cov.__code__
            expected = code.co_firstlineno + self._BODY_LINE_OFFSET
            lines = {
                i.starts_line
                for i in dis.get_instructions(code)
                if i.starts_line is not None
            }
            if expected not in lines:
                raise RuntimeError(
                    f"_BODY_LINE_OFFSET={self._BODY_LINE_OFFSET} does not match "
                    f"_trace_cov bytecode lines: {sorted(lines)}"
                )
            self._body_line = expected
        return self._body_line

    def _valid_frame(self, frame):
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

        # Only report on the body line of _trace_cov's loop where
        # `node` in f_locals holds the current (not stale) value.
        if frame.f_lineno != self._get_body_line():
            return (-1, -1)

        node = frame.f_locals.get("node")
        if node is None:
            return (-1, -1)

        # Always (lineno, lineno) — single-line spans. Multi-line constructs
        # (e.g. multi-line if conditions) are collapsed to their start line
        # by _collapse_cov_node, and coverage.py arc tracking operates per-line.
        return (node.lineno, node.lineno)

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


def _true_arc(if_node, fn_node):
    """Target line for the true (body) branch of an If node."""
    first_body = if_node.body[0]
    if _is_null_return(first_body):
        return fn_node.lineno
    return first_body.lineno


def _false_arc(if_node, fn_node):
    """Target line for the false (else/fallthrough) branch of an If node."""
    # explicit else/elif
    if if_node.orelse:
        first_else = if_node.orelse[0]
        if _is_null_return(first_else):
            return fn_node.lineno
        return first_else.lineno

    # find the next sibling statement after the if
    children = if_node._parent.get_children()
    for node, next_ in zip(children, children[1:]):
        if id(node) == id(if_node):
            target = next_.lineno
            # past end of function → implicit return
            if target > fn_node.end_lineno:
                return fn_node.lineno
            return target

    # if was the last statement in its scope (no next sibling found)
    if isinstance(if_node._parent, vy_ast.For):
        return if_node._parent.lineno  # loop back to for header

    # fallthrough to next line after enclosing block
    target = if_node._parent.end_lineno + 1
    if target > fn_node.end_lineno:
        return fn_node.lineno  # implicit return
    return target


class TitanoboaReporter(coverage.plugin.FileReporter):
    def __init__(self, filename, env=None):
        super().__init__(filename)

    @cached_property
    def _ast(self):
        return parse_to_ast(self.source())

    def arcs(self):
        ret = set()
        for if_node in self._ast.get_descendants(vy_ast.If):
            fn_node = get_fn_ancestor_from_node(if_node)
            ret.add((if_node.lineno, _true_arc(if_node, fn_node)))
            ret.add((if_node.lineno, _false_arc(if_node, fn_node)))
        return ret

    def exit_counts(self):
        ret = {}
        for ast_node in self._ast.get_descendants(vy_ast.If):
            ret[ast_node.lineno] = 2
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
