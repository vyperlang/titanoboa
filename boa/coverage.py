# Coverage data flow:
#
#   EVM execution (py-evm)
#     → computation.code._trace  (list of PCs)
#     → Env._trace_computation   (PC → AST node via source_map,
#                                  collapse nodes, group by file)
#     → CoverageCollector         (extracts lines + branch arcs from AST
#                                  nodes, writes directly to CoverageData)
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


# Max bytecode bytes to scan forward when searching for a JUMPI
# after a break/continue condition.  The compiler emits the JUMPI
# within a few instructions of the condition PUSH.
_JUMPI_SCAN_LIMIT = 20

# Max consecutive PC addresses to probe in the AST map when
# classifying which branch a JUMPI destination belongs to.
# The AST map is sparse; 30 addresses covers the gap between
# a JUMPDEST and the first mapped instruction in practice.
_PATH_CLASSIFY_LIMIT = 30


@lru_cache(maxsize=128)
def _build_jumpi_table(bytecode: bytes) -> dict[int, tuple[int | None, int]]:
    """Map each JUMPI PC -> (taken_dest, fallthrough_pc).

    Scans bytecode forward to correctly parse PUSH operands,
    tracking the most recent PUSH value before each JUMPI.
    """
    table: dict[int, tuple[int | None, int]] = {}
    last_push_value: int | None = None
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
                last_push_value = None
            pc += 1
    return table


def _find_if_jumpi(bytecode: bytes, from_pc: int) -> Optional[int]:
    """Scan bytecode forward from from_pc to find the nearest JUMPI."""
    if from_pc >= len(bytecode):
        return None
    # Advance past the full instruction at from_pc.  PUSHn opcodes are
    # multi-byte: ``PUSH1 xx`` = 2 bytes, ``PUSH2 xx xx`` = 3 bytes, etc.
    # Starting at ``from_pc + 1`` would land inside the operand, causing
    # data bytes (e.g. 0x57 inside ``PUSH2 0x0057``) to be misread as a
    # JUMPI opcode.
    scan = from_pc + _instruction_size(bytecode[from_pc])
    limit = min(from_pc + _JUMPI_SCAN_LIMIT, len(bytecode))
    while scan < limit:
        if bytecode[scan] == _JUMPI:
            return scan
        scan += _instruction_size(bytecode[scan])
    return None


def _collapse_cov_node(node: vy_ast.VyperNode) -> Optional[vy_ast.VyperNode]:
    """Collapse AST nodes for coverage line reporting.

    - Nodes inside an If.test subtree → the If node itself.
    - FunctionDef nodes → None (function-level bytecode for loop
      management, setup/teardown — invisible to coverage).
    """
    child = node
    parent = getattr(node, "_parent", None)
    while parent is not None:
        # Vyper AST preserves node identity — test subtrees are never
        # cloned, so `is` reliably identifies the original child.
        if isinstance(parent, vy_ast.If) and child is parent.test:
            return parent
        child = parent
        parent = getattr(parent, "_parent", None)

    if isinstance(node, vy_ast.FunctionDef):
        return None

    return node


def _is_descendant(node: vy_ast.VyperNode, ancestor: vy_ast.VyperNode) -> bool:
    """Return True if *node* is *ancestor* or is inside its AST subtree."""
    cur = node
    while cur is not None:
        if cur is ancestor:
            return True
        cur = getattr(cur, "_parent", None)
    return False


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
    """Return True if *node* is a compile-time constant expression.

    The Vyper compiler constant-folds expressions composed entirely of
    literals and operators (e.g. ``1 == 1``, ``True and True``).
    """
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
    """Return True if the statement generates no bytecode.

    ``pass`` compiles to nothing.  ``assert <const-true-expr>`` (e.g.
    ``assert True``, ``assert 1 == 1``) is constant-folded away by the
    compiler.  Both are invisible in the AST source map, so they cannot
    serve as branch-classification anchors.
    """
    if isinstance(ast_node, vy_ast.Pass):
        return True
    if isinstance(ast_node, vy_ast.Assert) and _is_const_expr(ast_node.test):
        return True
    return False


def _is_noop_branch(if_node: vy_ast.If) -> bool:
    """Return True if the If is a no-op branch (body all noop, no else).

    When the body is entirely no-op (pass / assert True) and there is
    no else clause, the compiler eliminates the branch — both paths
    produce identical bytecode.  Branch coverage cannot distinguish
    the two directions, so these should not be declared as branches.
    """
    return all(_is_noop(s) for s in if_node.body) and not if_node.orelse


