# Coverage data flow:
#
#   EVM execution (py-evm)
#     → computation.code._trace  (list of PCs)
#     → Env._trace_computation   (PC → AST node via source_map,
#                                  collapse/normalize/dedup, group by file)
#     → Env._trace_cov           (iterate nodes; dummy expression triggers
#                                  coverage.py line events per node)
#     → TitanoboaTracer           (coverage.py calls line_number_range and
#                                  dynamic_source_filename on each line event;
#                                  reads node/filename from f_locals)
#     → TitanoboaReporter         (declares coverable lines, possible branch
#                                  arcs, and exit_counts for each .vy file)

from functools import cached_property

import coverage.plugin
import vyper.ast as vy_ast
from vyper.ast.parse import parse_to_ast

from boa.contracts.vyper.ast_utils import get_fn_ancestor_from_node


def _collapse_cov_node(node):
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


def _dedup_nodes(nodes):
    """Remove consecutive nodes with the same lineno."""
    result = []
    last_lineno = None
    for node in nodes:
        if node.lineno != last_lineno:
            result.append(node)
            last_lineno = node.lineno
    return result


def _normalize_if_arcs(nodes, last_funcdef):
    """Resolve If branch arcs deterministically via AST subtree membership.

    Must run before _dedup_nodes to preserve iteration boundaries.
    """
    if not nodes:
        return nodes
    fn_node = get_fn_ancestor_from_node(nodes[0])
    if fn_node is None:
        fn_node = last_funcdef  # fallback
    if fn_node is None:
        return nodes
    return _resolve_branches(nodes, fn_node)


def _is_descendant(node, ancestor):
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
        self._env_cls = None

    @property
    def _Env(self):
        if self._env_cls is None:
            from boa.environment import Env

            self._env_cls = Env
        return self._env_cls

    # coverage.py requires us to inspect the python call frame to
    # see what line number to produce. we hook into specially crafted
    # Env._trace_cov which is called for every unique pc if coverage is
    # enabled, and then back out the contract and lineno information
    # from there.

    def _get_body_line(self):
        if self._body_line is None:
            import dis

            code = self._Env._trace_cov.__code__
            expected = code.co_firstlineno + self._BODY_LINE_OFFSET
            # Python >=3.13 changed starts_line from int|None to bool
            # and added line_number as the int|None attribute.
            if hasattr(dis.Instruction, "line_number"):
                lines = {
                    i.line_number
                    for i in dis.get_instructions(code)
                    if i.line_number is not None
                }
            else:
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
            return code_qualname == self._Env._trace_cov.__qualname__

        else:
            # in Python<3.11 we don't have co_qualname, so try hard to
            # find a match anyways. (this might fail if for some reason
            # the executing env has a monkey-patched _trace_cov
            # or something)
            env = self._Env.get_singleton()
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


def _branch_targets(if_node, fn_node):
    """Compute branch target info for an If node.

    Returns (true_line, false_line, true_entry_stmt, false_entry_stmt,
             false_mode, loop_owner).
    """
    # --- True target ---
    first_body = if_node.body[0]
    if _is_null_return(first_body):
        true_line = fn_node.lineno
        true_stmt = None
    else:
        true_line = first_body.lineno
        true_stmt = first_body

    # --- False target ---
    if if_node.orelse:
        first_else = if_node.orelse[0]
        if _is_null_return(first_else):
            false_line, false_stmt, false_mode, loop_owner = (
                fn_node.lineno,
                None,
                "null_return",
                None,
            )
        else:
            false_line, false_stmt, false_mode, loop_owner = (
                first_else.lineno,
                first_else,
                "explicit_else",
                None,
            )
    else:
        false_line, false_stmt, false_mode, loop_owner = _find_false_target(
            if_node, fn_node
        )

    return true_line, false_line, true_stmt, false_stmt, false_mode, loop_owner


