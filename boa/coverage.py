# Coverage data flow:
#
#   EVM execution (py-evm)
#     → computation.code._trace  (list of every PC executed, in order)
#     → Env._trace_computation   (walks trace + child computations)
#     → BranchCollector           (at each JUMPI mapped to an If node,
#                                  checks next PC to determine direction,
#                                  writes arcs directly to CoverageData)
#     → TitanoboaReporter         (declares coverable lines, possible branch
#                                  arcs, and exit_counts for each .vy file)

from functools import cached_property, lru_cache
from typing import Optional

import coverage
import coverage.plugin
import vyper.ast as vy_ast
from vyper.ast.parse import parse_to_ast

from boa.contracts.vyper.ast_utils import get_fn_ancestor_from_node

_JUMPI = 0x57


def _instruction_size(op: int) -> int:
    """Return byte-length of EVM instruction (1 for most, 1+n for PUSHn)."""
    if 0x5F <= op <= 0x7F:
        return (op - 0x5F) + 1
    return 1


@lru_cache(maxsize=128)
def _build_jumpi_table(bytecode: bytes) -> dict[int, tuple[int, int]]:
    """Map each JUMPI PC -> (taken_dest, fallthrough_pc).

    Scans bytecode, tracking the most recent PUSH value before each JUMPI.
    The taken destination is the value pushed onto the stack.
    The fallthrough is always JUMPI_PC + 1.
    """
    table: dict[int, tuple[int, int]] = {}
    last_push_value: int = 0
    pc = 0
    while pc < len(bytecode):
        op = bytecode[pc]
        if op == _JUMPI:
            table[pc] = (last_push_value, pc + 1)
        if 0x5F <= op <= 0x7F:
            n = op - 0x5F
            if n == 0:
                last_push_value = 0
            else:
                last_push_value = int.from_bytes(bytecode[pc + 1 : pc + 1 + n], "big")
            pc += _instruction_size(op)
        else:
            if op != _JUMPI:
                last_push_value = 0
            pc += 1
    return table


def _collapse_to_if(node: vy_ast.VyperNode) -> Optional[vy_ast.If]:
    """If this node is inside an If.test subtree, return that If node.
    Otherwise return the node itself if it's an If, else None."""
    if isinstance(node, vy_ast.If):
        return node
    child = node
    parent = getattr(node, "_parent", None)
    while parent is not None:
        if isinstance(parent, vy_ast.If) and child is parent.test:
            return parent
        child = parent
        parent = getattr(parent, "_parent", None)
    return None


def _collapse_cov_node(node: vy_ast.VyperNode) -> Optional[vy_ast.VyperNode]:
    """Collapse AST nodes for coverage line reporting.

    - Nodes inside an If.test subtree → the If node itself.
    - FunctionDef nodes → None (setup/teardown bytecode).
    """
    child = node
    parent = getattr(node, "_parent", None)
    while parent is not None:
        if isinstance(parent, vy_ast.If) and child is parent.test:
            return parent
        child = parent
        parent = getattr(parent, "_parent", None)

    if isinstance(node, vy_ast.FunctionDef):
        return None

    return node


def coverage_init(registry, options):
    from boa.environment import Env

    plugin = TitanoboaPlugin(options)
    registry.add_file_tracer(plugin)

    # set on the class so that reset_env() doesn't disable tracing
    Env._coverage_enabled = True


class TitanoboaPlugin(coverage.plugin.CoveragePlugin):
    def __init__(self, options):
        pass

    def file_tracer(self, filename):
        return None

    def file_reporter(self, filename):
        if filename.endswith(".vy"):
            return TitanoboaReporter(filename)


# helper function. null returns get optimized directly into a jump
# to function cleanup which maps to the parent FunctionDef ast.
def _is_null_return(ast_node: vy_ast.VyperNode) -> bool:
    match ast_node:
        case vy_ast.Return(value=None):
            return True
    return False


def _is_const_expr(node: vy_ast.VyperNode) -> bool:
    """Return True if *node* is a compile-time constant expression."""
    if isinstance(node, (vy_ast.NameConstant, vy_ast.Int, vy_ast.Decimal, vy_ast.Str)):
        return True
    if isinstance(node, (vy_ast.Compare, vy_ast.BinOp)):
        return _is_const_expr(node.left) and _is_const_expr(node.right)
    if isinstance(node, vy_ast.BoolOp):
        return all(_is_const_expr(v) for v in node.values)
    if isinstance(node, vy_ast.UnaryOp):
        return _is_const_expr(node.operand)
    return False


def _is_noop(ast_node: vy_ast.VyperNode) -> bool:
    """Return True if the statement generates no bytecode."""
    if isinstance(ast_node, vy_ast.Pass):
        return True
    if isinstance(ast_node, vy_ast.Assert) and _is_const_expr(ast_node.test):
        return True
    return False


