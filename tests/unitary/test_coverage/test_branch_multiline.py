"""Branch coverage tests for multiline conditions and statements.

Tests for multiline if-conditions (and/or), multiline body statements
(return, assign, augassign, assert), continuation line filtering, and
multiline tail returns.
"""

import vyper.ast as vy_ast
from vyper.ast.parse import parse_to_ast

from .conftest import (
    _check_branch_coverage,
    _check_full_branch_coverage,
    _coverage_session,
)


def test_branch_multiline_condition():
    """Multi-line if condition: both branches hit, no missing arcs."""
    source = """\
@external
def foo(x: uint256, y: uint256) -> uint256:
    if (x > 5 and
        y > 10):
        return 1
    else:
        return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10, 20), c.foo(1, 1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_multiline_then_same_operator_no_missing_lines():
    """Multi-line if followed by another if using the same operator — no phantom missing lines."""
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
    with _coverage_session(
        source,
        lambda c: (
            c.foo(10, 20),  # true branch of first if
            c.foo(1, 1),  # false branch of first if
            c.foo(25, 1),  # true branch of second if (false on first)
            c.foo(1, 1),  # false branch of second if
        ),
    ) as analysis:
        assert not analysis.missing, (
            f"No lines should be missing when all branches are hit, "
            f"got missing lines: {analysis.missing}"
        )


def test_branch_multiline_condition_no_missing_lines():
    """Multi-line if condition: continuation lines must not appear as uncovered."""
    source = """\
@external
def foo(x: uint256, y: uint256) -> uint256:
    if (x > 5 and
        y > 10):
        return 1
    else:
        return 0
"""
    with _coverage_session(source, lambda c: (c.foo(10, 20), c.foo(1, 1))) as analysis:
        assert not analysis.missing, (
            f"No lines should be missing when both branches are hit, "
            f"got missing lines: {analysis.missing}"
        )


def test_branch_multiline_condition_partial():
    """Only true branch hit for multi-line condition — false arc missing."""
    source = """\
@external
def foo(x: uint256, y: uint256) -> uint256:
    if (x > 5 and
        y > 10):
        return 1
    else:
        return 0
"""
    missing = _check_branch_coverage(source, lambda c: c.foo(10, 20))
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    else_first = if_node.orelse[0]
    assert missing == {
        if_node.lineno: [else_first.lineno]
    }, f"Unexpected missing arcs: {missing}"


def test_branch_multiline_body_statement():
    """Multiline assignment in if-body: both branches hit, no missing arcs."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        y: uint256 = (
            x +
            1
        )
        return y
    else:
        return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_multiline_body_statement_partial():
    """Multiline assignment in if-body, only false branch hit."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        y: uint256 = (
            x +
            1
        )
        return y
    else:
        return 0
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    # True arc target is the statement line (AnnAssign line)
    stmt_line = if_node.body[0].lineno

    missing = _check_branch_coverage(source, lambda c: c.foo(1))
    assert if_node.lineno in missing, f"Expected if-line in missing: {missing}"
    assert (
        stmt_line in missing[if_node.lineno]
    ), f"Expected true arc to stmt line {stmt_line}, got {missing}"


def test_branch_multiline_return_in_body():
    """Multiline return in if-body: both branches hit, no missing arcs."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return (
            x + 1
        )
    else:
        return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_multiline_return_in_else():
    """Multiline return in else-body: both branches hit, no missing arcs."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        return (
            x + 1
        )
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_multiline_assert_in_body():
    """Multiline assert in if-body: both branches hit, no missing arcs.

    Assert has `.test` not `.value` — _bytecode_lineno must check both.
    """
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        assert (
            x < 100
        )
        return x
    return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_multiline_return_in_body_with_else():
    """Multiline return in true branch with explicit else — both arcs covered."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return (
            x + 1
        )
    else:
        return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_multiline_augassign_in_else():
    """Multiline AugAssign in else-body: both branches hit, no missing arcs."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    s: uint256 = 0
    if x > 5:
        s += 1
    else:
        s += (
            x +
            1
        )
    return s
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


# --- multiline correctness regressions ---


SOURCE_MULTILINE_RETURN_ELSE_FALLTHROUGH = """\
@external
def foo(x: uint256) -> uint256:
    y: uint256 = 0
    if x > 5:
        return (
            x + 1
        )
    else:
        y = x
    return y
"""


def test_correctness_multiline_return_else_fallthrough_both():
    """Multiline return in true body + else fallthrough — both arcs covered."""
    missing = _check_branch_coverage(
        SOURCE_MULTILINE_RETURN_ELSE_FALLTHROUGH, lambda c: (c.foo(10), c.foo(1))
    )
    assert missing == {}, f"Both branches hit, expected no missing arcs: {missing}"


def test_correctness_multiline_return_else_fallthrough_true_only():
    """True-only: true arc must be executed, false arc must be missing."""
    ast = parse_to_ast(SOURCE_MULTILINE_RETURN_ELSE_FALLTHROUGH)
    if_node = ast.get_descendants(vy_ast.If)[0]

    possible, executed, missing = _check_full_branch_coverage(
        SOURCE_MULTILINE_RETURN_ELSE_FALLTHROUGH, lambda c: c.foo(10)
    )
    # True arc should be executed
    assert (
        if_node.lineno in executed
    ), f"If-line {if_node.lineno} not in executed: {executed}"
    # False arc should be missing
    assert (
        if_node.lineno in missing
    ), f"If-line {if_node.lineno} not in missing: {missing}"


def test_correctness_multiline_return_else_fallthrough_false_only():
    """False-only: false arc must be executed, true arc must be missing."""
    ast = parse_to_ast(SOURCE_MULTILINE_RETURN_ELSE_FALLTHROUGH)
    if_node = ast.get_descendants(vy_ast.If)[0]

    possible, executed, missing = _check_full_branch_coverage(
        SOURCE_MULTILINE_RETURN_ELSE_FALLTHROUGH, lambda c: c.foo(1)
    )
    orelse_line = if_node.orelse[0].lineno
    assert (
        if_node.lineno in executed
    ), f"If-line {if_node.lineno} not in executed: {executed}"
    assert (
        orelse_line in executed[if_node.lineno]
    ), f"False arc to {orelse_line} not in executed: {executed}"
    assert (
        if_node.lineno in missing
    ), f"If-line {if_node.lineno} not in missing: {missing}"


# --- multiline no-else / elif-tail regression tests ---


def test_branch_no_else_multiline_true_return_multiline_tail():
    """If without else, multiline return in true body + multiline tail — both arcs covered."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return (
            x + 1
        )
    return (
        x + 2
    )
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_no_else_multiline_true_return_multiline_tail_partial():
    """Partial: only true branch hit — false arc (to tail) must be missing."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return (
            x + 1
        )
    return (
        x + 2
    )
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    tail_return = ast.get_descendants(vy_ast.Return)[-1]

    missing = _check_branch_coverage(source, lambda c: c.foo(10))
    assert if_node.lineno in missing, f"Expected if-line in missing: {missing}"
    assert (
        tail_return.lineno in missing[if_node.lineno]
    ), f"Expected false arc to tail return {tail_return.lineno}, got {missing}"


def test_branch_no_else_multiline_assign_multiline_tail():
    """If without else, multiline assign in true body + multiline tail — both arcs covered."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    s: uint256 = 0
    if x > 5:
        s = (
            x + 1
        )
    return (
        s + 1
    )
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"