def _find_false_target(if_node, fn_node):
    """Find the false-branch target for an If without orelse.

    Returns (line, stmt_or_None, false_mode, loop_owner).
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
                return fn_node.lineno, None, "null_return", None
            return next_.lineno, next_, "lexical_fallthrough", None

    # No sibling — walk up through enclosing blocks
    ancestor = if_node._parent
    while ancestor is not fn_node:
        if isinstance(ancestor, vy_ast.For):
            return ancestor.lineno, None, "loop_back", ancestor
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
                    return fn_node.lineno, None, "null_return", None
                return next_.lineno, next_, "lexical_fallthrough", None
        ancestor = enclosing

    return fn_node.lineno, None, "fn_exit", None


def _mark_preambles(nodes):
    """Identify preamble node positions in the raw collapsed stream.

    A preamble is a node sandwiched between same-identity If re-evaluations
    as part of condition evaluation bytecode.  After the initial evaluation
    run (consecutive same-If nodes), subsequent same-If appearances are
    post-body re-evaluations and are also marked.

    Returns a set of indices that are preamble positions.
    """
    preamble_indices = set()
    i = 0
    while i < len(nodes):
        if not isinstance(nodes[i], vy_ast.If):
            i += 1
            continue

        if_node = nodes[i]
        body0 = if_node.body[0]

        # Branch entries that are For nodes: the compiler emits the For
        # iterator expression inline with If condition evaluation, so
        # For-iterator descendants sandwiched between If re-evals are
        # evidence, not preambles.
        for_entries = []
        if isinstance(body0, vy_ast.For):
            for_entries.append(body0)
        if if_node.orelse and isinstance(if_node.orelse[0], vy_ast.For):
            for_entries.append(if_node.orelse[0])

        # Phase 1: Consume the initial evaluation run.
        # Consecutive same-If nodes with sandwiched non-If preambles.
        j = i + 1
        while j < len(nodes):
            if nodes[j] is if_node:
                # Same If re-evaluation — mark as preamble.
                preamble_indices.add(j)
                j += 1
            elif (
                not isinstance(nodes[j], vy_ast.For)
                and j + 1 < len(nodes)
                and nodes[j + 1] is if_node
            ):
                # Non-For node immediately followed by same If — preamble.
                # But NOT if it's an unrelated If.
                if isinstance(nodes[j], vy_ast.If) and nodes[j]._parent is not if_node:
                    break
                # NOT a preamble if it's a descendant of a For that is
                # the branch entry — the compiler emits the For iterator
                # inline with condition evaluation bytecode.
                if any(_is_descendant(nodes[j], fe) for fe in for_entries):
                    break
                preamble_indices.add(j)
                j += 1
            else:
                break

        # j now points past the initial evaluation run.

        # Phase 2: Trailing preamble detection.
        # After the evaluation run, the compiler may emit orelse/sibling
        # setup bytecode before the real evidence.  Scan ahead to find
        # the first body-descendant (true evidence).  Non-body nodes
        # before it are trailing preambles.
        k = j
        first_body_idx = None
        while k < len(nodes) and not isinstance(nodes[k], vy_ast.If):
            if _is_descendant(nodes[k], body0):
                first_body_idx = k
                break
            k += 1
        if first_body_idx is not None:
            for k in range(j, first_body_idx):
                if not isinstance(nodes[k], vy_ast.For):
                    preamble_indices.add(k)

        # Phase 3: Post-body re-evaluation detection.
        # After the real evidence, the compiler may jump back to the
        # If condition as a post-body re-evaluation.  Scan from j
        # (or first_body_idx) forward for same-If appearances that
        # follow body descendants — these are post-body re-evals.
        # The resolved_this_epoch check in the engine handles this,
        # so we only need to handle the case where body evidence
        # precedes the re-eval.
        scan_start = first_body_idx if first_body_idx is not None else j
        k = scan_start
        while k < len(nodes):
            if nodes[k] is if_node:
                preamble_indices.add(k)
                k += 1
            elif isinstance(nodes[k], vy_ast.If) and nodes[k]._parent is if_node:
                # Child If between evidence and post-body re-eval
                k += 1
            elif not isinstance(nodes[k], vy_ast.For) and _is_descendant(
                nodes[k], if_node
            ):
                # Node inside if_node's subtree (body or orelse descendant)
                k += 1
            else:
                break

        i = j if j > i + 1 else i + 1

    return preamble_indices


def _resolve_branches(nodes, fn_node):
    """Resolve If branch outcomes deterministically via AST subtree membership.

    Replaces all heuristic strip/normalize functions.

    Phase 1: Collapse If-evaluation runs (preamble removal).
    Phase 2: Decision engine resolves branch outcomes via subtree membership.

    State:
      pending:   list of (if_node, meta) awaiting resolution
      resolved:  {id(if_node): if_node} resolved in current epoch
      deferred:  nodes buffered while decisions are pending
    """
    # Phase 1: identify preamble positions
    preamble_indices = _mark_preambles(nodes)

    pending = []
    resolved_this_epoch = {}  # {id(if_node): if_node}
    deferred = []  # buffered nodes awaiting decision resolution
    result = []

    for idx, node in enumerate(nodes):
        # Skip preamble nodes entirely — they are compiler artifacts
        # (condition re-evaluations and branch setup bytecode) that
        # would create spurious arcs if emitted.
        if idx in preamble_indices:
            continue

        # --- For-marker: resolve loop-back Ifs, emit For, advance epoch ---
        if isinstance(node, vy_ast.For):
            # Resolve pending loop-back Ifs inside this For.
            new_pending = []
            any_resolved = False
            for if_node, meta in pending:
                *_, false_mode, loop_owner = meta
                if false_mode == "loop_back" and loop_owner is node:
                    resolved_this_epoch[id(if_node)] = if_node
                    any_resolved = True
                else:
                    new_pending.append((if_node, meta))
            pending = new_pending
            if any_resolved or not pending:
                # For resolved a loop-back or no pending: emit immediately
                result.append(node)
                if not pending:
                    result.extend(deferred)
                    deferred = []
            else:
                # For didn't resolve anything and decisions still pending:
                # defer it to preserve arc chain (If → evidence).
                deferred.append(node)
            # Epoch reset: Ifs inside this For can re-resolve next iteration
            resolved_this_epoch = {
                k: v
                for k, v in resolved_this_epoch.items()
                if not _is_descendant(v, node)
            }
            continue

        # --- Resolve ALL matching pending decisions FIRST ---
        new_pending = []
        any_resolved = False
        for if_node, meta in reversed(pending):
            true_line, false_line, true_stmt, false_stmt, false_mode, loop_owner = meta
            if true_stmt is not None and _is_descendant(node, true_stmt):
                # True branch taken.
                if true_stmt.lineno != node.lineno:
                    result.append(true_stmt)  # multiline entry fixup
                resolved_this_epoch[id(if_node)] = if_node
                any_resolved = True
                continue  # pop from pending
            if false_stmt is not None and _is_descendant(node, false_stmt):
                # False branch taken (explicit else or lexical fallthrough).
                if false_stmt.lineno != node.lineno:
                    result.append(false_stmt)  # multiline entry fixup
                resolved_this_epoch[id(if_node)] = if_node
                any_resolved = True
                continue  # pop from pending
            # Terminal loop-back false: node is outside loop_owner subtree.
            if (
                false_mode == "loop_back"
                and loop_owner is not None
                and not _is_descendant(node, loop_owner)
            ):
                result.append(loop_owner)  # For node as false evidence
                resolved_this_epoch[id(if_node)] = if_node
                any_resolved = True
                continue  # pop from pending
            new_pending.append((if_node, meta))

        pending = list(reversed(new_pending))

        # --- If node: dedup AFTER resolution, then push or skip ---
        if isinstance(node, vy_ast.If):
            if any(node is p[0] for p in pending):
                # Same If already pending — preamble re-evaluation.
                continue
            if id(node) in resolved_this_epoch:
                # Same If already resolved this epoch — post-body
                # re-evaluation.
                continue
            # New If decision — push and emit.
            meta = _branch_targets(node, fn_node)
            pending.append((node, meta))
            result.append(node)
        elif any_resolved:
            # Node resolved a decision — emit it (evidence).
            result.append(node)
            # Flush deferred only when ALL pending decisions are resolved.
            if not pending:
                result.extend(deferred)
                deferred = []
        elif pending:
            # Node didn't resolve any pending decision — defer it.
            deferred.append(node)
        else:
            # No pending decisions — emit normally.
            result.append(node)

    # --- End-of-stream drain ---
    for if_node, meta in pending:
        *_, false_mode, loop_owner = meta
        if false_mode == "loop_back" and loop_owner is not None:
            result.append(loop_owner)
        else:
            result.append(fn_node)
        resolved_this_epoch[id(if_node)] = if_node
    pending = []

    # Flush remaining deferred nodes (for statement coverage).
    result.extend(deferred)

    return result


def _true_arc(if_node, fn_node):
    """Target line for the true (body) branch of an If node."""
    return _branch_targets(if_node, fn_node)[0]


def _false_arc(if_node, fn_node):
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

        # Exclude continuation lines from multi-line If conditions.
        # The tracer collapses If.test nodes to the If line, so any
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
                if stmt.end_lineno is not None and stmt.end_lineno > stmt.lineno:
                    desc_linenos = {n.lineno for n in stmt.get_descendants()}
                    if stmt.lineno not in desc_linenos:
                        ret.discard(stmt.lineno)

        return ret

    # OVERRIDES
    def lines(self):
        return self._lines
