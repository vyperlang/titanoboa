"""Branch coverage tests for nested if/elif structures.

Tests for nested if/else, elif chains, if-in-orelse,
and nested if without outer else.
"""

import vyper.ast as vy_ast
from vyper.ast.parse import parse_to_ast

from .conftest import _check_branch_coverage, _check_full_branch_coverage


def test_branch_nested_if():
    """Both branches of nested if statements are fully covered."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 10:
        if x > 20:
            return 3
        else:
            return 2
    else:
        return 1
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(25), c.foo(15), c.foo(5)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_nested_if_partial():
    """Only outer-true + inner-true hit — outer-false and inner-false missing."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 10:
        if x > 20:
            return 3
        else:
            return 2
    else:
        return 1
"""
    # Only call with x=25 → outer true, inner true
    missing = _check_branch_coverage(source, lambda c: c.foo(25))
    ast = parse_to_ast(source)
    if_nodes = ast.get_descendants(vy_ast.If)
    outer_if = if_nodes[0]
    inner_if = if_nodes[1]
    # outer-false arc should target the else body line (`return 1`)
    outer_else_line = outer_if.orelse[0].lineno
    assert outer_if.lineno in missing, f"Expected outer if {outer_if.lineno} in missing"
    assert (
        outer_else_line in missing[outer_if.lineno]
    ), f"Expected outer false target {outer_else_line} in {missing[outer_if.lineno]}"
    # inner-false arc should target the inner else body line (`return 2`)
    inner_else_line = inner_if.orelse[0].lineno
    assert inner_if.lineno in missing, f"Expected inner if {inner_if.lineno} in missing"
    assert (
        inner_else_line in missing[inner_if.lineno]
    ), f"Expected inner false target {inner_else_line} in {missing[inner_if.lineno]}"


# --- elif coverage ---


def test_branch_elif_full():
    """if/elif/else — all three paths hit → no missing arcs."""
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
    missing = _check_branch_coverage(source, lambda c: (c.foo(25), c.foo(15), c.foo(5)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_elif_only_first():
    """Only if-true path hit — elif-true and elif-false (else) arcs missing."""
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
    missing = _check_branch_coverage(source, lambda c: c.foo(25))
    ast = parse_to_ast(source)
    if_nodes = ast.get_descendants(vy_ast.If)
    inner_if = if_nodes[1]  # elif is a nested If in orelse
    # When only the outer-if-true is hit, the elif condition is never evaluated
    # so both elif arcs (true → return 2, false → return 1) should be missing
    assert (
        inner_if.lineno in missing
    ), f"Expected elif {inner_if.lineno} in missing: {missing}"
    assert (
        len(missing[inner_if.lineno]) == 2
    ), f"Expected 2 missing arcs from elif, got {missing[inner_if.lineno]}"


def test_branch_elif_only_middle():
    """Only elif path hit — if-true and else arcs missing."""
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
    missing = _check_branch_coverage(source, lambda c: c.foo(15))
    ast = parse_to_ast(source)
    if_nodes = ast.get_descendants(vy_ast.If)
    outer_if = if_nodes[0]
    inner_if = if_nodes[1]
    # outer-if true arc (to `return 3`) should be missing
    outer_true_line = outer_if.body[0].lineno
    assert outer_if.lineno in missing, f"Expected outer if {outer_if.lineno} in missing"
    assert (
        outer_true_line in missing[outer_if.lineno]
    ), f"Expected outer true target {outer_true_line} in {missing[outer_if.lineno]}"
    # elif false arc (to `return 1`) should be missing
    elif_else_line = inner_if.orelse[0].lineno
    assert inner_if.lineno in missing, f"Expected elif {inner_if.lineno} in missing"
    assert (
        elif_else_line in missing[inner_if.lineno]
    ), f"Expected elif false target {elif_else_line} in {missing[inner_if.lineno]}"


def test_branch_if_in_orelse_without_else():
    """if inside an else block with no else of its own — both arcs covered.

    Regression test for _false_arc sibling lookup: the inner if lives in
    parent.orelse, not parent.body, so the sibling search must check both.
    """
    source = """\
@external
def foo(x: uint256, y: uint256) -> uint256:
    if x > 0:
        return 1
    else:
        if y > 0:
            return 2
        return 3
