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
    def __init__(self):
        pass

    # coverage.py requires us to inspect the python call frame to
    # see what line number to produce. we hook into specially crafted
    # Env._trace_cov which is called for every unique pc if coverage is
    # enabled, and then back out the contract and lineno information
    # from there.

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


class TitanoboaReporter(coverage.plugin.FileReporter):
    def __init__(self, filename, env=None):
        super().__init__(filename)

    @cached_property
    def _ast(self):
        return parse_to_ast(self.source())

    def arcs(self):
        ret = set()

        for ast_node in self._ast.get_descendants(vy_ast.If):
            fn_node = get_fn_ancestor_from_node(ast_node)

            # one arc is directly into the body
            arc_true = ast_node.body[0].lineno
            if _is_null_return(ast_node.body[0]):
                arc_true = fn_node.lineno
            ret.add((ast_node.lineno, arc_true))

            # the other arc is to the end of the if statement
            # try hard to find the next executable line.
            children = ast_node._parent.get_children()
            for node, next_ in zip(children, children[1:]):
                if id(node) == id(ast_node):
                    arc_false = next_.lineno
                    break
            else:
                # the if stmt was the last stmt in the enclosing scope.
                arc_false = ast_node._parent.end_lineno + 1

            # unless there is an else or elif. then the other
            # arc is to the else/elif statement.
            if ast_node.orelse:
                arc_false = ast_node.orelse[0].lineno

            # return cases:
            # if it's past the end of the fn it's an implicit return
            if arc_false > fn_node.end_lineno:
                arc_false = fn_node.lineno
            # or it's an explicit return
            if ast_node.orelse and _is_null_return(ast_node.orelse[0]):
                arc_false = fn_node.lineno

            ret.add((ast_node.lineno, arc_false))

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