def _branch_targets(
    if_node: vy_ast.If, fn_node: vy_ast.FunctionDef
) -> tuple[int, int, Optional[vy_ast.VyperNode], Optional[vy_ast.VyperNode]]:
    """Compute branch target info for an If node.

    Returns (true_line, false_line, true_entry_stmt, false_entry_stmt).
    """
    # --- True target ---
    first_body = if_node.body[0]
    if _is_null_return(first_body):
        true_line = fn_node.lineno
        true_stmt = None
    elif all(_is_noop(s) for s in if_node.body):
        # Body is entirely no-op (pass / assert True) — no bytecode
        # generated, so the branch falls through to the same place as
        # the false branch.  Use the fallthrough statement for JUMPI
        # classification (true_stmt) but report the no-op statement
        # line so the true arc is distinguishable from the false arc.
        true_line = first_body.lineno
        _, true_stmt = _find_false_target(if_node, fn_node)
    else:
        true_line = first_body.lineno
        true_stmt = first_body

    # --- False target ---
    if if_node.orelse:
        first_else = if_node.orelse[0]
        if _is_null_return(first_else):
            false_line, false_stmt = fn_node.lineno, None
        elif all(_is_noop(s) for s in if_node.orelse):
            false_line = first_else.lineno
            _, false_stmt = _find_false_target(if_node, fn_node)
        else:
            false_line, false_stmt = first_else.lineno, first_else
    else:
        false_line, false_stmt = _find_false_target(if_node, fn_node)

    return true_line, false_line, true_stmt, false_stmt


def _find_false_target(
    if_node: vy_ast.If, fn_node: vy_ast.FunctionDef
) -> tuple[int, Optional[vy_ast.VyperNode]]:
    """Find the false-branch target for an If without orelse.

    Returns (line, stmt_or_None).
    """
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
                return fn_node.lineno, None
            return next_.lineno, next_

    # No sibling — walk up through enclosing blocks
    ancestor = if_node._parent
    while ancestor is not fn_node:
        if isinstance(ancestor, vy_ast.For):
            return ancestor.lineno, None
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
                    return fn_node.lineno, None
                return next_.lineno, next_
        ancestor = enclosing

    return fn_node.lineno, None


def _classify_from_raw_trace(
    jumpi_pc: int,
    raw_trace: list[int],
    raw_trace_start: int,
    jumpi_table: dict[int, tuple[int | None, int]],
    true_stmt: Optional[vy_ast.VyperNode],
    false_stmt: Optional[vy_ast.VyperNode],
    if_node: vy_ast.If,
    ast_map: dict[int, vy_ast.VyperNode],
) -> tuple[Optional[str], int]:
    """Classify branch direction by checking where the JUMPI goes.

    Determines the JUMPI's taken destination, then checks which
    direction (taken vs fallthrough) leads to the true body by
    consulting the AST map.  Finally checks the raw trace to see
    which direction was actually taken.

    raw_trace_start: index into raw_trace to begin searching for the JUMPI.
    Returns (branch_result, new_raw_trace_position).  Returns None as
    branch_result when the JUMPI is not found (phantom event).
    """
    taken_dest, fallthrough = jumpi_table.get(jumpi_pc, (None, jumpi_pc + 1))
    if taken_dest is None:
        return "false", raw_trace_start

    # When taken and fallthrough converge (noop body compiled away),
    # the JUMPI is a no-op — both directions hit the same PC.
    # Report "both" so the caller records both arcs.
    if taken_dest == fallthrough:
        for i in range(raw_trace_start, len(raw_trace)):
            if raw_trace[i] == jumpi_pc:
                return "both", i + 1
        return "both", raw_trace_start

    taken_is_true = _resolve_jumpi_direction(
        taken_dest, fallthrough, ast_map, true_stmt, false_stmt, if_node
    )

    for i in range(raw_trace_start, len(raw_trace)):
        if raw_trace[i] == jumpi_pc:
            next_idx = i + 1
            if next_idx < len(raw_trace):
                actual_dest = raw_trace[next_idx]
                was_taken = actual_dest == taken_dest
                if was_taken == taken_is_true:
                    return "true", next_idx
                else:
                    return "false", next_idx
            return "false", next_idx
    # JUMPI not found in raw_trace from current position — this
    # If event is a phantom (e.g. merge-point JUMPDEST or shared
    # condition PC re-mapped to this If).  Return None so the
    # caller skips recording an arc and the cursor is unchanged.
    return None, raw_trace_start