"""
    missing = _check_branch_coverage(
        source, lambda c: (c.foo(1, 0), c.foo(0, 1), c.foo(0, 0))
    )
    assert missing == {}, f"Missing branch arcs: {missing}"


SOURCE_ELIF_NO_ELSE = """\
@external
def foo(x: uint256) -> uint256:
    if x > 20:
        return 3
    elif x > 10:
        return 2
    return 0
"""


def test_correctness_elif_no_else_all_branches():
    """P1 regression: if/elif without explicit else, fallthrough tail.

    When all three paths are exercised (outer true, inner true, both false),
    no branches should be missing.  Previously the inner elif's false arc
    was dropped because the compiler's outer-If re-evaluation was not
    ghost-removed (ghost was restricted to For-loop parents).
    """
    missing = _check_branch_coverage(
        SOURCE_ELIF_NO_ELSE, lambda c: (c.foo(25), c.foo(15), c.foo(5))
    )
    assert missing == {}, f"All branches hit, expected no missing: {missing}"


def test_correctness_elif_no_else_inner_false():
    """Inner elif false branch alone must produce the fallthrough arc."""
    ast = parse_to_ast(SOURCE_ELIF_NO_ELSE)
    if_nodes = ast.get_descendants(vy_ast.If)
    inner_if = if_nodes[1]  # the elif

    possible, executed, missing = _check_full_branch_coverage(
        SOURCE_ELIF_NO_ELSE, lambda c: c.foo(5)
    )
    # Inner elif must have its false arc (to return 0) executed
    inner_targets = set(executed.get(inner_if.lineno, []))
    # The false fallthrough target is `return 0` at inner_if.end_lineno + 1
    assert (
        len(inner_targets) > 0
    ), f"Inner elif@L{inner_if.lineno} should have executed arcs: {executed}"


def test_correctness_elif_no_else_multiline_tail():
    """elif fallthrough to multiline return must target the statement line.

    _false_arc uses stmt.lineno, and the tracer normalizes multiline entries
    to match, so the reporter's possible arc matches the tracer's executed arc.
    """
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 20:
        return 3
    elif x > 10:
        return 2
    return (
        x + 1
    )
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(25), c.foo(15), c.foo(5)))
    assert missing == {}, f"All branches hit, expected no missing: {missing}"


# --- nested if without outer else ---


def test_branch_nested_if_no_outer_else():
    """Inner if (no else) last in outer if body (no outer else).

    Regression: compiler re-evaluates the outer If after the inner If's
    false branch, producing spurious arcs (inner → outer) and losing
    the inner false arc (inner → return 0).
    """
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 10:
        if x > 20:
            return 3
    return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(25), c.foo(15), c.foo(5)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_nested_if_no_outer_else_exact_arcs():
    """Verify exact executed arcs for nested if without outer else."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 10:
        if x > 20:
            return 3
    return 0
"""
    ast = parse_to_ast(source)
    if_nodes = ast.get_descendants(vy_ast.If)
    outer_if = if_nodes[0]
    inner_if = if_nodes[1]
    tail = ast.get_descendants(vy_ast.Return)[-1]  # return 0

    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: (c.foo(25), c.foo(15), c.foo(5))
    )
    assert missing == {}, f"Missing: {missing}"
    # Outer if: true → inner if line, false → return 0
    outer_targets = set(executed.get(outer_if.lineno, []))
    assert outer_targets == {
        inner_if.lineno,
        tail.lineno,
    }, f"Outer executed targets: {outer_targets}"
    # Inner if: true → return 3, false → return 0
    inner_targets = set(executed.get(inner_if.lineno, []))
    assert inner_targets == {
        inner_if.body[0].lineno,
        tail.lineno,
    }, f"Inner executed targets: {inner_targets}"


def test_branch_nested_if_no_outer_else_partial():
    """Only inner-true hit — outer-false and inner-false must be missing."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 10:
        if x > 20:
            return 3
    return 0
