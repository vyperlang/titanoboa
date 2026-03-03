"""Branch coverage tests for multiline conditions and statements.

Tests for multiline if-conditions (and/or), multiline body statements
(return, assign, augassign, assert), continuation line filtering, and
multiline tail returns.
"""

import vyper.ast as vy_ast
from vyper.ast.parse import parse_to_ast

from .conftest import _check_branch_coverage, _coverage_session


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
