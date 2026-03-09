"""Invariant tests for BranchCollector.

Verify that executed arcs ⊆ possible arcs and that branch
classification is correct across high-risk scenarios.
"""

from .conftest import _check_full_branch_coverage


def _assert_branch_invariants(source, calls_fn):
    """Assert executed arcs ⊆ possible arcs and return (possible, executed, missing)."""
    possible, executed, missing = _check_full_branch_coverage(source, calls_fn)
    # executed_branch_arcs() returns {line: [target_lines]}
    # Convert to set of (line, target) tuples for comparison
    executed_arcs = set()
    for line, targets in executed.items():
        for target in targets:
            executed_arcs.add((line, target))
    assert (
        executed_arcs <= possible
    ), f"Executed arcs not in possible: {executed_arcs - possible}"
    return possible, executed, missing


class TestCollectorInvariants:
    def test_simple_if_else_both_branches(self):
        source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        return 0
"""
        _, _, missing = _assert_branch_invariants(
            source, lambda c: (c.foo(10), c.foo(1))
        )
        assert missing == {}

    def test_if_without_else_both_branches(self):
        source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    return 0
"""
        _, _, missing = _assert_branch_invariants(
            source, lambda c: (c.foo(10), c.foo(1))
        )
        assert missing == {}

    def test_if_in_for_loop_back_false(self):
        source = """\
@external
def foo(xs: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for x: uint256 in xs:
        if x > 5:
            total += x
    return total
"""
        _, _, missing = _assert_branch_invariants(
            source, lambda c: (c.foo([1, 10]), c.foo([]))
        )
        assert missing == {}

    def test_if_in_for_with_else_both_branches(self):
        source = """\
@external
def foo(xs: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for x: uint256 in xs:
        if x > 5:
            total += x
        else:
            total += 1
    return total
"""
        _, _, missing = _assert_branch_invariants(source, lambda c: c.foo([1, 10]))
        assert missing == {}

    def test_nested_if_outer_true_inner_both(self):
        source = """\
@external
def foo(x: uint256, y: uint256) -> uint256:
    if x > 5:
        if y > 10:
            return 2
        else:
            return 1
    else:
        return 0
"""
        _, _, missing = _assert_branch_invariants(
            source, lambda c: (c.foo(10, 20), c.foo(10, 1), c.foo(1, 1))
        )
        assert missing == {}

    def test_elif_without_else_all_paths(self):
        source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 10:
        return 2
    elif x > 5:
        return 1
    return 0
"""
        _, _, missing = _assert_branch_invariants(
            source, lambda c: (c.foo(20), c.foo(7), c.foo(1))
        )
        assert missing == {}

    def test_multiline_if_condition(self):
        source = """\
@external
def foo(x: uint256, y: uint256) -> uint256:
    if (
        x > 5
        and y > 10
    ):
        return 1
    else:
        return 0
"""
        _, _, missing = _assert_branch_invariants(
            source, lambda c: (c.foo(10, 20), c.foo(1, 1))
        )
        assert missing == {}

    def test_for_zero_iterations_as_branch_target(self):
        """If false branch targets a For that executes zero iterations."""
        source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    total: uint256 = x
    for i: uint256 in range(3):
        total += 1
    return total
"""
        _, _, missing = _assert_branch_invariants(
            source, lambda c: (c.foo(10), c.foo(1))
        )
        assert missing == {}

    def test_if_without_else_false_only(self):
        """Only the false branch is taken in a single call."""
        source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    return 0
"""
        _, _, missing = _assert_branch_invariants(source, lambda c: c.foo(1))
        # Only false branch taken — true branch should be missing
        assert len(missing) > 0

    def test_nested_if_no_outer_else(self):
        source = """\
@external
def foo(x: uint256, y: uint256) -> uint256:
    if x > 5:
        if y > 10:
            return 2
        return 1
    return 0