def _resolve_jumpi_direction(
    taken_dest: int,
    fallthrough: int,
    ast_map: dict[int, vy_ast.VyperNode],
    true_stmt: Optional[vy_ast.VyperNode],
    false_stmt: Optional[vy_ast.VyperNode],
    if_node: vy_ast.If,
) -> bool:
    """Determine if JUMPI taken = true branch.

    Walk PCs forward from taken_dest and fallthrough in the AST map
    to find the first classifiable node, then check if it's in the
    true or false subtree.  Returns True if taken = true branch.

    The compiler may share calldataload instructions between branches,
    so the first mapped node can be misleading.  We walk further to
    find an unambiguous node (one that differs between the two paths).
    """

    def _classify_path(start_pc):
        """Return "true"/"false"/"exit"/None for the path.

        Scans PCs forward, collecting true/false/exit evidence.
        The compiler may share initial instructions (e.g. calldataload)
        between branches, so we scan enough PCs to find an unambiguous
        classification.  If we see both true and false evidence, the
        later (more specific) evidence wins.
        """
        result = None
        for offset in range(_PATH_CLASSIFY_LIMIT):
            node = ast_map.get(start_pc + offset)
            if node is None:
                continue
            collapsed = _collapse_cov_node(node)
            if collapsed is None:
                continue  # FunctionDef
            if collapsed is if_node:
                continue  # If-mapped JUMPDEST
            if true_stmt is not None and _is_descendant(node, true_stmt):
                return "true"
            if false_stmt is not None and _is_descendant(node, false_stmt):
                if result is None:
                    result = "false"
                continue  # Keep scanning in case a true node follows
            if not _is_descendant(node, if_node):
                return result or "exit"
        return result

    taken_class = _classify_path(taken_dest)
    fall_class = _classify_path(fallthrough)

    if taken_class == "true":
        return True
    if fall_class == "true":
        return False

    # When true_stmt is None (bare return / null return), the true
    # branch exits the function.  _classify_path returns "exit" for
    # such paths.  Distinguish "exit = true branch" from "exit =
    # past the If" by checking true_stmt: if the true body has no
    # classifiable statement, an exit path IS the true branch.
    if true_stmt is None:
        if taken_class == "exit":
            return True
        if fall_class == "exit":
            return False

    if taken_class == "false":
        return False
    if fall_class == "false":
        return True

    if taken_class == "exit":
        return True
    if fall_class == "exit":
        return False

    # Neither path classifiable — assume taken = false
    return False


def _build_coverage_events(raw_trace, ast_map):
    """Build coverage event segments from a raw PC trace.

    Returns list of (filename, events) tuples where events is
    list of (pc, collapsed_node, raw_node).
    """
    segments = []
    current_file = None
    current_events = []  # list of (pc, collapsed_node, raw_node)

    # Track FunctionDef gaps to detect for-loop backedges.
    # A backward PC jump during a FunctionDef gap means the
    # EVM jumped back to the loop header (iteration boundary).
    # Intra-expression FunctionDef PCs (e.g. If branch jumps)
    # never involve a backward PC jump.
    max_gap_pc = 0
    gap_had_backward_jump = False

    # Track max PC for non-FunctionDef nodes to detect
    # inner-loop backedges that don't cross a FunctionDef gap.
    max_node_pc = 0

    for pc in raw_trace:
        if (node := ast_map.get(pc)) is not None:
            raw_node = node
            node = _collapse_cov_node(node)
            if node is None:
                if pc < max_gap_pc:
                    gap_had_backward_jump = True
                max_gap_pc = max(max_gap_pc, pc)
                continue
            fname = node.module_node.resolved_path
            if fname != current_file:
                if current_events:
                    segments.append((current_file, current_events))
                current_file = fname
                current_events = []
                max_node_pc = 0
                max_gap_pc = 0
                gap_had_backward_jump = False
            # Detect for-loop backedge: a backward PC jump
            # during the FunctionDef gap means the EVM looped
            # back.  Insert the For-header so coverage sees
            # the backedge arc.
            if (
                gap_had_backward_jump
                and current_events
                and node is current_events[-1][1]
                and isinstance(getattr(node, "_parent", None), vy_ast.For)
            ):
                current_events.append((None, node._parent, node._parent))
                max_node_pc = pc  # reset so condition PCs don't re-trigger
            # Detect inner-loop backedge: same node at a lower
            # PC without a FunctionDef gap in between.
            elif (
                pc < max_node_pc
                and current_events
                and node is current_events[-1][1]
                and isinstance(getattr(node, "_parent", None), vy_ast.For)
            ):
                current_events.append((None, node._parent, node._parent))
                max_node_pc = pc  # reset so condition PCs don't re-trigger
            max_gap_pc = 0
            gap_had_backward_jump = False
            # Only update max_node_pc for consecutive events of
            # the same collapsed node.  Internal function calls
            # interleave helper body nodes (at high PCs) between
            # runs of the same If node; inflating max_node_pc
            # across different nodes would cause false inner-loop
            # backedge detection on the return to lower PCs.
            if current_events and node is current_events[-1][1]:
                max_node_pc = max(max_node_pc, pc)
            else:
                max_node_pc = pc
            current_events.append((pc, node, raw_node))

    if current_events:
        segments.append((current_file, current_events))

    return segments