def _is_noop_branch(if_node: vy_ast.If) -> bool:
    """Return True if the If is a no-op branch (body all noop, no else).

    The compiler eliminates the branch entirely — both paths produce
    identical bytecode — so it cannot be tracked.
    """
    return all(_is_noop(s) for s in if_node.body) and not if_node.orelse


def _branch_targets(
    if_node: vy_ast.If, fn_node: vy_ast.FunctionDef
) -> tuple[int, int]:
    """Compute (true_line, false_line) for an If node."""
    # --- True target ---
    first_body = if_node.body[0]
    if _is_null_return(first_body):
        true_line = fn_node.lineno
    elif all(_is_noop(s) for s in if_node.body):
        true_line = first_body.lineno
    else:
        true_line = first_body.lineno

    # --- False target ---
    if if_node.orelse:
        first_else = if_node.orelse[0]
        if _is_null_return(first_else):
            false_line = fn_node.lineno
        else:
            false_line = first_else.lineno
    else:
        false_line = _find_false_target(if_node, fn_node)

    return true_line, false_line


def _find_false_target(
    if_node: vy_ast.If, fn_node: vy_ast.FunctionDef
) -> int:
    """Find the false-branch target line for an If without orelse."""
    # Check immediate siblings first
    parent = if_node._parent
    siblings = (
        parent.orelse
        if hasattr(parent, "orelse") and if_node in parent.orelse
        else parent.body
    )
    for node, next_ in zip(siblings, siblings[1:]):
        if node is if_node:
            if _is_null_return(next_):
                return fn_node.lineno
            return next_.lineno

    # No sibling — walk up through enclosing blocks
    ancestor = if_node._parent
    while ancestor is not fn_node:
        if isinstance(ancestor, vy_ast.For):
            return ancestor.lineno
        enclosing = ancestor._parent
        if enclosing is None:
            break
        if hasattr(enclosing, "orelse") and ancestor in enclosing.orelse:
            scope = enclosing.orelse
        elif hasattr(enclosing, "body"):
            scope = enclosing.body
        else:
            ancestor = enclosing
            continue
        for node, next_ in zip(scope, scope[1:]):
            if node is ancestor:
                if _is_null_return(next_):
                    return fn_node.lineno
                return next_.lineno
        ancestor = enclosing

    return fn_node.lineno


class BranchCollector:
    """Collects coverage data via direct CoverageData writes.

    Walks the raw PC trace.  For each JUMPI whose ast_map entry
    maps to an If node, checks the next PC in the trace to determine
    which direction was taken, and records the corresponding arc.
    """

    _PLUGIN_NAME = "boa.coverage.TitanoboaPlugin"

    def __init__(self):
        self._arcs_by_file: dict[str, set[tuple[int, int]]] = {}
        self._lines_by_file: dict[str, set[int]] = {}

    def trace_computation(self, computation, ast_map, bytecode):
        """Walk the raw trace and record lines + branch arcs."""
        jumpi_table = _build_jumpi_table(bytecode)
        raw_trace = computation.code._trace

        # Cache: if_node id -> (true_line, false_line)
        branch_meta: dict[int, tuple[int, int]] = {}

        for i, pc in enumerate(raw_trace):
            node = ast_map.get(pc)
            if node is None:
                continue

            collapsed = _collapse_cov_node(node)
            if collapsed is None:
                continue  # FunctionDef setup/teardown

            fname = collapsed.module_node.resolved_path
            if not fname.endswith(".vy") or "site-packages" in fname:
                continue

            lines = self._lines_by_file.setdefault(fname, set())
            lines.add(collapsed.lineno)

            # Branch detection: is this PC a JUMPI mapped to an If?
            if bytecode[pc] != _JUMPI:
                continue

            if_node = _collapse_to_if(node)
            if if_node is None:
                continue

            # Skip short-circuit JUMPIs from compound conditions (and/or).
            # These are mapped to BoolOp nodes, not to the If or its test.
            if isinstance(node, vy_ast.BoolOp):
                continue

            # Skip noop branches (compiler eliminates them)
            if _is_noop_branch(if_node):
                continue

            fn_node = get_fn_ancestor_from_node(if_node)
            if fn_node is None:
                continue

            # Get branch targets
            if id(if_node) not in branch_meta:
                branch_meta[id(if_node)] = _branch_targets(if_node, fn_node)
            true_line, false_line = branch_meta[id(if_node)]

            # Determine direction from the next PC in the trace
            if pc not in jumpi_table:
                continue
            taken_dest, fallthrough = jumpi_table[pc]

            if i + 1 < len(raw_trace):
                next_pc = raw_trace[i + 1]
                was_taken = (next_pc == taken_dest)
            else:
                # End of trace = condition was false (fell through to end)
                was_taken = False

            # Determine if taken = true branch or false branch.
            # The compiler puts the true-body label on the stack before
            # JUMPI, so taken = true body, fallthrough = false/else.
            # But the compiler may also invert this (ISZERO + JUMPI),
            # so we need to check which direction leads to the true body.
            #
            # Strategy: look at what AST node the taken destination maps to.
            # If it's in the true body, taken = true. If it's in the false
            # body (orelse) or past the If, taken = false.
            taken_is_true = _is_taken_true(
                taken_dest, fallthrough, ast_map, if_node
            )

            arcs = self._arcs_by_file.setdefault(fname, set())
            if was_taken == taken_is_true:
                arcs.add((if_node.lineno, true_line))
            else:
                arcs.add((if_node.lineno, false_line))

    def flush(self):
        """Write accumulated data to the active coverage instance."""
        cov = coverage.Coverage.current()
        if cov is None:
            return

        data = cov.get_data()
        if cov.get_option("run:branch"):
            # In branch mode, lines are derived from arc endpoints.
            # Ensure every executed line appears in at least one arc.
            for filename, lines in self._lines_by_file.items():
                arcs = self._arcs_by_file.setdefault(filename, set())
                arc_lines = set()
                for a, b in arcs:
                    if a > 0:
                        arc_lines.add(a)
                    if b > 0:
                        arc_lines.add(b)
                for line in lines - arc_lines:
                    arcs.add((-1, line))
            if self._arcs_by_file:
                data.add_arcs(self._arcs_by_file)
        else:
            if self._lines_by_file:
                data.add_lines(self._lines_by_file)

        all_files = set(self._arcs_by_file) | set(self._lines_by_file)
        tracers = {f: self._PLUGIN_NAME for f in all_files if f.endswith(".vy")}
        if tracers:
            data.add_file_tracers(tracers)

        self._arcs_by_file.clear()
        self._lines_by_file.clear()


