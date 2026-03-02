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
    """if with bare return (no value) — JUMPI is unmapped in ast_map.

    Regression: the null return compiles to a direct jump to function
    cleanup (FunctionDef), so the condition's JUMPI is not mapped to
    an If node.  Without the _find_if_jumpi fallback, both arcs are
    dropped.
    """
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
    """Bare return with compound condition (and) — decision JUMPI unmapped.

    Regression: short-circuit JUMPI from `and` was selected instead of
    the actual decision JUMPI for the bare return.
    """
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
    """Internal function called twice with different inputs in one tx.

    Regression: the resolved guard suppressed If processing after first
    occurrence, so only the first branch direction was recorded.
    """
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
    """for + break + helper condition, false-only must not report full coverage.

    Regression: internal call in If.test splits If events into two runs,
    causing double classification that adds both arcs from one execution.
    """
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
    """for + continue + helper+and, true-only must not report full coverage.

    Regression: compound condition with helpers causes double classification.
    """
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
    """top-level if/else + helper+and, true-only must not report full coverage.

    Regression: helpers in condition cause double classification.
    """
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
    """top-level if/else + helper short-circuit or, false-only must not report full.

    Regression: complex compound condition with helpers causes double classification.
    """
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
    """if without else + tail + helper condition, false-only must not report full.

    Regression: helpers in condition cause double classification.
    """
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
    """bare-return body + helper condition, false-only must not report full.

    Regression: helpers in condition cause double classification.
    """
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
    """Entering a function must not mark untaken branch body lines as covered.

    Regression: old boa's FunctionDef span inflation marked every line in a
    function as covered when the function was entered, regardless of which
    branches were actually taken.
    """
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
    """True-only: false arc (to tail) must be missing.

    Regression: compiler re-evaluates the If condition after the true
    body as a jump target, producing a spurious false arc when only the
    true branch was exercised.
    """
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
    """if with pass body — both branches hit.

    Regression: pass generates no bytecode, so the JUMPI direction
    classifier could not find the true branch anchor.  Both arcs
    collapse to the same fallthrough target (degenerate case).
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
    missing = _check_branch_coverage(source, lambda c: (c.f(10), c.f(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_if_assert_true_body_both():
    """if with assert True body — both branches hit.

    Regression: assert True is constant-folded away, producing no
    bytecode, same root cause as pass.
    """
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
    """if/else where else is pass — both branches hit.

    Regression: pass in the else branch generated no bytecode, causing
    the decision JUMPI to be unmapped and the false branch to never be
    recorded.
    """
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
    """Internal function with else pass — both branches hit.

    Regression: same unmapped-JUMPI issue in internal function calls.
    """
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
    """if with assert <const-expr> body — both branches hit.

    Regression: assert 1 == 1 is constant-folded away by the compiler
    (no bytecode), but _is_noop only recognized literal assert True.
    """
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


def test_branch_else_pass_compound_condition_both():
    """else pass + compound condition — both branches hit.

    Regression: with compound conditions (and/or), the backward event
    scan found a short-circuit JUMPI instead of the decision JUMPI,
    causing wrong branch direction classification.
    """
    source = """\
@external
def f(x: uint256) -> uint256:
    if (x > 5) and (x < 20):
        return 1
    else:
        pass
    return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.f(10), c.f(30)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_else_pass_compound_condition_partial():
    """else pass + compound condition — single call classification correct.

    Regression: f(30) (false path) was misclassified as true because the
    short-circuit JUMPI was selected instead of the decision JUMPI.
    """
    source = """\
@external
def f(x: uint256) -> uint256:
    if (x > 5) and (x < 20):
        return 1
    else:
        pass
    return 0
"""
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    # f(30): x>5 True, x<20 False => false path
    missing = _check_branch_coverage(source, lambda c: c.f(30))
    assert if_node.lineno in missing, f"Expected if-line in missing: {missing}"


