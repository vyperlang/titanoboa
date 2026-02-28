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


def _resolve_if(node, next_node):
    """Classify an If node's relationship with its successor in the trace."""
    parent = getattr(node, "_parent", None)

    if next_node is node:
        return "loop_reiter"
    if next_node is not None and next_node.lineno == node.body[0].lineno:
        return "true"
    if (
        node.orelse
        and next_node is not None
        and next_node.lineno == node.orelse[0].lineno
    ):
        return "false"
    if next_node is parent:
        return "for_present"
    if not node.orelse and isinstance(parent, vy_ast.For) and parent.body[-1] is node:
        return "for_insert"
    if node.orelse and next_node is not None:
        return "ghost"
    if next_node is None:
        return "func_exit"
    return "unresolved"


def _strip_if_preambles(nodes):
    """Remove preamble aliases from If evaluation runs.

    Vyper compiles body/orelse setup bytecode inline with the If
    condition evaluation.  These preamble nodes appear between
    consecutive If evaluations of the same If and create spurious
    branch arcs.

    A preamble is any non-If, non-For node sandwiched between identical
    If nodes.  For orelse Ifs, trailing preambles after the run are also
    stripped when they belong to the wrong branch subtree.
    """
    if not nodes:
        return nodes

    result = []
    i = 0
    while i < len(nodes):
        node = nodes[i]

        if isinstance(node, vy_ast.If):
            if_node = node

            # Scan the If evaluation run: consecutive If(same) nodes
            # interspersed with preamble aliases.  Preserve For nodes
            # (backedge markers from _trace_computation).
            j = i + 1
            while j < len(nodes):
                if nodes[j] is if_node:
                    j += 1
                elif (
                    j + 1 < len(nodes)
                    and nodes[j + 1] is if_node
                    and not isinstance(nodes[j], vy_ast.For)
                ):
                    # Non-If, non-For node sandwiched: preamble. Skip.
                    j += 1
                else:
                    break
            # j now points past the run (first node not followed by
            # if_node, or a For node).

            # Keep If and For nodes from the run, discard preambles.
            # Also discard body/orelse child Ifs — they appear as part
            # of the parent If's condition evaluation bytecode and are
            # not real branch entries.
            for k in range(i, j):
                if nodes[k] is if_node:
                    result.append(nodes[k])
                elif isinstance(nodes[k], vy_ast.For):
                    result.append(nodes[k])
                elif isinstance(nodes[k], vy_ast.If):
                    # Keep only if NOT a body/orelse child of if_node
                    if nodes[k]._parent is not if_node:
                        result.append(nodes[k])

            # Trailing preamble stripping (orelse Ifs only — no-else
            # trailing aliases are handled by _normalize_multiline_entries).
            if if_node.orelse and j < len(nodes) and j + 1 < len(nodes):
                trail = nodes[j]
                after = nodes[j + 1]
                body0_stmt = if_node.body[0]
                orelse0_stmt = if_node.orelse[0]
                # Case 1: trail matches neither branch entry — clear
                # preamble (sub-expression of a multiline body).
                if (
                    trail.lineno != body0_stmt.lineno
                    and trail.lineno != orelse0_stmt.lineno
                ):
                    i = j + 1
                    continue
                # Case 2: trail matches orelse but after is in body
                # range — an orelse setup before true body starts.
                if (
                    trail.lineno == orelse0_stmt.lineno
                    and body0_stmt.lineno <= after.lineno <= body0_stmt.end_lineno
                ):
                    i = j + 1
                    continue
                # Case 3: trail belongs to one branch subtree but
                # after belongs to the other — cross-branch alias.
                trail_in_body = _is_descendant(trail, body0_stmt)
                trail_in_else = _is_descendant(trail, orelse0_stmt)
                after_in_body = _is_descendant(after, body0_stmt)
                after_in_else = _is_descendant(after, orelse0_stmt)
                if (trail_in_body and after_in_else) or (
                    trail_in_else and after_in_body
                ):
                    i = j + 1
                    continue
            i = j
        else:
            result.append(node)
            i += 1

    return result


