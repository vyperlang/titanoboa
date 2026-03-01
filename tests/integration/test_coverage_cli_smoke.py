import os
import subprocess
import sys
import textwrap

import coverage
import pytest
import vyper.ast as vy_ast
from vyper.ast.parse import parse_to_ast

import boa
from boa.environment import Env
from tests.coverage_utils import _analyze

# repo root so the subprocess always imports the local checkout
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONTRACT_SOURCE = textwrap.dedent(
    """\
    @external
    def foo(x: uint256) -> uint256:
        if x > 5:
            return 1
        else:
            return 0
"""
)


@pytest.fixture()
def coverage_workspace(tmp_path):
    """Create a temp directory with .coveragerc, contract.vy, and runner.py."""
    rcfile = tmp_path / ".coveragerc"
    rcfile.write_text("[run]\nplugins = boa.coverage\n")

    contract = tmp_path / "contract.vy"
    contract.write_text(CONTRACT_SOURCE)

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    runner = tmp_path / "runner.py"
    runner.write_text(
        textwrap.dedent(
            f"""\
        import boa
        from boa.interpret import set_cache_dir

        set_cache_dir({repr(str(cache_dir))})
        c = boa.load({repr(str(contract))})
        c.foo(10)  # only true branch
    """
        )
    )

    return tmp_path


def test_coverage_cli_smoke(coverage_workspace):
    tmp_path = coverage_workspace

    env = os.environ.copy()
    env["PYTHONPATH"] = REPO_ROOT + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "coverage",
            "run",
            "--branch",
            "--rcfile=.coveragerc",
            "runner.py",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr

    # load .coverage data (use the same rcfile so the plugin is registered)
    rcfile = str(tmp_path / ".coveragerc")
    cov = coverage.Coverage(data_file=str(tmp_path / ".coverage"), config_file=rcfile)
    cov.load()
    data = cov.get_data()

    # .vy file was measured
    measured = data.measured_files()
    vy_files = [f for f in measured if f.endswith(".vy")]
    assert len(vy_files) == 1

    # branch arcs exist
    vy_file = vy_files[0]
    arcs = data.arcs(vy_file)
    assert arcs is not None and len(arcs) > 0

    # the `if` line has a missing branch (only one path executed)
    tree = parse_to_ast(CONTRACT_SOURCE)
    if_line = tree.get_descendants(vy_ast.If)[0].lineno

    analysis = _analyze(cov, vy_file)
    missing = dict(analysis.missing_branch_arcs())
    assert if_line in missing, (
        f"Expected line {if_line} (the if-statement) to have missing arcs, "
        f"got missing arcs at lines: {sorted(missing)}"
    )


def test_loads_no_crash_on_report():
    """boa.loads() must not crash coverage report.

    Regression: source-string contracts resolve to <unknown>, which
    was recorded as a measured file.  coverage.report() then raised
    NoSource because no .vy file exists at that path.
    """
    source = """\
@external
def foo(x: uint256) -> uint256:
    if x > 5:
        return 1
    else:
        return 0
"""
    saved = Env._coverage_enabled
    try:
        cov = coverage.Coverage(branch=True, config_file=False, data_file=None)
        cov.set_option("run:plugins", ["boa.coverage"])
        cov.start()
        try:
            c = boa.loads(source)
            c.foo(10)
            c.foo(1)
        finally:
            cov.stop()

        data = cov.get_data()
        unknown = [f for f in data.measured_files() if "unknown" in f]
        assert unknown == [], f"<unknown> should not be measured: {unknown}"

        # Must not raise NoSource
        cov.report(file=open(os.devnull, "w"))
    finally:
        Env._coverage_enabled = saved
