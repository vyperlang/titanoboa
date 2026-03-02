"""Core branch coverage tests.

Basic if/else, if-without-else, early return, void functions,
cross-contract, statement-only coverage, pass-only functions,
untaken branch lines, invariant checks, and tail-statement tests.

Loop-specific tests are in test_branch_loops.py.
Nested/elif tests are in test_branch_nested.py.
Multiline tests are in test_branch_multiline.py.
"""

import pytest
import vyper.ast as vy_ast
from vyper.ast.parse import parse_to_ast

import boa

from .conftest import (
    _analyze,
    _check_branch_coverage,
    _check_full_branch_coverage,
    _coverage_session,
    _coverage_session_lines,
    _coverage_session_multi,
)


@pytest.fixture(scope="module")
def external_contract():
    source_code = """
@external
@view
def foo(a: uint256) -> uint256:
    return a * a
"""
    return boa.loads(source_code, name="ExternalContract")


@pytest.fixture(scope="module")
def source_contract(external_contract):
    source_code = """
interface Foo:
    def foo(a: uint256) -> uint256: view

FOO: immutable(address)

@deploy
def __init__(_foo_address: address):
    FOO = _foo_address

@external
@view
def bar(b: uint256) -> uint256:
    c: uint256 = staticcall Foo(FOO).foo(b)
    return c
"""
    return boa.loads(source_code, external_contract.address, name="TestContract")


def test_sub_computations(source_contract):
    from boa.environment import Env

    saved = Env._coverage_enabled
    try:
        Env._coverage_enabled = True
        source_contract.bar(10)
    finally:
        Env._coverage_enabled = saved


# --- branch coverage tests ---


def test_branch_simple_if_else():
    """Both branches of a simple if/else are hit."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_if_without_else():
    """Both branches of an if without explicit else are hit."""
    source = """\
x: public(uint256)

@external
def foo(val: uint256):
    if val > 5:
        self.x = val
    self.x = 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_bare_return_in_if():
    """if with bare return (no value) — both arcs covered."""
    source = """\
x: public(uint256)

@external
def foo(val: uint256):
    if val > 5:
        return
    self.x = val
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_bare_return_in_if_partial():
    """Bare return if, only true branch hit — false arc must be missing.

    The exact missing arc must target `self.x = val` (the false/fallthrough
    branch), not the function line (the true/return branch).  This ensures
    the JUMPI direction classifier assigns the correct labels.
    """
    source = """\
x: public(uint256)

@external
def foo(val: uint256):
    if val > 5:
        return
    self.x = val
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    fn_node = ast.get_descendants(vy_ast.FunctionDef)[0]
    false_target = if_node._parent.body[-1]  # self.x = val
    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: c.foo(10)
    )
    # True arc (to fn_node.lineno for bare return) should be executed
    assert if_node.lineno in executed, f"If-line not in executed: {executed}"
    assert (
        fn_node.lineno in executed[if_node.lineno]
    ), f"Expected true arc to fn_line {fn_node.lineno} in executed, got {executed}"
    # False arc (to self.x = val) should be missing
    assert if_node.lineno in missing, f"Expected if-line in missing: {missing}"
    assert (
        false_target.lineno in missing[if_node.lineno]
    ), f"Expected false arc to {false_target.lineno} in missing, got {missing}"