def _strip_parent_if_reruns(nodes):
    """Strip parent-If re-evaluations after nested-If false branches.

    When an inner If (no orelse) is the last statement in a parent If's
    body or orelse, the compiler re-evaluates the parent If as cleanup
    after the inner If's false branch.  These re-evaluations produce
    spurious arcs (inner → parent) and must be stripped.

    The pattern in the node stream:
      ..., If@inner, If@parent, [If@inner|If@parent]*, real_target, ...
    becomes:
      ..., If@inner, real_target, ...
    """
    if not nodes:
        return nodes

    result = []
    i = 0
    while i < len(nodes):
        node = nodes[i]
        result.append(node)

        if isinstance(node, vy_ast.If) and not node.orelse:
            parent = getattr(node, "_parent", None)
            if isinstance(parent, vy_ast.If):
                # Check if inner is the last stmt in parent's body/orelse
                if hasattr(parent, "orelse") and node in parent.orelse:
                    is_last = node is parent.orelse[-1]
                else:
                    is_last = node is parent.body[-1]

                if is_last and i + 1 < len(nodes) and nodes[i + 1] is parent:
                    # Skip all parent/inner re-evaluations
                    j = i + 1
                    while j < len(nodes) and (nodes[j] is parent or nodes[j] is node):
                        j += 1
                    i = j
                    continue

        i += 1

    return result


def _strip_post_body_if_reruns(nodes):
    """Strip If re-evaluations that follow the If's own true body.

    When an If (no orelse) has a next sibling (tail statement), the
    compiler jumps back to the If condition bytecode after the true
    body completes, before falling through to the tail.  This
    re-evaluation appears as `..., body_desc, If@X, tail_desc, ...`
    and would produce a spurious false arc (If → tail).

    Strip If@X when the preceding node is inside the If's body subtree
    and the If has no orelse.
    """
    if len(nodes) < 2:
        return nodes

    result = [nodes[0]]
    for i in range(1, len(nodes)):
        node = nodes[i]
        if (
            isinstance(node, vy_ast.If)
            and not node.orelse
            and any(_is_descendant(result[-1], stmt) for stmt in node.body)
        ):
            # This If is a post-body re-evaluation — skip it
            continue
        result.append(node)

    return result


def _normalize_if_arcs(nodes, last_funcdef):
    """Insert synthetic nodes so coverage.py sees correct branch arcs.

    First strips preamble aliases (compiler artifacts), then strips
    parent-If re-evaluations from nested-If false branches, then
    strips post-body If re-evaluations, then uses _resolve_if to
    classify each If node's relationship with its successor.  Only
    two tags require action: "for_insert" (append For-header) and
    "ghost" (remove spurious loop-exit If).

    Must run before _dedup_nodes to preserve iteration boundaries.
    """
    nodes = _strip_if_preambles(nodes)
    nodes = _strip_parent_if_reruns(nodes)
    nodes = _strip_post_body_if_reruns(nodes)
    result = []
    for i, node in enumerate(nodes):
        result.append(node)
        if not isinstance(node, vy_ast.If):
            continue

        next_node = nodes[i + 1] if i + 1 < len(nodes) else None
        tag = _resolve_if(node, next_node)

        if tag == "for_insert":
            result.append(node._parent)
        elif tag == "ghost":
            result.pop()

    if last_funcdef is not None and result and isinstance(result[-1], vy_ast.If):
        result.append(last_funcdef)

    return result


def _stmt_ancestor(node):
    """Return the nearest vy_ast.Stmt ancestor (or the node itself if it is one)."""
    cur = node
    while cur is not None and not isinstance(cur, vy_ast.Stmt):
        cur = getattr(cur, "_parent", None)
    return cur


def _is_descendant(node, ancestor):
    """Return True if *node* is *ancestor* or is inside its AST subtree."""
    cur = node
    while cur is not None:
        if cur is ancestor:
            return True
        cur = getattr(cur, "_parent", None)
    return False


def _next_sibling_stmt(if_node):
    """Return the next sibling Stmt after *if_node*, or None.

    When if_node is the last statement in its scope (e.g. an elif at
    the end of the outer If's orelse), walk up the ancestor chain to
    find the next statement after the enclosing block.
    """
    parent = if_node._parent
    siblings = (
        parent.orelse
        if hasattr(parent, "orelse") and if_node in parent.orelse
        else parent.body
    )
    for node, next_ in zip(siblings, siblings[1:]):
        if node is if_node:
            return next_

    # No next sibling — walk up to find the ancestor that is a
    # direct child of the enclosing FunctionDef, then find its
    # next sibling.  This mirrors _false_arc's fallthrough logic.
    if isinstance(parent, vy_ast.Stmt) and not isinstance(parent, vy_ast.FunctionDef):
        grandparent = getattr(parent, "_parent", None)
        if grandparent is not None and isinstance(grandparent, vy_ast.FunctionDef):
            for node, next_ in zip(grandparent.body, grandparent.body[1:]):
                if node is parent:
                    return next_

    return None