def _find_jumpi_forward_scan(
    bytecode, pc, if_node, ast_map, is_special_body, noop_body, skip_fwd
):
    """Forward scan from event PC for special/noop bodies.

    For break/continue/bare-return/no-op bodies, the decision JUMPI
    may be unmapped.  Forward scan finds the JUMPI closest to the body.
    Returns JUMPI PC or None.
    """
    if skip_fwd or pc is None or not (is_special_body or noop_body):
        return None
    # The event PC may already BE the decision JUMPI
    if bytecode[pc] == _JUMPI:
        found = pc
    else:
        found = _find_if_jumpi(bytecode, pc)
    # Validate: the found JUMPI must belong to this If, not a
    # different one (e.g. an elif's JUMPI found via forward scan
    # from a shared PC).
    if found is not None:
        mapped = ast_map.get(found)
        if mapped is not None:
            mc = _collapse_cov_node(mapped)
            if isinstance(mc, vy_ast.If) and mc is not if_node:
                found = None
    return found


def _find_jumpi_noop_backward(bytecode, events, idx, if_node, ast_map):
    """Backward event scan for noop-else/noop-body branches.

    When the body or else is a no-op, the decision JUMPI may be unmapped.
    Scans backward through earlier event PCs to find the JUMPI.
    Returns JUMPI PC or None.
    """
    scan = idx
    while scan >= 0 and events[scan][1] is if_node:
        epc = events[scan][0]
        if epc is not None and bytecode[epc] != 0x5B:
            if bytecode[epc] == _JUMPI:
                found = epc
            else:
                found = _find_if_jumpi(bytecode, epc)
            if found is not None:
                # Validate: the found JUMPI must belong to this If,
                # not a parent or sibling.
                mapped = ast_map.get(found)
                if mapped is not None:
                    mc = _collapse_cov_node(mapped)
                    if isinstance(mc, vy_ast.If) and mc is not if_node:
                        scan -= 1
                        continue
                return found
        scan -= 1
    return None


def _find_jumpi_backward(bytecode, events, idx, if_node, ast_map):
    """General backward scan skipping BoolOp-mapped JUMPIs.

    Scans backward through events mapped to this If, skipping
    short-circuit JUMPIs from compound conditions (and/or) which
    are mapped to BoolOp.  Returns JUMPI PC or None.
    """
    scan = idx
    while scan >= 0 and events[scan][1] is if_node:
        epc = events[scan][0]
        if epc is not None and bytecode[epc] == _JUMPI:
            # Skip short-circuit JUMPIs from compound conditions
            # (and/or).  These are mapped to BoolOp, not If.
            mapped = ast_map.get(epc)
            if isinstance(mapped, vy_ast.BoolOp):
                scan -= 1
                continue
            return epc
        scan -= 1
    return None


