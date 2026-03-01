"""Shared helpers for coverage tests.

Wraps private coverage.py APIs so drift is isolated to one place.
"""


def _analyze(cov, filename):
    """Wrap coverage.py's private _analyze() so API drift is isolated."""
    return cov._analyze(filename)