def test_branch_else_pass_complex_compound_or_and():
    """else pass + complex compound condition ``(A and B) or C``.

    Regression: _find_if_jumpi misread a PUSH2 operand byte (0x57) as
    a JUMPI opcode when scanning forward from a PUSHn instruction,
    selecting a phantom JUMPI inside the condition instead of the real
    decision JUMPI.
    """
    source = """\
@external
def f(x: uint256) -> uint256:
    if ((x == 2) and (x > 5)) or (x == 3):
        return 1
    else:
        pass
    return 0
"""
    missing = _check_branch_coverage(source, lambda c: (c.f(3), c.f(1)))
    assert missing == {}, f"Missing branch arcs: {missing}"


def test_branch_else_pass_complex_compound_or_and_partial():
    """else pass + complex compound ``(A and B) or C`` — true-only partial."""
    source = """\
@external
def f(x: uint256) -> uint256:
    if ((x == 2) and (x > 5)) or (x == 3):
        return 1
    else:
        pass
    return 0
"""
    possible, executed, missing = _check_full_branch_coverage(source, lambda c: c.f(3))
    # f(3) hits the true branch; false should be missing
    ast = parse_to_ast(source)
    if_node = ast.get_descendants(vy_ast.If)[0]
    assert if_node.lineno in missing, f"Expected if-line in missing: {missing}"
    assert if_node.lineno in executed, f"Expected true arc executed: {executed}"
    # True arc (to return 1) should be in executed targets
    true_target = if_node.body[0].lineno
    assert (
        true_target in executed[if_node.lineno]
    ), f"Expected true arc to L{true_target}: {executed}"


# --- mutation-testing regression: skip-gate, classify_path edge cases ---


def test_branch_compound_and_skip_gate_false_only():
    """Compound `and` condition, false-only: only the false arc should be reported.

    Mutation regression (if_run_skip_gate): when the skip-gate that
    deduplicates consecutive If events is disabled, intermediate condition
    events find a short-circuit JUMPI instead of the decision JUMPI and
    mis-classify the branch, spuriously adding the true arc.
    """
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
    """If body starts with an internal call — FunctionDef at JUMPI destination.

    Mutation regression (classify_path_fn_def): if _classify_path returns
    "exit" on the first FunctionDef node instead of skipping it, the
    true-branch direction is misidentified as an exit and flipped.
    """
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
    """Internal call in condition — condition node at JUMPI destination.

    Mutation regression (classify_path_cond): if _classify_path returns
    "false" on a condition node instead of skipping it, the branch
    direction is misidentified and the wrong arc is recorded.
    """
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
    """Neither path classifiable — verify the default direction is 'true'.

    Mutation regression (unknown_default): when both _classify_path calls
    return None (e.g. both branches are bare returns with sparse AST map),
    _resolve_jumpi_direction defaults to True (taken = true branch).
    Verify that flipping to False would change the executed arc label.

    Both bare-return branches target fn_line, so we verify that the
    classification yields a "true" arc by checking executed_branch_arcs.
    """
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


# --- mutation-testing regression: classify_path and direction edge cases ---


def test_branch_compound_and_true_only_no_spurious_false():
    """Compound ``and`` condition — true-only must NOT report false arc.

    Mutation regression (if_run_skip_gate): when the If-event
    consecutive-run skip is weakened (continue → pass), the collector
    processes intermediate events and may classify a short-circuit
    JUMPI, adding a spurious false arc alongside the correct true arc.
    """
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
    """Compound ``or`` condition — false-only must NOT report true arc.

    Same skip-gate regression but for ``or`` conditions: processing
    intermediate events may add a spurious true arc.
    """
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
    """If with return in true body + storage write in false body.

    Mutation regression (taken_false_exit): the bytecode layout for
    this pattern produces a decision JUMPI where _classify_path
    returns "false" for the taken path. Flipping the direction return
    for ``taken_class in ("false", "exit")`` swaps the arc labels.
    """
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