def _normalize_multiline_entries(nodes):
    """Ensure the first node after an If has the parent statement's lineno.

    When the compiler emits bytecode for a multiline branch-entry statement,
    the first traced node may be a child expression (different lineno from
    the parent Stmt).  Insert the parent Stmt node so that _dedup_nodes
    produces stmt.lineno as the arc target, matching what the reporter
    declares.

    Branch-aware: skips preamble aliases (same-If re-evaluations and
    trailing compiler setup nodes), determines which branch was taken
    by scanning for the first body-descendant node, and inserts the
    parent stmt before the real branch entry.
    """
    result = []
    i = 0
    while i < len(nodes):
        node = nodes[i]
        if isinstance(node, vy_ast.If):
            if_node = node
            result.append(node)
            # Scan past the If evaluation run (same-If repeats and
            # sandwiched preamble aliases).
            j = i + 1
            while j < len(nodes):
                if nodes[j] is if_node:
                    result.append(nodes[j])
                    j += 1
                    continue
                if _is_preamble(nodes, j, if_node):
                    result.append(nodes[j])
                    j += 1
                    continue
                break
            # j points to the first non-preamble, non-If node (or end).
            # Determine which branch was taken by scanning forward for
            # the first node inside body[0]'s subtree.  If found, the
            # true branch was taken and any preceding nodes are trailing
            # compiler aliases that should be dropped.  Otherwise the
            # false branch was taken.
            candidate, insert_at = _find_branch_entry(nodes, j, if_node)
            entry_inserted = False
            while j < len(nodes) and not isinstance(nodes[j], vy_ast.If):
                if j < insert_at:
                    # Trailing compiler alias before the real entry — drop.
                    j += 1
                    continue
                if not entry_inserted and candidate is not None:
                    result.append(candidate)
                    entry_inserted = True
                result.append(nodes[j])
                j += 1
            i = j
        else:
            result.append(node)
            i += 1
    return result


def _find_branch_entry(nodes, start, if_node):
    """Scan forward from *start* to find the real branch entry.

    Returns (candidate_stmt, insert_index) where candidate_stmt is the
    Stmt to insert (or None) and insert_index is where to insert it.
    """
    body0 = if_node.body[0]

    # Scan for the first node inside body[0] subtree (true branch).
    j = start
    while j < len(nodes) and not isinstance(nodes[j], vy_ast.If):
        if _is_descendant(nodes[j], body0):
            if (
                not isinstance(body0, (vy_ast.If, vy_ast.For))
                and body0.lineno != nodes[j].lineno
            ):
                return body0, j
            return None, j
        j += 1

    # No body[0] descendant found — false branch.  Use the first node.
    if start < len(nodes) and not isinstance(nodes[start], vy_ast.If):
        candidate = _branch_entry_candidate(if_node, nodes[start])
        if (
            candidate is not None
            and not isinstance(candidate, (vy_ast.If, vy_ast.For))
            and candidate.lineno != nodes[start].lineno
        ):
            return candidate, start

    return None, start


def _is_preamble(nodes, idx, if_node):
    """Return True if nodes[idx] is a preamble alias.

    A preamble node is immediately followed by the same If identity
    (possibly with one intervening preamble node).  We check at most
    2 positions ahead to avoid false positives from distant
    re-evaluations.
    """
    k = idx + 1
    if k < len(nodes) and nodes[k] is if_node:
        return True
    if k + 1 < len(nodes) and nodes[k + 1] is if_node:
        return True
    return False


def _branch_entry_candidate(if_node, observed):
    """Determine which branch-entry statement *observed* belongs to.

    Returns the candidate Stmt (body[0], orelse[0], or next sibling)
    if *observed* is inside its subtree, otherwise None.
    """
    # True branch: body[0]
    body0 = if_node.body[0]
    if _is_descendant(observed, body0):
        return body0

    # False branch with explicit else: orelse[0]
    if if_node.orelse:
        else0 = if_node.orelse[0]
        if _is_descendant(observed, else0):
            return else0

    # False branch without else: next sibling statement
    sibling = _next_sibling_stmt(if_node)
    if sibling is not None and _is_descendant(observed, sibling):
        return sibling

    return None


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

    # if was the last statement in its scope (no next sibling found).
    # Walk up through enclosing blocks one level at a time, looking for
    # the next sibling at each scope.  This handles nested Ifs inside
    # For loops (the next sibling is in the For body, not the function).
    ancestor = if_node._parent
    while ancestor is not fn_node:
        # If we've exhausted a For body, the false branch loops back.
        if isinstance(ancestor, vy_ast.For):
            return ancestor.lineno
        enclosing = ancestor._parent
        if enclosing is None:
            break
        # Determine which child list ancestor belongs to
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
        # No sibling at this level, keep walking up
        ancestor = enclosing

    return fn_node.lineno  # implicit return


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
