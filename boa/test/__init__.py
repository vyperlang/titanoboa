#!/usr/bin/python3
"""
Test utils borrowed from Brownie.
"""

import warnings
from hypothesis.errors import HypothesisDeprecationWarning

from .strategies import strategy  # NOQA: F401

# hypothesis warns against combining function-scoped fixtures with @given
# but in brownie this is a documented and useful behaviour. In boa.test we
# will follow the same logic:
warnings.filterwarnings("ignore", category=HypothesisDeprecationWarning)