def test_branch_bare_return_compound_condition():
    """Bare return with compound condition (and) — both arcs covered."""
    source = """\
y: public(uint256)

@external
def f(x: uint256):
    if (x != 2) and (x >= 25):
        return
    self.y = 1
"""
    missing = _check_branch_coverage(source, lambda c: (c.f(25), c.f(0)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_both_null_return_degenerate():
    """if/else where both branches are bare return — arcs collapse.

    Both branches compile to the same target (fn_node.lineno), so
    coverage.py cannot distinguish them.  Executing only one branch
    still reports full coverage.  This is a known limitation: the
    reporter declares two arcs with the same endpoints.
    """
    source = """\
@external
def foo(x: uint256):
    if x > 5:
        return
    else:
        return
"""
    # Only true branch hit — coverage still reports full because
    # both arcs are (if_line, fn_line).
    missing = _check_branch_coverage(source, lambda c: c.foo(10))
    assert missing == {}, (
        f"Both arcs target fn_line; partial execution should still "
        f"show no missing (degenerate case), got: {missing}"
    )


# --- branch negative controls (partial coverage) ---


def test_branch_simple_if_else_partial():
    """Only true branch hit — false arc must be missing."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        return 0
"""
    missing = _check_branch_coverage(source, lambda c: c.foo(10))
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    else_first = if_node.orelse[0]
    assert missing == {
        if_node.lineno: [else_first.lineno]
    }, f"Unexpected missing arcs: {missing}"


def test_branch_if_without_else_partial():
    """Only true branch hit — fallthrough (false) arc must be missing."""
    source = """\
@external
def foo(val: uint256) -> uint256:
    if val > 5:
        return val
    return 0
"""
    # Only call with val=10 → true branch returns, fallthrough not taken
    missing = _check_branch_coverage(source, lambda c: c.foo(10))
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    # The false arc for if-without-else: next sibling is `return 0`
    return_0 = ast.get_descendants(vy_ast.Return)[-1]
    assert (
        if_node.lineno in missing
    ), f"Expected if-line {if_node.lineno} in missing: {missing}"
    assert (
        return_0.lineno in missing[if_node.lineno]
    ), f"Expected false arc to {return_0.lineno}, got {missing}"


# --- full arc assertion (possible + executed + missing) ---


def test_full_arcs_simple_if_else():
    """Assert exact possible, executed, and missing arcs for simple if/else."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        return 0
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    true_target = if_node.body[0].lineno
    false_target = if_node.orelse[0].lineno
    expected_possible = {(if_node.lineno, true_target), (if_node.lineno, false_target)}

    # Exercise both branches
    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: (c.foo(10), c.foo(1))
    )
    assert possible == expected_possible, f"Possible: {possible}"
    assert if_node.lineno in executed, f"If-line not in executed: {executed}"
    assert set(executed[if_node.lineno]) == {
        true_target,
        false_target,
    }, f"Executed: {executed}"
    assert missing == {}, f"Missing: {missing}"


# --- control flow exits in branches ---


def test_branch_if_with_early_return():
    """if body returns early, else falls through; both paths hit → no missing."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    result: uint256 = 0
    if x > 5:
        return 1
    else:
        result = x + 1
    return result
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


# --- multi-contract / cross-contract coverage ---


def test_branch_cross_contract():
    """Arcs from a called contract are attributed to the callee's file."""
    callee_source = """\
@external
def bar(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        return 0
"""
    caller_source = """\
interface Callee:
    def bar(x: uint256) -> uint256: nonpayable

CALLEE: immutable(address)

@deploy
def __init__(callee_addr: address):
    CALLEE = callee_addr

@external
def call_bar(x: uint256) -> uint256:
    return extcall Callee(CALLEE).bar(x)
"""

    def setup(paths):
        callee = boa.load(paths["callee"])
        caller = boa.load(paths["caller"], callee.address)
        caller.call_bar(10)
        caller.call_bar(1)

    with _coverage_session_multi(
        {"callee": callee_source, "caller": caller_source}, setup
    ) as (cov, paths):
        analysis = _analyze(cov, paths["callee"])
        missing = dict(analysis.missing_branch_arcs())
        assert missing == {}, f"Callee missing branch arcs: {missing}"


# --- internal function called multiple times in one transaction ---


def test_branch_internal_call_both_directions():
    """Internal function called twice with different inputs in one tx — both arcs covered."""
    source = """\
@internal
def _check(x: uint256) -> uint256:
    if x > 5:
        return 1
    return 0

@external
def foo(a: uint256, b: uint256) -> uint256:
    return self._check(a) + self._check(b)
"""
    # a=10 hits true, b=1 hits false — single call covers both
    missing = _check_branch_coverage(source, lambda c: c.foo(10, 1))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_internal_call_same_direction():
    """Internal function called twice, same direction — partial coverage."""
    source = """\
@internal
def _check(x: uint256) -> uint256:
    if x > 5:
        return 1
    return 0

@external
def foo(a: uint256, b: uint256) -> uint256:
    return self._check(a) + self._check(b)
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    # Both calls take true branch — false arc should be missing
    missing = _check_branch_coverage(source, lambda c: c.foo(10, 20))
    assert if_node.lineno in missing, f"Expected if-line in missing: {missing}"


def test_branch_internal_call_three_times():
    """Internal function called three times: true, false, true."""
    source = """\
@internal
def _check(x: uint256) -> uint256:
    if x > 5:
        return 1
    return 0

@external
def foo(a: uint256, b: uint256, c: uint256) -> uint256:
    return self._check(a) + self._check(b) + self._check(c)
"""
    missing = _check_branch_coverage(source, lambda c: c.foo(10, 1, 20))
    assert missing == {}, f"Missing branch arcs: {missing}"


# --- internal call in If.test (condition helpers) ---


def test_branch_helper_condition_break_false_only():
    """for + break + helper condition, false-only must not report full coverage."""
    source = """\
@internal
def gt5(x: uint256) -> bool:
    return x > 5

@external
def f(xs: DynArray[uint256, 10]) -> uint256:
    s: uint256 = 0
    for x: uint256 in xs:
        if self.gt5(x):
            break
        s += x
    return s
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    missing = _check_branch_coverage(source, lambda c: c.f([1]))
    assert (
        if_node.lineno in missing
    ), f"Expected if-line {if_node.lineno} in missing (false only), got: {missing}"


def test_branch_helper_compound_continue_true_only():
    """for + continue + helper+and, true-only must not report full coverage."""
    source = """\
@internal
def gt5(x: uint256) -> bool:
    return x > 5
@internal
def lt20(x: uint256) -> bool:
    return x < 20

@external
def f(xs: DynArray[uint256, 10]) -> uint256:
    s: uint256 = 0
    for x: uint256 in xs:
        if (self.gt5(x)) and (self.lt20(x)):
            continue
        s += x
    return s
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    missing = _check_branch_coverage(source, lambda c: c.f([10]))
    assert (
        if_node.lineno in missing
    ), f"Expected if-line {if_node.lineno} in missing (true only), got: {missing}"


def test_branch_helper_compound_if_else_true_only():
    """top-level if/else + helper+and, true-only must not report full coverage."""
    source = """\
@internal
def gt5(x: uint256) -> bool:
    return x > 5
@internal
def lt20(x: uint256) -> bool:
    return x < 20

@external
def f(x: uint256) -> uint256:
    if (self.gt5(x)) and (self.lt20(x)):
        return 1
    else:
        return 0
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    missing = _check_branch_coverage(source, lambda c: c.f(10))
    assert (
        if_node.lineno in missing
    ), f"Expected if-line {if_node.lineno} in missing (true only), got: {missing}"


def test_branch_helper_triple_or_false_only():
    """top-level if/else + helper short-circuit or, false-only must not report full."""
    source = """\
@internal
def gt5(x: uint256) -> bool:
    return x > 5
@internal
def lt20(x: uint256) -> bool:
    return x < 20
@internal
def eq100(x: uint256) -> bool:
    return x == 100

@external
def f(x: uint256) -> uint256:
    if ((self.gt5(x)) and (self.lt20(x))) or (self.eq100(x)):
        return 1
    else:
        return 0
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    missing = _check_branch_coverage(source, lambda c: c.f(25))
    assert (
        if_node.lineno in missing
    ), f"Expected if-line {if_node.lineno} in missing (false only), got: {missing}"


def test_branch_helper_no_else_tail_false_only():
    """if without else + tail + helper condition, false-only must not report full."""
    source = """\
@internal
def gt5(x: uint256) -> bool:
    return x > 5
@internal
def lt20(x: uint256) -> bool:
    return x < 20

@external
def f(x: uint256) -> uint256:
    y: uint256 = 0
    if (self.gt5(x)) and (self.lt20(x)):
        y = 1
    return y
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    missing = _check_branch_coverage(source, lambda c: c.f(25))
    assert (
        if_node.lineno in missing
    ), f"Expected if-line {if_node.lineno} in missing (false only), got: {missing}"


def test_branch_helper_bare_return_false_only():
    """bare-return body + helper condition, false-only must not report full."""
    source = """\
@internal
def gt5(x: uint256) -> bool:
    return x > 5

y: uint256
@external
def f(x: uint256):
    if self.gt5(x):
        return
    self.y = 1
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    missing = _check_branch_coverage(source, lambda c: c.f(1))
    assert (
        if_node.lineno in missing
    ), f"Expected if-line {if_node.lineno} in missing (false only), got: {missing}"


def test_branch_helper_condition_both_branches():
    """Helper condition with both branches hit — no missing arcs."""
    source = """\
@internal
def gt5(x: uint256) -> bool:
    return x > 5

@external
def f(x: uint256) -> uint256:
    if self.gt5(x):
        return 1
    else:
        return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.f(10), c.f(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


# --- if-without-else at function end ---


def test_branch_if_without_else_at_function_end():
    """if-without-else with trailing return — both arcs covered.

    The false branch falls through to `return 0` (next sibling).
    """
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_if_without_else_at_function_end_partial():
    """Only true branch hit — false arc (to next sibling) must be missing."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    return 0
"""
    missing = _check_branch_coverage(source, lambda c: c.foo(10))
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    # The false arc should target `return 0` (the next sibling)
    return_0 = ast.get_descendants(vy_ast.Return)[-1]
    assert (
        if_node.lineno in missing
    ), f"Expected if-line {if_node.lineno} in missing: {missing}"
    assert (
        return_0.lineno in missing[if_node.lineno]
    ), f"Expected false arc to {return_0.lineno}, got {missing}"


def test_branch_void_function_if_last_statement():
    """Void function where if is the last statement — false arc is implicit return.

    Regression test for _false_arc using parent.body instead of
    get_children() which would pick up decorator nodes.
    """
    source = """\
x: public(uint256)

@external
def foo(val: uint256):
    if val > 5:
        self.x = val
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_void_function_if_last_statement_partial():
    """Only true branch hit in void function — false arc (implicit return) missing."""
    source = """\
x: public(uint256)

@external
def foo(val: uint256):
    if val > 5:
        self.x = val
"""
    missing = _check_branch_coverage(source, lambda c: c.foo(10))
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    fn_node = ast.get_descendants(vy_ast.FunctionDef)[0]
    # False arc targets fn_node.lineno (implicit return)
    assert (
        if_node.lineno in missing
    ), f"Expected if-line {if_node.lineno} in missing: {missing}"
    assert (
        fn_node.lineno in missing[if_node.lineno]
    ), f"Expected false arc to fn_line {fn_node.lineno}, got {missing}"


def test_untaken_branch_lines_are_missing():
    """Entering a function must not mark untaken branch body lines as covered."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        return 0
"""
    with _coverage_session(source, lambda c: c.foo(10)) as analysis:
        ast = parse_to_ast(source)
        if_node = ast.get_descendants(vy_ast.If)[0]
        else_line = if_node.orelse[0].lineno
        # Only true branch hit — else body must be in missing
        assert else_line in analysis.missing, (
            f"Untaken else-body line {else_line} should be missing. "
            f"Executed: {sorted(analysis.executed)}, Missing: {sorted(analysis.missing)}"
        )


def test_pass_only_function_lines():
    """A pass-only function: `pass` is coverable but never hit at runtime.

    Bytecode for `pass` maps to the FunctionDef node, which _collapse_cov_node
    filters out. So even after calling foo(), the pass line is never traced.
    """
    source = """\
@external
def foo():
    pass

@external
def bar(x: uint256) -> uint256:
    return x
"""
    with _coverage_session(source, lambda c: (c.foo(), c.bar(42))) as analysis:
        ast = parse_to_ast(source)
        fn_bar = next(
            f for f in ast.get_descendants(vy_ast.FunctionDef) if f.name == "bar"
        )
        bar_return_line = fn_bar.body[0].lineno
        # bar's return line should be executed
        assert bar_return_line in analysis.executed, (
            f"bar's return line {bar_return_line} should be executed. "
            f"Executed: {sorted(analysis.executed)}"
        )

        fn_foo = next(
            f for f in ast.get_descendants(vy_ast.FunctionDef) if f.name == "foo"
        )
        pass_line = fn_foo.body[0].lineno
        # pass compiles to FunctionDef bytecode which is filtered — it should be missing
        assert pass_line in analysis.missing, (
            f"pass line {pass_line} should be in missing (FunctionDef filtered). "
            f"Executed: {sorted(analysis.executed)}, Missing: {sorted(analysis.missing)}"
        )


# --- if without else + tail statement (post-body re-evaluation) ---


def test_branch_if_no_else_with_tail_true_only():
    """if without else + tail statement, true-only: false arc must be missing."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    y: uint256 = 0
    if x > 5:
        y += 1
    y += 2
    return y
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]

    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: c.foo(10)
    )
    # True arc should be executed, false arc should be missing
    assert if_node.lineno in executed, f"If-line not in executed: {executed}"
    assert set(executed[if_node.lineno]) == {
        if_node.body[0].lineno
    }, f"Only true arc should be executed: {executed}"
    assert if_node.lineno in missing, f"If-line not in missing: {missing}"


def test_branch_if_no_else_with_tail_both():
    """Both branches hit — no missing arcs."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    y: uint256 = 0
    if x > 5:
        y += 1
    y += 2
    return y
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


# --- invariant and decision engine tests ---


def test_invariant_executed_subset_of_possible():
    """For every scenario, executed branch arcs must be a subset of possible arcs."""
    scenarios = [
        # (source, calls_fn) covering various shapes
        (
            """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        return 0
""",
            lambda c: (c.foo(10), c.foo(1)),
        ),
        (
            """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    return 0
""",
            lambda c: (c.foo(10), c.foo(1)),
        ),
        (
            """\
@external
def foo(data: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for val: uint256 in data:
        if val > 5:
            total += val
    return total
""",
            lambda c: c.foo([1, 10]),
        ),
        (
            """\
@external
def foo(data: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for val: uint256 in data:
        if val > 5:
            total += val
        else:
            total += 1
    return total
""",
            lambda c: c.foo([10, 1]),
        ),
        (
            """\
@external
def foo(x: uint256) -> uint256:
    if x > 20:
        return 3
    elif x > 10:
        return 2
    return 0
""",
            lambda c: (c.foo(25), c.foo(15), c.foo(5)),
        ),
        (
            """\
@external
def foo(x: uint256) -> uint256:
    if x > 10:
        if x > 20:
            return 3
    return 0
""",
            lambda c: (c.foo(25), c.foo(15), c.foo(5)),
        ),
        (
            """\
@external
def foo(x: uint256) -> uint256:
    y: uint256 = 0
    if x > 5:
        y += 1
    y += 2
    return y
""",
            lambda c: (c.foo(10), c.foo(1)),
        ),
        (
            """\
@external
def foo(data: DynArray[uint256, 10]) -> uint256:
    total: uint256 = 0
    for val: uint256 in data:
        if val > 100:
            total += val
        total += 1
    return total
""",
            lambda c: c.foo([1, 2, 3]),
        ),
        # If branch target is a For (zero-iteration edge case)
        (
            """\
@external
def foo(flag: bool, data: DynArray[uint256, 10]) -> uint256:
    s: uint256 = 0
    if flag:
        for v: uint256 in data:
            s += v
    else:
        s += 1
    return s
""",
            lambda c: (c.foo(True, []), c.foo(False, [])),
        ),
        (
            """\
@external
def foo(flag: bool, data: DynArray[uint256, 10]) -> uint256:
    s: uint256 = 0
    if flag:
        s += 1
    else:
        for v: uint256 in data:
            s += v
    return s
""",
            lambda c: (c.foo(True, []), c.foo(False, [])),
        ),
    ]
    for source, calls_fn in scenarios:
        possible, executed, missing = _check_full_branch_coverage(source, calls_fn)
        for line, targets in executed.items():
            arc_set = {(line, t) for t in targets}
            assert (
                arc_set <= possible
            ), f"Executed arcs {arc_set} not subset of possible {possible}"


# --- no-op body (pass / assert True) ---


def test_branch_if_pass_body_both():
    """if with pass body — both branches hit (degenerate: arcs collapse)."""
    source = """\
@external
def f(x: uint256) -> uint256:
    y: uint256 = 0
    if x > 5:
        pass
    y += 1
    return y
"""
    missing = _check_branch_coverage(source, lambda c: (c.f(10), c.f(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_if_assert_true_body_both():
    """if with assert True body (constant-folded to noop) — both branches hit."""
    source = """\
@external
def f(x: uint256) -> uint256:
    y: uint256 = 0
    if x > 5:
        assert True
    y += 1
    return y
"""
    missing = _check_branch_coverage(source, lambda c: (c.f(10), c.f(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_if_pass_body_degenerate():
    """if with pass body — arcs collapse (both point to same line).

    Like the double-null-return degenerate case: the pass body is a
    no-op so both branches fall through to the same statement.
    Executing only one branch still reports full coverage.
    """
    source = """\
@external
def f(x: uint256) -> uint256:
    y: uint256 = 0
    if x > 5:
        pass
    y += 1
    return y
"""
    missing = _check_branch_coverage(source, lambda c: c.f(10))
    assert missing == {}, (
        "Both arcs target the same fallthrough line; partial execution "
        f"should still show no missing (degenerate case), got: {missing}"
    )


def test_branch_else_pass_both():
    """if/else where else is pass — both branches hit."""
    source = """\
@external
def f(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        pass
    return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.f(10), c.f(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_else_assert_true_both():
    """if/else where else is assert True — both branches hit."""
    source = """\
@external
def f(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        assert True
    return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.f(10), c.f(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_else_pass_partial_true_only():
    """if/else where else is pass — only true hit, false arc missing."""
    source = """\
@external
def f(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        pass
    return 0
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    missing = _check_branch_coverage(source, lambda c: c.f(10))
    assert if_node.lineno in missing, f"Expected if-line in missing: {missing}"


def test_branch_else_pass_partial_false_only():
    """if/else where else is pass — only false hit, true arc missing."""
    source = """\
@external
def f(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        pass
    return 0
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    missing = _check_branch_coverage(source, lambda c: c.f(1))
    assert if_node.lineno in missing, f"Expected if-line in missing: {missing}"


def test_branch_internal_else_pass_both():
    """Internal function with else pass — both branches hit."""
    source = """\
@internal
def g(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        pass
    return 0

@external
def f(x: uint256) -> uint256:
    return self.g(x)
"""
    missing = _check_branch_coverage(source, lambda c: (c.f(10), c.f(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_if_assert_const_expr_body_both():
    """if with assert <const-expr> body (constant-folded to noop) — both branches hit."""
    source = """\
@external
def f(x: uint256) -> uint256:
    y: uint256 = 0
    if x > 5:
        assert 1 == 1
    y += 1
    return y
"""
    missing = _check_branch_coverage(source, lambda c: (c.f(10), c.f(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


SOURCE_ELSE_PASS_COMPOUND_AND = """\
@external
def f(x: uint256) -> uint256:
    if (x > 5) and (x < 20):
        return 1
    else:
        pass
    return 0
"""

SOURCE_ELSE_PASS_COMPLEX_OR_AND = """\
@external
def f(x: uint256) -> uint256:
    if ((x == 2) and (x > 5)) or (x == 3):
        return 1
    else:
        pass
    return 0
"""


def test_branch_else_pass_compound_condition_both():
    """else pass + compound condition — both branches hit."""
    missing = _check_branch_coverage(
        SOURCE_ELSE_PASS_COMPOUND_AND, lambda c: (c.f(10), c.f(30))
    )
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_else_pass_compound_condition_partial():
    """else pass + compound condition — false-only, true arc must be missing."""
    ast = parse_to_ast(SOURCE_ELSE_PASS_COMPOUND_AND)
    if_node = ast.get_descendants(vy_ast.If)[0]
    # f(30): x>5 True, x<20 False => false path
    missing = _check_branch_coverage(SOURCE_ELSE_PASS_COMPOUND_AND, lambda c: c.f(30))
    assert if_node.lineno in missing, f"Expected if-line in missing: {missing}"


def test_branch_else_pass_complex_compound_or_and():
    """else pass + complex compound condition ``(A and B) or C`` — both arcs covered."""
    missing = _check_branch_coverage(
        SOURCE_ELSE_PASS_COMPLEX_OR_AND, lambda c: (c.f(3), c.f(1))
    )
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_else_pass_complex_compound_or_and_partial():
    """else pass + complex compound ``(A and B) or C`` — true-only partial."""
    possible, executed, missing = _check_full_branch_coverage(
        SOURCE_ELSE_PASS_COMPLEX_OR_AND, lambda c: c.f(3)
    )
    # f(3) hits the true branch; false should be missing
    ast = parse_to_ast(SOURCE_ELSE_PASS_COMPLEX_OR_AND)
    if_node = ast.get_descendants(vy_ast.If)[0]
    assert if_node.lineno in missing, f"Expected if-line in missing: {missing}"
    assert if_node.lineno in executed, f"Expected true arc executed: {executed}"
    # True arc (to return 1) should be in executed targets
    true_target = if_node.body[0].lineno
    assert (
        true_target in executed[if_node.lineno]
    ), f"Expected true arc to L{true_target}: {executed}"


# --- noop true body (pass/assert True in if body, non-noop else) ---


def test_branch_noop_true_body_full():
    """Noop true body (pass) with non-noop else — all branches covered."""
    source = """\
@external
def f(x: uint256) -> uint256:
    y: uint256 = 0
    if x > 5:
        pass
    else:
        y += 1
        return y
    return 1
"""
    missing = _check_branch_coverage(source, lambda c: (c.f(10), c.f(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_noop_true_body_true_only():
    """Noop true body — only true branch hit, false should be missing."""
    source = """\
@external
def f(x: uint256) -> uint256:
    y: uint256 = 0
    if x > 5:
        pass
    else:
        y += 1
        return y
    return 1
"""
    possible, executed, missing = _check_full_branch_coverage(source, lambda c: c.f(10))
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    # True arc should be executed
    assert if_node.lineno in executed, f"Expected true arc: {executed}"
    # False arc (else body) should be missing
    assert if_node.lineno in missing, f"Expected missing false arc: {missing}"
    false_target = if_node.orelse[0].lineno
    assert (
        false_target in missing[if_node.lineno]
    ), f"Expected false arc to L{false_target}: {missing}"


def test_branch_noop_true_body_false_only():
    """Noop true body — only false branch hit, true should be missing."""
    source = """\
@external
def f(x: uint256) -> uint256:
    y: uint256 = 0
    if x > 5:
        pass
    else:
        y += 1
        return y
    return 1
"""
    possible, executed, missing = _check_full_branch_coverage(source, lambda c: c.f(1))
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    # False arc (else body) should be executed
    false_target = if_node.orelse[0].lineno
    assert if_node.lineno in executed, f"Expected false arc: {executed}"
    assert (
        false_target in executed[if_node.lineno]
    ), f"Expected false arc to L{false_target}: {executed}"
    # True arc should be missing
    assert if_node.lineno in missing, f"Expected missing true arc: {missing}"


def test_branch_noop_true_body_assert_true():
    """assert True in if body (constant-folded away) with non-noop else."""
    source = """\
@external
def f(x: uint256) -> uint256:
    y: uint256 = 0
    if x > 5:
        assert True
    else:
        y += 1
        return y
    return 1
"""
    missing = _check_branch_coverage(source, lambda c: (c.f(10), c.f(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_noop_true_body_elif_full():
    """Noop true body (pass) with elif — all branches covered."""
    source = """\
@external
def f(x: uint256) -> uint256:
    if x > 20:
        pass
    elif x > 10:
        return 2
    return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.f(25), c.f(15), c.f(5)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_noop_true_body_elif_outer_true_only():
    """Noop true body + elif — outer true only, no phantom dual arc."""
    source = """\
@external
def f(x: uint256) -> uint256:
    if x > 20:
        pass
    elif x > 10:
        return 2
    return 0
"""
    possible, executed, missing = _check_full_branch_coverage(source, lambda c: c.f(25))
    ast = parse_to_ast(source)
    outer_if = ast.get_descendants(vy_ast.If)[0]
    # Only the outer true arc should be executed — no phantom dual arc
    outer_targets = set(executed.get(outer_if.lineno, []))
    # true_line for noop body = fallthrough target (return 0 at line 7)
    assert outer_targets == {
        7
    }, f"Expected only outer true arc {{7}}, got {outer_targets}"


def test_branch_noop_true_body_elif_inner_true():
    """Noop true body + elif — elif true arc correctly credited."""
    source = """\
@external
def f(x: uint256) -> uint256:
    if x > 20:
        pass
    elif x > 10:
        return 2
    return 0
"""
    possible, executed, missing = _check_full_branch_coverage(source, lambda c: c.f(15))
    ast = parse_to_ast(source)
    inner_if = ast.get_descendants(vy_ast.If)[1]  # elif
    inner_targets = set(executed.get(inner_if.lineno, []))
    # elif true arc should target `return 2` at line 6
    assert (
        inner_if.body[0].lineno in inner_targets
    ), f"Expected elif true arc to L{inner_if.body[0].lineno}: {inner_targets}"


def test_branch_noop_true_body_fallthrough_else_false_only():
    """Noop true body with fallthrough (non-return) else — false only, true must be missing."""
    source = """\
@external
def f(x: uint256) -> uint256:
    y: uint256 = 0
    if x > 5:
        pass
    else:
        y += 1
    y += 2
    return y
"""
    possible, executed, missing = _check_full_branch_coverage(source, lambda c: c.f(1))
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    # Only false arc should be executed
    false_target = if_node.orelse[0].lineno
    assert if_node.lineno in executed, f"Expected false arc: {executed}"
    assert (
        false_target in executed[if_node.lineno]
    ), f"Expected false arc to L{false_target}: {executed}"
    # True arc should be missing
    assert if_node.lineno in missing, f"Expected missing true arc: {missing}"


def test_branch_noop_true_body_fallthrough_else_full():
    """Noop true body with fallthrough else — all branches covered."""
    source = """\
@external
def f(x: uint256) -> uint256:
    y: uint256 = 0
    if x > 5:
        pass
    else:
        y += 1
    y += 2
    return y
"""
    missing = _check_branch_coverage(source, lambda c: (c.f(10), c.f(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_noop_else_in_loop_order_independent():
    """Noop else in loop — coverage must not depend on call order."""
    source = """\
@external
def f(xs: DynArray[uint256, 10]) -> uint256:
    s: uint256 = 0
    for x: uint256 in xs:
        if x > 5:
            s += 1
        else:
            pass
        s += x
    return s
"""
    # Both orderings must produce the same result
    missing_tf = _check_branch_coverage(source, lambda c: c.f([10, 1]))
    assert missing_tf == {}, f"[10,1] missing: {missing_tf}"
    missing_ft = _check_branch_coverage(source, lambda c: c.f([1, 10]))
    assert missing_ft == {}, f"[1,10] missing: {missing_ft}"


def test_branch_noop_body_in_loop_false_only():
    """Noop true body in loop — false-only should not credit true arc."""
    source = """\
@external
def f(xs: DynArray[uint256, 10]) -> uint256:
    s: uint256 = 0
    for x: uint256 in xs:
        if x > 5:
            pass
        else:
            s += 1
        s += x
    return s
"""
    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: c.f([1])
    )
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    # Only false arc should be executed
    assert if_node.lineno in executed, f"Expected false arc: {executed}"
    assert if_node.lineno in missing, f"Expected missing true arc: {missing}"


def test_branch_noop_body_in_loop_full():
    """Noop true body in loop — both branches covered."""
    source = """\
@external
def f(xs: DynArray[uint256, 10]) -> uint256:
    s: uint256 = 0
    for x: uint256 in xs:
        if x > 5:
            pass
        else:
            s += 1
        s += x
    return s
"""
    missing = _check_branch_coverage(source, lambda c: c.f([10, 1]))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_compound_and_skip_gate_false_only():
    """Compound `and` condition, false-only: only the false arc should be reported."""
    source = """\
@external
def f(x: uint256, y: uint256) -> uint256:
    if (x > 5) and (y < 20):
        return 1
    return 0
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    true_target = if_node.body[0].lineno

    # x=10, y=30 → x>5 True, y<20 False → false branch
    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: c.f(10, 30)
    )
    assert (
        if_node.lineno in missing
    ), f"Expected if-line {if_node.lineno} in missing (false only): {missing}"
    # The true arc must NOT be in executed arcs
    if if_node.lineno in executed:
        assert true_target not in executed[if_node.lineno], (
            f"True arc to L{true_target} should NOT be executed "
            f"(only false branch taken): {executed}"
        )


def test_branch_internal_call_body_classify_path_fn_def():
    """If body starts with an internal call — both arcs covered and partial correct."""
    source = """\
@internal
def _helper() -> uint256:
    return 42

@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return self._helper()
    return 0
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    true_target = if_node.body[0].lineno

    # x=10 → true branch, x=1 → false branch; both should be covered
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"

    # Also verify partial: true-only should show false arc missing
    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: c.foo(10)
    )
    assert if_node.lineno in executed, f"If-line not in executed: {executed}"
    assert (
        true_target in executed[if_node.lineno]
    ), f"True arc to L{true_target} not executed: {executed}"
    assert (
        if_node.lineno in missing
    ), f"Expected false arc missing for true-only call: {missing}"


def test_branch_internal_call_condition_classify_path_cond():
    """Internal call in condition — true-only must show correct arcs."""
    source = """\
@internal
def _gt5(x: uint256) -> bool:
    return x > 5

@external
def foo(x: uint256) -> uint256:
    if self._gt5(x):
        return 1
    return 0
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    true_target = if_node.body[0].lineno

    # true-only call: must show false arc missing, true arc executed
    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: c.foo(10)
    )
    assert if_node.lineno in executed, f"If-line not in executed: {executed}"
    assert (
        true_target in executed[if_node.lineno]
    ), f"True arc to L{true_target} not executed for true-only call: {executed}"
    assert (
        if_node.lineno in missing
    ), f"Expected false arc missing for true-only call: {missing}"


def test_branch_unknown_default_direction():
    """Both branches are bare returns (degenerate) — arcs still recorded."""
    source = """\
@external
def foo(x: uint256):
    if x > 5:
        return
    else:
        return
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    fn_node = ast.get_descendants(vy_ast.FunctionDef)[0]

    # Both arcs point to fn_line — this is the degenerate case.
    # Call with x=10 (true branch). The default fallback direction
    # determines if the recorded arc is from the "true" or "false"
    # classification.  Ensure at least one arc is executed.
    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: c.foo(10)
    )
    # Both arcs are (if_line, fn_line), so both are always "covered"
    # regardless of direction, but the arc must actually be executed
    assert (
        if_node.lineno in executed
    ), f"If-line {if_node.lineno} not in executed: {executed}"
    assert (
        fn_node.lineno in executed[if_node.lineno]
    ), f"Expected arc to fn_line {fn_node.lineno} executed: {executed}"

    # Also verify with only the false branch (x=1)
    possible2, executed2, missing2 = _check_full_branch_coverage(
        source, lambda c: c.foo(1)
    )
    assert (
        if_node.lineno in executed2
    ), f"If-line {if_node.lineno} not in executed (false-only): {executed2}"


def test_branch_compound_and_true_only_no_spurious_false():
    """Compound ``and`` condition — true-only must NOT report false arc."""
    source = """\
@external
def foo(x: uint256, y: uint256) -> uint256:
    if x > 5 and y > 10:
        return 1
    return 0
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    true_target = if_node.body[0]
    false_target = if_node._parent.body[-1]  # return 0

    # True-only: only the true arc should be executed
    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: c.foo(10, 20)
    )
    assert if_node.lineno in executed, f"If-line not in executed: {executed}"
    assert (
        true_target.lineno in executed[if_node.lineno]
    ), f"True arc to L{true_target.lineno} not in executed: {executed}"
    # The false arc must NOT be in executed (only true-only was called)
    assert false_target.lineno not in executed.get(
        if_node.lineno, []
    ), f"Spurious false arc L{false_target.lineno} in executed: {executed}"
    # The false arc must be in missing
    assert (
        if_node.lineno in missing
    ), f"Expected false arc missing for true-only: {missing}"
    assert (
        false_target.lineno in missing[if_node.lineno]
    ), f"False arc to L{false_target.lineno} not in missing: {missing}"


def test_branch_compound_or_false_only_no_spurious_true():
    """Compound ``or`` condition — false-only must NOT report true arc."""
    source = """\
@external
def foo(x: uint256, y: uint256) -> uint256:
    if x > 5 or y > 10:
        return 1
    return 0
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    true_target = if_node.body[0]
    false_target = if_node._parent.body[-1]

    # False-only: only the false arc should be executed
    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: c.foo(1, 1)
    )
    assert if_node.lineno in executed, f"If-line not in executed: {executed}"
    assert (
        false_target.lineno in executed[if_node.lineno]
    ), f"False arc to L{false_target.lineno} not in executed: {executed}"
    # The true arc must NOT be in executed
    assert true_target.lineno not in executed.get(
        if_node.lineno, []
    ), f"Spurious true arc L{true_target.lineno} in executed: {executed}"


def test_branch_if_return_with_storage_write_partial():
    """If with return + storage write in false body — partial coverage correct."""
    source = """\
x: public(uint256)

@external
def foo(val: uint256) -> uint256:
    if val > 5:
        return val
    self.x = val
    return 0
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    true_target = if_node.body[0]  # Return
    false_target_node = if_node._parent.body[-2]  # self.x = val (Assign)

    # True-only: must record true arc, not false arc
    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: c.foo(10)
    )
    assert if_node.lineno in executed, f"If-line not in executed: {executed}"
    assert (
        true_target.lineno in executed[if_node.lineno]
    ), f"True arc to L{true_target.lineno} not executed: {executed}"
    assert (
        if_node.lineno in missing
    ), f"Expected false arc missing for true-only: {missing}"
    assert (
        false_target_node.lineno in missing[if_node.lineno]
    ), f"False arc to L{false_target_node.lineno} not in missing: {missing}"

    # False-only: must record false arc, not true arc
    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: c.foo(1)
    )
    assert if_node.lineno in executed, f"If-line not in executed: {executed}"
    assert (
        false_target_node.lineno in executed[if_node.lineno]
    ), f"False arc to L{false_target_node.lineno} not executed: {executed}"
    assert (
        if_node.lineno in missing
    ), f"Expected true arc missing for false-only: {missing}"


def test_branch_if_return_with_storage_write_both():
    """If with return in true body + storage write — both branches hit."""
    source = """\
x: public(uint256)

@external
def foo(val: uint256) -> uint256:
    if val > 5:
        return val
    self.x = val
    return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_if_return_with_multiple_storage_writes_partial():
    """If with return + multiple storage writes in false path.

    Similar to above but with more statements between if and return 0,
    producing a wider bytecode gap that stresses _classify_path.
    """
    source = """\
x: public(uint256)
y: public(uint256)

@external
def foo(val: uint256) -> uint256:
    if val > 5:
        return val
    self.x = val
    self.y = val + 1
    return 0
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    true_target = if_node.body[0]

    # True-only
    possible, executed, missing = _check_full_branch_coverage(
        source, lambda c: c.foo(10)
    )
    assert if_node.lineno in executed, f"If-line not in executed: {executed}"
    assert (
        true_target.lineno in executed[if_node.lineno]
    ), f"True arc to L{true_target.lineno} not executed: {executed}"
    assert (
        if_node.lineno in missing
    ), f"Expected false arc missing for true-only: {missing}"

    # Both branches
    missing = _check_branch_coverage(source, lambda c: (c.foo(10), c.foo(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


# --- unit tests for internal helpers (mutation regression) ---


def test_classify_path_skips_fn_def_node():
    """_classify_path must skip FunctionDef nodes and continue scanning.

    Mutation regression (classify_path_fn_def): if _classify_path returns
    "exit" when it encounters a FunctionDef node (collapsed == None) instead
    of continuing past it, _resolve_jumpi_direction may infer the wrong
    branch direction when FunctionDef bytecode sits between the JUMPI
    destination and the actual branch body in the AST map.

    Uses _resolve_jumpi_direction directly with a synthetic AST map where
    a FunctionDef node precedes the true_stmt descendant at the taken
    destination.  With the mutation (return "exit"), taken_class becomes
    "exit" and the direction is wrong.  With the correct code (continue),
    the scan proceeds past the FunctionDef and finds the true body node.
    """
    from boa.coverage import _resolve_jumpi_direction

    source = """\
@internal
def _helper() -> uint256:
    return 42

@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return self._helper()
    return 0
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    fn_node = ast.get_descendants(vy_ast.FunctionDef, {"name": "foo"})[0]
    helper_fn = ast.get_descendants(vy_ast.FunctionDef, {"name": "_helper"})[0]
    true_stmt = if_node.body[0]  # Return(value=self._helper())
    false_stmt_node = fn_node.body[-1]  # return 0

    # Build a synthetic AST map where:
    #   PC 100 (taken_dest) → FunctionDef node (should be skipped)
    #   PC 102 → a node that is a descendant of true_stmt
    #   PC 200 (fallthrough) → false_stmt descendant
    # With the mutation, _classify_path(100) returns "exit" at PC 100.
    # With correct code, it skips FunctionDef, finds true_stmt at PC 102.
    true_body_node = true_stmt.value  # the self._helper() call expression
    ast_map = {
        100: helper_fn,  # FunctionDef — should be skipped
        102: true_body_node,  # descendant of true_stmt
        200: false_stmt_node,  # descendant of false_stmt
    }

    result = _resolve_jumpi_direction(
        taken_dest=100,
        fallthrough=200,
        ast_map=ast_map,
        true_stmt=true_stmt,
        false_stmt=false_stmt_node,
        if_node=if_node,
    )
    # taken path starts at FunctionDef then reaches true_stmt → taken IS true
    assert (
        result is True
    ), f"Expected taken=true (FunctionDef skipped, true_stmt found), got {result}"


def test_unknown_default_direction_distinct_arcs():
    """Default direction must be True when both paths are unclassifiable.

    Mutation regression (unknown_default): when _resolve_jumpi_direction
    reaches the fallback ``return True`` (both _classify_path calls return
    None), flipping to ``return False`` would swap the arc labels.

    Uses _resolve_jumpi_direction directly with a synthetic AST map where
    neither path contains classifiable nodes (only if_node-mapped and
    unmapped PCs), but the true and false arcs point to different lines.
    The fallback direction determines which arc is recorded, so flipping
    it would record the wrong arc.
    """
    from boa.coverage import _resolve_jumpi_direction

    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    return 0
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    true_stmt = if_node.body[0]
    fn_node = ast.get_descendants(vy_ast.FunctionDef)[0]
    false_stmt_node = fn_node.body[-1]

    # Build a synthetic AST map where both paths only contain if_node
    # itself (which _classify_path skips) and unmapped PCs.
    # This forces both _classify_path calls to return None, reaching
    # the default ``return True`` fallback.
    ast_map = {
        100: if_node,  # taken_dest → skipped (is if_node)
        200: if_node,  # fallthrough → skipped (is if_node)
    }

    result = _resolve_jumpi_direction(
        taken_dest=100,
        fallthrough=200,
        ast_map=ast_map,
        true_stmt=true_stmt,
        false_stmt=false_stmt_node,
        if_node=if_node,
    )
    # Both paths unclassifiable → default is True (taken = true branch)
    assert result is True, f"Expected default direction True (taken=true), got {result}"


def test_path_classify_limit_upper_bound():
    """_PATH_CLASSIFY_LIMIT must not scan too far beyond the branch.

    Mutation regression (path_classify_limit upper): increasing
    _PATH_CLASSIFY_LIMIT from 30 to 60 would cause _classify_path to scan
    past the branch body into unrelated code, potentially finding a node
    from a different statement that overrides an earlier correct classification.

    Uses _resolve_jumpi_direction with a synthetic AST map where:
    - false_stmt sits at taken_dest + 5 (within any limit) → "false"
    - true_stmt sits at taken_dest + 35 (beyond 30, within 60) → "true"
    With limit=30, only false_stmt is found → taken="false" → correct.
    With limit=60, true_stmt overrides → taken="true" → wrong direction.
    """
    from boa.coverage import _PATH_CLASSIFY_LIMIT, _resolve_jumpi_direction

    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    return 0
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    true_stmt = if_node.body[0]
    fn_node = ast.get_descendants(vy_ast.FunctionDef)[0]
    false_stmt_node = fn_node.body[-1]

    ast_map = {
        105: false_stmt_node,  # false body at taken_dest + 5
        135: true_stmt,  # true body at taken_dest + 35 (beyond limit 30)
    }

    result = _resolve_jumpi_direction(
        taken_dest=100,
        fallthrough=200,
        ast_map=ast_map,
        true_stmt=true_stmt,
        false_stmt=false_stmt_node,
        if_node=if_node,
    )
    assert result is False, (
        f"Expected taken=false (false_stmt at offset 5, true_stmt beyond "
        f"_PATH_CLASSIFY_LIMIT={_PATH_CLASSIFY_LIMIT}), got {result}"
    )


def test_find_if_jumpi_scan_limit():
    """_find_if_jumpi must not scan beyond _JUMPI_SCAN_LIMIT bytes.

    Mutation regression (scan_limit): increasing _JUMPI_SCAN_LIMIT from
    20 to 80 would cause _find_if_jumpi to find a JUMPI that's far from
    the condition, potentially matching a JUMPI belonging to a different
    branch.  Verify that a JUMPI placed beyond the limit is NOT found.
    """
    from boa.coverage import _JUMPI_SCAN_LIMIT, _find_if_jumpi

    _JUMPI = 0x57
    # Craft bytecode: single-byte instructions (e.g. POP = 0x50) with a
    # JUMPI placed exactly at from_pc + _JUMPI_SCAN_LIMIT (just beyond).
    # _find_if_jumpi starts scanning at from_pc + instruction_size(op).
    # We put a PUSH1 (0x60, 2 bytes) at from_pc, so scanning starts at
    # from_pc + 2.  Place JUMPI beyond the limit.
    from_pc = 0
    # bytecode: PUSH1 0x00 at PC 0, then filler, then JUMPI beyond limit
    filler_len = _JUMPI_SCAN_LIMIT  # JUMPI at from_pc + JUMPI_SCAN_LIMIT
    bytecode = bytes([0x60, 0x00])  # PUSH1 0x00 at PC 0 (2 bytes)
    bytecode += bytes([0x50] * (filler_len - 2))  # POP filler
    bytecode += bytes([_JUMPI])  # JUMPI at PC = _JUMPI_SCAN_LIMIT

    # The JUMPI is at exactly from_pc + _JUMPI_SCAN_LIMIT, which is the
    # limit boundary.  The scan goes up to min(from_pc + limit, len).
    # Since range is [scan, limit), the JUMPI AT the limit is excluded.
    result = _find_if_jumpi(bytecode, from_pc)
    assert result is None, (
        f"JUMPI at PC {_JUMPI_SCAN_LIMIT} (at limit boundary) should NOT be found, "
        f"got PC {result}.  _JUMPI_SCAN_LIMIT={_JUMPI_SCAN_LIMIT}"
    )

    # Verify a JUMPI just inside the limit IS found.
    bytecode_inside = bytes([0x60, 0x00])  # PUSH1 0x00 at PC 0
    bytecode_inside += bytes([0x50] * (filler_len - 3))  # one less filler
    bytecode_inside += bytes([_JUMPI])  # JUMPI at PC = _JUMPI_SCAN_LIMIT - 1

    result_inside = _find_if_jumpi(bytecode_inside, from_pc)
    assert result_inside == _JUMPI_SCAN_LIMIT - 1, (
        f"JUMPI at PC {_JUMPI_SCAN_LIMIT - 1} (inside limit) should be found, "
        f"got {result_inside}"
    )


def test_scan_limit_prevents_false_jumpi_match():
    """Scan limit prevents matching a far-away JUMPI from another branch.

    Mutation regression (scan_limit): with _JUMPI_SCAN_LIMIT = 80, a
    contract with two sequential if-statements could have the second If's
    JUMPI mistakenly found by a forward scan from the first If's event PC.
    With the correct limit of 20, the second If's JUMPI is out of range.

    Construct bytecode where a "wrong" JUMPI sits at PC 25 (within 80 but
    beyond 20).  With limit=20, it must NOT be found.
    """
    from boa.coverage import _JUMPI_SCAN_LIMIT, _find_if_jumpi

    _JUMPI = 0x57
    from_pc = 0
    bytecode = bytearray(100)
    bytecode[0] = 0x60  # PUSH1 at PC 0 (2 bytes)
    bytecode[1] = 0x00
    for i in range(2, 100):
        bytecode[i] = 0x50  # POP (single-byte)
    # Only a far JUMPI at PC 25
    bytecode[25] = _JUMPI
    bytecode = bytes(bytecode)

    result = _find_if_jumpi(bytecode, from_pc)
    assert result is None, (
        f"JUMPI at PC 25 is beyond _JUMPI_SCAN_LIMIT={_JUMPI_SCAN_LIMIT}, "
        f"should return None, got {result}"
    )


def test_path_classify_limit_minimum():
    """_PATH_CLASSIFY_LIMIT must be large enough to find branch body nodes.

    Mutation regression (path_classify_limit): reducing _PATH_CLASSIFY_LIMIT
    from 30 to 5 would prevent _classify_path from scanning far enough to
    find the true/false body node when several unmapped PCs separate the
    JUMPI destination from the first AST-mapped body instruction.

    Uses _resolve_jumpi_direction directly with a synthetic AST map where
    both body nodes sit at offset 10 from their respective destinations
    (beyond limit=5, within limit=30).  The false body is on the taken
    path and the true body on the fallthrough path, so the correct answer
    is False (taken != true).  With limit=5, both _classify_path calls
    return None → default True (wrong).
    """
    from boa.coverage import _PATH_CLASSIFY_LIMIT, _resolve_jumpi_direction

    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    return 0
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    true_stmt = if_node.body[0]  # Return(value=1)
    fn_node = ast.get_descendants(vy_ast.FunctionDef)[0]
    false_stmt_node = fn_node.body[-1]  # return 0

    # Place false_stmt on the taken path at offset 10, true_stmt on the
    # fallthrough path at offset 10.  With limit >= 11, _classify_path
    # correctly identifies taken=false and fall=true → return False.
    # With limit = 5, both return None → default True (wrong direction).
    ast_map = {
        110: false_stmt_node,  # false body at taken_dest + 10
        210: true_stmt,  # true body at fallthrough + 10
    }

    result = _resolve_jumpi_direction(
        taken_dest=100,
        fallthrough=200,
        ast_map=ast_map,
        true_stmt=true_stmt,
        false_stmt=false_stmt_node,
        if_node=if_node,
    )
    assert result is False, (
        f"Expected taken=false (false_stmt at taken+10, true_stmt at fall+10, "
        f"_PATH_CLASSIFY_LIMIT={_PATH_CLASSIFY_LIMIT}), got {result}"
    )


def test_jumpi_scan_limit_lower_bound():
    """_JUMPI_SCAN_LIMIT must be at least ~10 to find compound condition JUMPIs.

    Mutation regression (scan_limit lower bound): reducing _JUMPI_SCAN_LIMIT
    from 20 to 8 would prevent _find_if_jumpi from finding a decision JUMPI
    that's more than 8 bytes from the event PC.

    Uses _find_if_jumpi directly with crafted bytecode where the JUMPI
    sits at offset 10 from from_pc.  With limit=8, it's not found.
    With limit=20, it's found.
    """
    from boa.coverage import _JUMPI_SCAN_LIMIT, _find_if_jumpi

    _JUMPI = 0x57
    from_pc = 0
    # PUSH1 0x00 at PC 0 (2 bytes), then single-byte fillers, JUMPI at PC 10
    bytecode = bytearray(30)
    bytecode[0] = 0x60  # PUSH1
    bytecode[1] = 0x00
    for i in range(2, 30):
        bytecode[i] = 0x50  # POP
    bytecode[10] = _JUMPI  # decision JUMPI at offset 10

    result = _find_if_jumpi(bytes(bytecode), from_pc)
    assert result == 10, (
        f"JUMPI at PC 10 should be found with _JUMPI_SCAN_LIMIT="
        f"{_JUMPI_SCAN_LIMIT}, got {result}"
    )


# --- statement-only coverage ---


def test_statement_only_coverage():
    """branch=False path: lines are recorded via add_lines, not add_arcs."""
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        return 0
"""
    with _coverage_session_lines(source, lambda c: c.foo(10)) as (cov, vy_path):
        data = cov.get_data()
        measured = data.measured_files()
        assert vy_path in measured, f"{vy_path} not in measured files: {measured}"

        lines = data.lines(vy_path)
        assert lines is not None and len(lines) > 0, "No lines recorded"

        # No arcs should be stored in statement-only mode
        arcs = data.arcs(vy_path)
        assert not arcs, f"Expected no arcs in branch=False mode, got {arcs}"
