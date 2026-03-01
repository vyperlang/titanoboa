"""Parity tests for CoverageCollector.

Verify the invariant (executed arcs ⊆ possible arcs) and correct
missing/executed arcs across high-risk branch scenarios.
"""

import contextlib
import os
import tempfile

import coverage as coverage_lib
import vyper.ast as vy_ast

import boa
from boa.environment import Env

from .conftest import _check_full_branch_coverage


def _assert_parity(source, calls_fn):
    """Assert executed ⊆ possible and return (possible, executed, missing)."""
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


class TestCollectorParity:
    def test_simple_if_else_both_branches(self):
        source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        return 0
"""
        _, _, missing = _assert_parity(source, lambda c: (c.foo(10), c.foo(1)))
        assert missing == {}

    def test_if_without_else_both_branches(self):
        source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    return 0
"""
        _, _, missing = _assert_parity(source, lambda c: (c.foo(10), c.foo(1)))
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
        _, _, missing = _assert_parity(source, lambda c: (c.foo([1, 10]), c.foo([])))
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
        _, _, missing = _assert_parity(source, lambda c: c.foo([1, 10]))
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
        _, _, missing = _assert_parity(
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
        _, _, missing = _assert_parity(
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
        _, _, missing = _assert_parity(source, lambda c: (c.foo(10, 20), c.foo(1, 1)))
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
        _, _, missing = _assert_parity(source, lambda c: (c.foo(10), c.foo(1)))
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
        possible, executed, missing = _assert_parity(source, lambda c: c.foo(1))
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
        _, _, missing = _assert_parity(
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
        _, _, missing = _assert_parity(source, lambda c: (c.foo(10, 3), c.foo(1, 3)))
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
        _, _, missing = _assert_parity(
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
        possible, executed, missing = _assert_parity(
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
        _, _, missing = _assert_parity(source, lambda c: c.foo([1]))
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
        _, _, missing = _assert_parity(source, lambda c: (c.foo(10, []), c.foo(1, [])))
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
        _, _, missing = _assert_parity(source, lambda c: (c.foo(10, []), c.foo(1, [])))
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
        _, _, missing = _assert_parity(
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
        _, _, missing = _assert_parity(source, lambda c: (c.foo([0, 5]), c.foo([5, 3])))
        assert missing == {}

    def test_nested_loop_order_parity(self):
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
        _, _, missing_ft = _assert_parity(source, lambda c: c.foo([1, 10]))
        assert missing_ft == {}
        # true first, then false
        _, _, missing_tf = _assert_parity(source, lambda c: c.foo([10, 1]))
        assert missing_tf == {}

    def test_cross_module_if_else_in_loop(self):
        """Branch in loop calling imported module — segments split A→B→A.

        A single call exercises both branches, but the raw_trace_pos
        must persist across segments so the second main segment finds
        its JUMPI at the correct position.
        """
        module_src = """\
x: uint256

@internal
def bump(v: uint256):
    self.x += v
"""
        main_src = """\
import module_lib

initializes: module_lib

@external
def foo(xs: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for x: uint256 in xs:
        if x > 5:
            module_lib.bump(x)
            total += x
        else:
            module_lib.bump(1)
            total += 1
    return total
"""
        saved_coverage = Env._coverage_enabled
        tmpdir = tempfile.mkdtemp()
        main_path = os.path.join(tmpdir, "main.vy")
        lib_path = os.path.join(tmpdir, "module_lib.vy")
        try:
            with open(main_path, "w") as f:
                f.write(main_src)
            with open(lib_path, "w") as f:
                f.write(module_src)

            cov = coverage_lib.Coverage(branch=True, config_file=False, data_file=None)
            cov.set_option("run:plugins", ["boa.coverage"])
            cov.start()
            try:
                c = boa.load(main_path)
                c.foo([10, 1])
            finally:
                cov.stop()

            analysis = cov._analyze(main_path)
            executed = dict(analysis.executed_branch_arcs())
            missing = dict(analysis.missing_branch_arcs())

            # Derive expected lines from AST rather than hardcoding
            with open(main_path) as f:
                tree = vy_ast.parse_to_ast(f.read(), source_id=0)
            func = tree.body[-1]  # FunctionDef for foo
            for_node = None
            for stmt in func.body:
                if isinstance(stmt, vy_ast.For):
                    for_node = stmt
                    break
            assert for_node is not None
            if_node = for_node.body[0]
            assert isinstance(if_node, vy_ast.If)

            if_line = if_node.lineno
            true_line = if_node.body[0].lineno
            false_line = if_node.orelse[0].lineno

            # Both branches should have been executed
            assert (
                if_line in executed
            ), f"If line {if_line} not in executed arcs: {executed}"
            executed_targets = set(executed[if_line])
            assert true_line in executed_targets, (
                f"True branch line {true_line} not in executed targets "
                f"{executed_targets} for if@{if_line}"
            )
            assert false_line in executed_targets, (
                f"False branch line {false_line} not in executed targets "
                f"{executed_targets} for if@{if_line}"
            )
            assert missing == {}, f"Unexpected missing arcs: {missing}"
        finally:
            Env._coverage_enabled = saved_coverage
            with contextlib.suppress(OSError):
                os.unlink(main_path)
            with contextlib.suppress(OSError):
                os.unlink(lib_path)
            with contextlib.suppress(OSError):
                os.rmdir(tmpdir)
