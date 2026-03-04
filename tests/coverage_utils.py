"""Shared helpers for coverage tests.

Wraps private coverage.py APIs so drift is isolated to one place.
"""

import contextlib

from boa.environment import Env


def _analyze(cov, filename):
    """Wrap coverage.py's private _analyze() so API drift is isolated."""
    return cov._analyze(filename)


@contextlib.contextmanager
def saved_coverage_state():
    """Save and restore Env coverage state around a block."""
    saved_coverage = Env._coverage_enabled
    saved_branch = Env._branch_coverage_enabled
    saved_tracer = Env._coverage_tracer
    try:
        yield
    finally:
        Env._coverage_enabled = saved_coverage
        Env._branch_coverage_enabled = saved_branch
        Env._coverage_tracer = saved_tracer
