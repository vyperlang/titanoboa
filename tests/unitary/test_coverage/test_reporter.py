import vyper.ast as vy_ast
from vyper.ast.parse import parse_to_ast

from boa.environment import _collapse_cov_node

from .conftest import _reporter_for

# --- reporter arcs ---


def test_reporter_arcs_nested_if_last_in_block():
    """Inner if (no else) last in outer if body — reporter must emit
    the false arc to the line after the outer block, not the function def."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 10:
        if x > 20:
            return 3
    return 0
"""
    with _reporter_for(source) as reporter:
        arcs = reporter.arcs()

    ast = parse_to_ast(source)
    if_nodes = ast.get_descendants(vy_ast.If)
    inner_if = next(n for n in if_nodes if n.lineno > if_nodes[0].lineno)
    # inner if false should go to `return 0`, not fn def
    return_0 = ast.get_descendants(vy_ast.Return)[-1]
    assert (
        inner_if.lineno,
        return_0.lineno,
    ) in arcs, f"Expected arc ({inner_if.lineno}, {return_0.lineno}) in {arcs}"


def test_reporter_arcs_simple_if():
    """Reporter arcs for simple if/else match expected arc set."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        return 0
"""
    with _reporter_for(source) as reporter:
        arcs = reporter.arcs()
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    true_body = if_node.body[0]
    false_body = if_node.orelse[0]
    expected = set()
    expected.add((if_node.lineno, true_body.lineno))
    expected.add((if_node.lineno, false_body.lineno))
    assert arcs == expected, f"Arcs: {arcs}, expected: {expected}"


def test_reporter_arcs_elif():
    """Reporter arcs include arcs from both the if line and the elif line."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 20:
        return 3
    elif x > 10:
        return 2
    else:
        return 1
"""
    with _reporter_for(source) as reporter:
        arcs = reporter.arcs()
    ast = parse_to_ast(source)
    if_nodes = ast.get_descendants(vy_ast.If)
    outer_if = if_nodes[0]
    inner_if = if_nodes[1]  # elif
    # outer if should have arcs
    outer_arcs = {(f, t) for f, t in arcs if f == outer_if.lineno}
    assert len(outer_arcs) == 2, f"Expected 2 arcs from outer if, got {outer_arcs}"
    # elif should have arcs
    elif_arcs = {(f, t) for f, t in arcs if f == inner_if.lineno}
    assert len(elif_arcs) == 2, f"Expected 2 arcs from elif, got {elif_arcs}"


def test_reporter_arcs_no_if():
    """Contract with no if statements → arcs() == empty set."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    return x * 2
"""
    with _reporter_for(source) as reporter:
        arcs = reporter.arcs()
    assert arcs == set(), f"Expected empty arcs, got {arcs}"


def test_reporter_arcs_nested_for_if():
    """If last in for body → false arc targets the for header."""
    source = """\
@external
def foo(data: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for val: uint256 in data:
        if val > 5:
            total += val
    return total
"""
    with _reporter_for(source) as reporter:
        arcs = reporter.arcs()
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    for_node = if_node.get_ancestor(vy_ast.For)
    assert (
        if_node.lineno,
        for_node.lineno,
    ) in arcs, f"Expected false arc to for-header {for_node.lineno}, arcs: {arcs}"


# --- reporter lines ---


def test_reporter_lines_basic():
    """lines() includes function body lines, excludes non-body elements."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        return 0
"""
    with _reporter_for(source) as reporter:
        lines = reporter.lines()
    ast = parse_to_ast(source)
    fn_node = ast.get_descendants(vy_ast.FunctionDef)[0]
    # Body statements should be included
    for stmt in fn_node.body:
        assert stmt.lineno in lines, f"Expected line {stmt.lineno} in lines"
    # Decorator line should NOT be in lines (decorator is not a body stmt)
    assert 1 not in lines, "Decorator line should not be in lines"


def test_reporter_lines_skips_for_iterator_annassign():
    """The AnnAssign-in-For special case is excluded from lines()."""
    source = """\
@external
def foo(data: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for val: uint256 in data:
        total += val
    return total
"""
    with _reporter_for(source) as reporter:
        lines = reporter.lines()
    ast = parse_to_ast(source)
    # The AnnAssign inside `for val: uint256 in data:` gets a synthetic lineno.
    # Verify it is excluded from lines().
    for for_node in ast.get_descendants(vy_ast.For):
        for ann in for_node.get_descendants(vy_ast.AnnAssign):
            if isinstance(ann.parent, vy_ast.For):
                assert ann.lineno not in lines, (
                    f"AnnAssign-in-For line {ann.lineno} should be"
                    f" excluded from lines: {sorted(lines)}"
                )
    # For-body statement should still be included
    for_body_line = ast.get_descendants(vy_ast.For)[0].body[0].lineno
    assert (
        for_body_line in lines
    ), f"Expected for-body line {for_body_line} in lines: {sorted(lines)}"