def _has_helper_gap(events, idx, if_node):
    """Detect helper-gap in If.test with internal function calls.

    When If.test contains internal function calls, helper body nodes
    split the If's condition events into multiple runs.  Earlier runs
    may contain short-circuit JUMPIs, not the decision JUMPI.

    Returns True when the same If node reappears later AND no
    body/orelse descendant events sit between here and that
    reappearance.
    """
    saw_body = False
    body_stmts = set(id(s) for s in if_node.body) | set(
        id(s) for s in getattr(if_node, "orelse", [])
    )
    for j in range(idx + 1, len(events)):
        ej = events[j][1]
        if isinstance(ej, vy_ast.For):
            break
        if ej is if_node:
            if not saw_body:
                return True
            break
        # Walk up from the raw node to check if any ancestor
        # is a direct body/orelse statement.
        is_body = False
        cur = events[j][2]
        while cur is not None:
            if id(cur) in body_stmts:
                saw_body = True
                is_body = True
                break
            cur = getattr(cur, "_parent", None)
        # If this event is not inside the If's body/orelse AND
        # belongs to the same function, it's a sibling statement.
        # The If evaluation is complete — stop.
        if not is_body and not isinstance(ej, vy_ast.If):
            ej_fn = get_fn_ancestor_from_node(events[j][2])
            if_fn = get_fn_ancestor_from_node(if_node)
            if ej_fn is if_fn:
                break
    return False


class CoverageCollector:
    """Collects coverage data via direct CoverageData writes."""

    _PLUGIN_NAME = "boa.coverage.TitanoboaPlugin"

    def __init__(self):
        self._arcs_by_file: dict[str, set[tuple[int, int]]] = {}
        self._lines_by_file: dict[str, set[int]] = {}
        self._raw_trace_pos: dict[tuple[str, int], int] = {}
        self._next_trace_id: int = 0

    def next_trace_id(self) -> int:
        """Allocate a unique trace ID for a computation's raw_trace.

        Each computation gets its own ID.  Cross-module segments
        (A → B → A) within one computation share the same ID so
        the raw_trace cursor is preserved across segments.
        """
        tid = self._next_trace_id
        self._next_trace_id += 1
        return tid

    def record_segment(self, filename, events, bytecode, raw_trace, ast_map, trace_id):
        """Process event tuples, extract lines and branch arcs.

        events: list of (pc, collapsed_node, raw_node) tuples.
        bytecode: the raw EVM bytecode for JUMPI detection.
        raw_trace: list of PCs from computation.code._trace.
        ast_map: PC → AST node mapping from source_map.
        trace_id: unique integer identifying this computation's trace,
            allocated via next_trace_id().
        """
        if not events or filename is None or not filename.endswith(".vy"):
            return
        if "site-packages" in filename:
            return

        lines = self._lines_by_file.setdefault(filename, set())
        arcs = self._arcs_by_file.setdefault(filename, set())

        jumpi_table = _build_jumpi_table(bytecode)
        if_meta = {}
        prev_lineno = None
        # Track position in raw_trace so each JUMPI match advances.
        # Key by (filename, trace_id) so that:
        #  - cross-module segments (A → B → A) sharing the same trace
        #    don't re-match earlier JUMPIs,
        #  - child computations (e.g. extcall self) with a different
        #    trace_id get an independent cursor.
        trace_key = (filename, trace_id)
        raw_trace_pos = self._raw_trace_pos.get(trace_key, 0)

        for idx, (pc, collapsed, _) in enumerate(events):
            lines.add(collapsed.lineno)

            if isinstance(collapsed, vy_ast.If):
                if_node = collapsed
                # Only process at the last If event in a consecutive run.
                # Skip if next event is also this If node.
                if idx + 1 < len(events) and events[idx + 1][1] is if_node:
                    continue
                if id(if_node) not in if_meta:
                    fn_node = get_fn_ancestor_from_node(if_node)
                    if fn_node is None:
                        continue
                    if_meta[id(if_node)] = _branch_targets(if_node, fn_node)
                meta = if_meta[id(if_node)]
                true_line, false_line, true_stmt, false_stmt = meta

                # Find the decision JUMPI for this If using three
                # strategies: forward scan, noop backward scan, and
                # general backward scan.
                body0 = if_node.body[0]
                orelse = getattr(if_node, "orelse", [])
                noop_else = orelse and all(_is_noop(s) for s in orelse)
                noop_body = all(_is_noop(s) for s in if_node.body)
                is_special_body = isinstance(
                    body0, (vy_ast.Break, vy_ast.Continue)
                ) or _is_null_return(body0)
                # JUMPDEST (0x5B) at noop-body If events are merge
                # points after body/else execution, not condition
                # evaluations.  Skip forward scan for those.  But
                # allow JUMPDEST for break/continue/bare-return —
                # compound conditions place a JUMPDEST between
                # short-circuit operands (landing pad), and the
                # forward scan must proceed past it.
                skip_fwd = (
                    noop_body
                    and not is_special_body
                    and pc is not None
                    and bytecode[pc] == 0x5B
                )
                jumpi_pc = _find_jumpi_forward_scan(
                    bytecode, pc, if_node, ast_map, is_special_body, noop_body, skip_fwd
                )
                if jumpi_pc is None and (noop_else or noop_body):
                    jumpi_pc = _find_jumpi_noop_backward(
                        bytecode, events, idx, if_node, ast_map
                    )
                if jumpi_pc is None:
                    jumpi_pc = _find_jumpi_backward(
                        bytecode, events, idx, if_node, ast_map
                    )

                if jumpi_pc is not None:
                    if _has_helper_gap(events, idx, if_node):
                        continue

                    branch, raw_trace_pos = _classify_from_raw_trace(
                        jumpi_pc,
                        raw_trace,
                        raw_trace_pos,
                        jumpi_table,
                        true_stmt,
                        false_stmt,
                        if_node,
                        ast_map,
                    )
                    if branch == "both":
                        arcs.add((if_node.lineno, true_line))
                        arcs.add((if_node.lineno, false_line))
                    elif branch == "true":
                        arcs.add((if_node.lineno, true_line))
                    elif branch == "false":
                        arcs.add((if_node.lineno, false_line))
                continue

            # For marker: track loop boundaries for sequential arcs
            if isinstance(collapsed, vy_ast.For):
                prev_lineno = collapsed.lineno
                continue

            # Sequential arc for line coverage in branch mode
            if prev_lineno is not None and prev_lineno != collapsed.lineno:
                arcs.add((prev_lineno, collapsed.lineno))

            prev_lineno = collapsed.lineno

        self._raw_trace_pos[trace_key] = raw_trace_pos

    def flush(self):
        """Write accumulated data to the active coverage instance."""
        cov = coverage.Coverage.current()
        if cov is None:
            return

        data = cov.get_data()
        if cov.get_option("run:branch"):
            # In branch mode, lines are derived from arc endpoints.
            # Ensure every executed line appears in at least one arc
            # by adding (-1, line) entry arcs for uncovered lines.
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
        self._raw_trace_pos.clear()
        self._next_trace_id = 0