"""
        _, _, missing = _assert_branch_invariants(
            source, lambda c: (c.foo(10, 20), c.foo(10, 1), c.foo(1, 1))
        )
        assert missing == {}

    def test_multiline_true_return_else_fallthrough(self):
        """Multiline return in true body + else that falls through."""
        source = """\
@external
def foo(x: uint256, y: uint256) -> uint256:
    result: uint256 = y
    if x > 5:
        return (
            y + 1
        )
    else:
        result = y + 2
    return result
"""
        _, _, missing = _assert_branch_invariants(
            source, lambda c: (c.foo(10, 3), c.foo(1, 3))
        )
        assert missing == {}

    def test_elif_no_else_multiline_tail(self):
        """Elif without else, multiline tail return."""
        source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 10:
        return 2
    elif x > 5:
        return 1
    return (
        x + 100
    )
"""
        _, _, missing = _assert_branch_invariants(
            source, lambda c: (c.foo(20), c.foo(7), c.foo(1))
        )
        assert missing == {}

    def test_nested_if_no_outer_else_inner_false(self):
        """Nested if, no outer else, inner false path."""
        source = """\
@external
def foo(x: uint256, y: uint256) -> uint256:
    if x > 5:
        if y > 10:
            return 2
        else:
            return 1
    return 0
"""
        _, _, missing = _assert_branch_invariants(
            source, lambda c: (c.foo(10, 20), c.foo(10, 1), c.foo(1, 1))
        )
        assert missing == {}

    def test_if_in_for_terminal_false_single_iteration(self):
        """Single element, false only in loop."""
        source = """\
@external
def foo(xs: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for x: uint256 in xs:
        if x > 5:
            total += x
        else:
            total += 1
    return total
"""
        _, _, missing = _assert_branch_invariants(source, lambda c: c.foo([1]))
        # Only false branch taken for the if — true should be missing
        assert len(missing) > 0

    def test_for_true_branch_zero_iterations(self):
        """If true branch is For with zero iterations."""
        source = """\
@external
def foo(x: uint256, xs: DynArray[uint256, 10]) -> uint256:
    if x > 5:
        total: uint256 = 0
        for v: uint256 in xs:
            total += v
        return total
    return 0
"""
        _, _, missing = _assert_branch_invariants(
            source, lambda c: (c.foo(10, []), c.foo(1, []))
        )
        assert missing == {}

    def test_for_false_branch_zero_iterations(self):
        """If false branch is For with zero iterations."""
        source = """\
@external
def foo(x: uint256, xs: DynArray[uint256, 10]) -> uint256:
    if x > 5:
        return 1
    total: uint256 = 0
    for v: uint256 in xs:
        total += v
    return total
"""
        _, _, missing = _assert_branch_invariants(
            source, lambda c: (c.foo(10, []), c.foo(1, []))
        )
        assert missing == {}

    def test_break_both_branches(self):
        source = """\
@external
def foo(xs: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for x: uint256 in xs:
        if x == 0:
            break
        total += x
    return total
"""
        _, _, missing = _assert_branch_invariants(
            source, lambda c: (c.foo([5, 0, 3]), c.foo([5, 3]))
        )
        assert missing == {}

    def test_continue_both_branches(self):
        source = """\
@external
def foo(xs: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for x: uint256 in xs:
        if x == 0:
            continue
        total += x
    return total
"""
        _, _, missing = _assert_branch_invariants(
            source, lambda c: (c.foo([0, 5]), c.foo([5, 3]))
        )
        assert missing == {}

    def test_nested_loop_order_invariant(self):
        """false→true vs true→false produce same arcs."""
        source = """\
@external
def foo(xs: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for x: uint256 in xs:
        if x > 5:
            total += x
        else:
            total += 1
    return total
"""
        # false first, then true
        _, _, missing_ft = _assert_branch_invariants(source, lambda c: c.foo([1, 10]))
        assert missing_ft == {}
        # true first, then false
        _, _, missing_tf = _assert_branch_invariants(source, lambda c: c.foo([10, 1]))
        assert missing_tf == {}