def test_reporter_lines_multiline_if_does_not_discard_other_if_line():
    """Regression: operator nodes (Gt, Lt, etc.) carry stale line numbers from
    the first occurrence in the file. The exclusion loop must skip them or it
    will discard unrelated statement lines.

    Contract has a multi-line `if (x > 5 and y > 10):` on line 3-4, then
    `if x > 20:` on line 6. The Gt inside If@6's test has lineno=3 (stale).
    Without the fix, line 3 (the outer if) would be erroneously discarded.
    """
    source = """\
@external
def foo(x: uint256, y: uint256) -> uint256:
    if (x > 5 and
        y > 10):
        return 1
    if x > 20:
        return 2
    return 0
"""
    with _reporter_for(source) as reporter:
        lines = reporter.lines()
    ast = parse_to_ast(source)
    if_nodes = ast.get_descendants(vy_ast.If)
    outer_if = if_nodes[0]  # line 3
    inner_if = if_nodes[1]  # line 6
    # Line 3 (outer If) must NOT be discarded
    assert outer_if.lineno in lines, (
        f"Outer if line {outer_if.lineno} was erroneously discarded from lines: "
        f"{sorted(lines)}"
    )
    # Line 6 (second If) must NOT be discarded
    assert inner_if.lineno in lines, (
        f"Second if line {inner_if.lineno} was erroneously discarded from lines: "
        f"{sorted(lines)}"
    )
    # Continuation line 4 (y > 10) SHOULD be excluded
    for node in outer_if.test.get_descendants():
        if node.lineno != outer_if.lineno and not isinstance(
            node,
            (
                vy_ast.And,
                vy_ast.Or,
                vy_ast.Not,
                vy_ast.Gt,
                vy_ast.GtE,
                vy_ast.Lt,
                vy_ast.LtE,
                vy_ast.Eq,
                vy_ast.NotEq,
                vy_ast.In,
                vy_ast.NotIn,
            ),
        ):
            assert node.lineno not in lines, (
                f"Continuation line {node.lineno} should be excluded from "
                f"lines: {sorted(lines)}"
            )


def test_reporter_lines_excludes_multiline_if_continuation():
    """Continuation lines of multi-line if conditions are excluded from lines().

    The tracer collapses If.test nodes to the If line, so continuation
    lines (e.g. the second line of a wrapped condition) must not appear
    as separate statements — otherwise they'd be perpetually uncovered.
    """
    source = """\
@external
def foo(x: uint256, y: uint256) -> uint256:
    if (x > 5 and
        y > 10):
        return 1
    else:
        return 0
"""
    with _reporter_for(source) as reporter:
        lines = reporter.lines()
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    # The if-line itself must be in lines
    assert if_node.lineno in lines, f"If-line {if_node.lineno} not in lines"
    # Continuation lines from the test subtree must NOT be in lines
    for node in if_node.test.get_descendants():
        if node.lineno != if_node.lineno:
            assert node.lineno not in lines, (
                f"Continuation line {node.lineno} from If.test should be "
                f"excluded from lines: {sorted(lines)}"
            )


# --- reporter exit_counts ---


def test_reporter_exit_counts():
    """exit_counts() returns {if_line: 2} for each If node."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        return 0
"""
    with _reporter_for(source) as reporter:
        ec = reporter.exit_counts()
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    assert ec == {if_node.lineno: 2}, f"exit_counts: {ec}"


# --- _collapse_cov_node smoke test ---


def test_collapse_cov_node_behaviors():
    """Test the two key collapse behaviors: If.test → If, FunctionDef → None."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        return 0
"""
    ast = parse_to_ast(source)

    # If.test child → the If node itself
    if_node = ast.get_descendants(vy_ast.If)[0]
    test_node = if_node.test  # the `x > 5` comparison
    result = _collapse_cov_node(test_node)
    assert result is if_node, f"Expected If node, got {type(result)}"

    # FunctionDef → None
    fn_node = ast.get_descendants(vy_ast.FunctionDef)[0]
    result = _collapse_cov_node(fn_node)
    assert result is None, f"FunctionDef should collapse to None, got {result}"