def _true_arc(if_node: vy_ast.If, fn_node: vy_ast.FunctionDef) -> int:
    """Target line for the true (body) branch of an If node."""
    return _branch_targets(if_node, fn_node)[0]


def _false_arc(if_node: vy_ast.If, fn_node: vy_ast.FunctionDef) -> int:
    """Target line for the false (else/fallthrough) branch of an If node."""
    return _branch_targets(if_node, fn_node)[1]


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
            ret.add((if_node.lineno, _true_arc(if_node, fn_node)))
            ret.add((if_node.lineno, _false_arc(if_node, fn_node)))
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
        # The collector collapses If.test nodes to the If line, so any
        # extra lines from the test subtree would appear perpetually
        # uncovered.
        for if_node in self._ast.get_descendants(vy_ast.If):
            for node in if_node.test.get_descendants():
                if isinstance(node, vy_ast.Operator):
                    continue
                if node.lineno != if_node.lineno:
                    ret.discard(node.lineno)
            if if_node.test.lineno != if_node.lineno:
                ret.discard(if_node.test.lineno)

        # Exclude keyword-only lines of multi-line statements.
        # e.g. `return (\n    expr\n)` — the `return` line has no
        # bytecode; the compiler only generates code for the expression.
        # These lines would appear perpetually uncovered.
        # Scan all statements including those nested in if/else/for.
        for f in functions:
            for stmt in f.get_descendants(vy_ast.Stmt):
                if isinstance(stmt, (vy_ast.If, vy_ast.Assert)):
                    continue  # these have bytecode on the keyword line
                if stmt.end_lineno is not None and stmt.end_lineno > stmt.lineno:
                    desc_linenos = {n.lineno for n in stmt.get_descendants()}
                    if stmt.lineno not in desc_linenos:
                        ret.discard(stmt.lineno)

        return ret

    # OVERRIDES
    def lines(self):
        return self._lines