def _is_taken_true(
    taken_dest: int,
    fallthrough: int,
    ast_map: dict[int, vy_ast.VyperNode],
    if_node: vy_ast.If,
) -> bool:
    """Determine whether the JUMPI taken destination is the true branch.

    Probes the ast_map at taken_dest and fallthrough to see which
    side of the If they land in.
    """
    taken_class = _classify_dest(taken_dest, ast_map, if_node)
    fall_class = _classify_dest(fallthrough, ast_map, if_node)

    if taken_class == "true":
        return True
    if fall_class == "true":
        return False
    if taken_class == "false":
        return False
    if fall_class == "false":
        return True

    # Default: the old IR codegen uses ISZERO + JUMPI, so taken = false body.
    return False


def _classify_dest(
    pc: int,
    ast_map: dict[int, vy_ast.VyperNode],
    if_node: vy_ast.If,
) -> Optional[str]:
    """Classify a JUMPI destination as 'true', 'false', or None.

    Scans forward from pc in the ast_map to find the first
    classifiable node.
    """
    # The JUMPDEST itself may not be in ast_map, scan a few PCs forward.
    for offset in range(30):
        node = ast_map.get(pc + offset)
        if node is None:
            continue
        collapsed = _collapse_cov_node(node)
        if collapsed is None:
            continue  # FunctionDef
        if collapsed is if_node:
            continue  # If-mapped JUMPDEST, keep scanning

        # Check if node is in the true body
        for stmt in if_node.body:
            if _is_descendant(node, stmt):
                return "true"
        # Check if node is in the false body (orelse)
        if if_node.orelse:
            for stmt in if_node.orelse:
                if _is_descendant(node, stmt):
                    return "false"
        # Node is outside the If entirely — it's the fallthrough
        return "false"

    return None


def _is_descendant(node: vy_ast.VyperNode, ancestor: vy_ast.VyperNode) -> bool:
    """Return True if *node* is *ancestor* or is inside its AST subtree."""
    cur = node
    while cur is not None:
        if cur is ancestor:
            return True
        cur = getattr(cur, "_parent", None)
    return False


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
            true_line, false_line = _branch_targets(if_node, fn_node)
            ret.add((if_node.lineno, true_line))
            ret.add((if_node.lineno, false_line))
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

        # Exclude continuation lines from multi-line If conditions.
        for if_node in self._ast.get_descendants(vy_ast.If):
            for node in if_node.test.get_descendants():
                if isinstance(node, vy_ast.Operator):
                    continue
                if node.lineno != if_node.lineno:
                    ret.discard(node.lineno)
            if if_node.test.lineno != if_node.lineno:
                ret.discard(if_node.test.lineno)

        # Exclude keyword-only lines of multi-line statements.
        for f in functions:
            for stmt in f.get_descendants(vy_ast.Stmt):
                if isinstance(stmt, (vy_ast.If, vy_ast.Assert)):
                    continue
                if stmt.end_lineno is not None and stmt.end_lineno > stmt.lineno:
                    desc_linenos = {n.lineno for n in stmt.get_descendants()}
                    if stmt.lineno not in desc_linenos:
                        ret.discard(stmt.lineno)

        return ret

    # OVERRIDES
    def lines(self):
        return self._lines