"""
    ast = parse_to_ast(source)
    if_nodes = ast.get_descendants(vy_ast.If)
    outer_if = if_nodes[0]
    inner_if = if_nodes[1]
    tail = ast.get_descendants(vy_ast.Return)[-1]

    missing = _check_branch_coverage(source, lambda c: c.foo(25))
    # Outer false arc (to return 0) should be missing
    assert outer_if.lineno in missing, f"Outer if should be in missing: {missing}"
    assert (
        tail.lineno in missing[outer_if.lineno]
    ), f"Expected outer false arc to {tail.lineno}: {missing}"
    # Inner false arc (to return 0) should be missing
    assert inner_if.lineno in missing, f"Inner if should be in missing: {missing}"
    assert (
        tail.lineno in missing[inner_if.lineno]
    ), f"Expected inner false arc to {tail.lineno}: {missing}"


def test_branch_if_in_orelse_no_inner_else_exact_arcs():
    """If inside else block (orelse), no inner else — no extra synthetic arcs.

    Regression: executed_branch_arcs showed extra arc to outer if line
    (inner → outer) in addition to logical targets.
    """
    source = """\
@external
def foo(x: uint256, y: uint256) -> uint256:
    if x > 0:
        return 1
    else:
        if y > 0:
            return 2
    return 3
"""
    ast = parse_to_ast(source)
    if_nodes = ast.get_descendants(vy_ast.If)
    inner_if = if_nodes[1]
    tail = ast.get_descendants(vy_ast.Return)[-1]  # return 3

    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: (c.foo(1, 0), c.foo(0, 1), c.foo(0, 0))
    )
    assert missing == {}, f"Missing: {missing}"
    # Inner if should have exactly {return 2, return 3} — no extra arcs
    inner_targets = set(executed.get(inner_if.lineno, []))
    expected_inner = {inner_if.body[0].lineno, tail.lineno}
    assert (
        inner_targets == expected_inner
    ), f"Inner if executed targets: {inner_targets}, expected {expected_inner}"


def test_branch_elif_no_else_multiline_body_multiline_tail():
    """if/elif without else, multiline elif body + multiline tail.

    Regression: the inner elif's false arc targets the tail statement
    after the outer block.  Both the elif true arc and the fallthrough
    false arc must match the reporter's declared targets.
    """
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 20:
        return 3
    elif x > 10:
        return (
            x + 2
        )
    return (
        x + 1
    )
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(25), c.foo(15), c.foo(5)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_elif_no_else_multiline_tail_partial():
    """Only outer-true hit — inner elif arcs must be missing."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 20:
        return 3
    elif x > 10:
        return (
            x + 2
        )
    return (
        x + 1
    )
"""
    ast = parse_to_ast(source)
    if_nodes = ast.get_descendants(vy_ast.If)
    inner_if = if_nodes[1]  # elif

    missing = _check_branch_coverage(source, lambda c: c.foo(25))
    assert (
        inner_if.lineno in missing
    ), f"Expected elif {inner_if.lineno} in missing: {missing}"
    assert (
        len(missing[inner_if.lineno]) == 2
    ), f"Expected 2 missing arcs from elif, got {missing[inner_if.lineno]}"


# --- nested if with no-op else ---


def test_branch_nested_noop_else_no_phantom():
    """Nested if with noop else — outer-true-only must not credit inner branch.

    Regression: the AST map shares a calldataload PC between inner and
    outer If conditions.  When only the outer true branch executes, a
    phantom inner-If event appears, and the noop-else fallback incorrectly
    selects the outer If's JUMPI for the inner If, producing a phantom arc.
    """
    source = """\
@external
def f(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        if x == 2:
            return 2
        else:
            pass
    return 0
"""
    ast = parse_to_ast(source)
    if_nodes = ast.get_descendants(vy_ast.If)
    inner_if = if_nodes[1]  # if x == 2

    possible, executed, missing = _check_full_branch_coverage(source, lambda c: c.f(10))
    # Only outer-true should be executed.  Inner if must have NO executed arcs.
    inner_targets = set(executed.get(inner_if.lineno, []))
    assert inner_targets == set(), (
        f"Inner if@L{inner_if.lineno} should have no executed arcs "
        f"(phantom), got: {inner_targets}"
    )


def test_branch_nested_noop_else_full():
    """Nested if with noop else — all branches exercised."""
    source = """\
@external
def f(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        if x == 2:
            return 2
        else:
            pass
    return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.f(10), c.f(2), c.f(0)))
    assert missing == {}, f"Missing branch arcs: {missing}"
