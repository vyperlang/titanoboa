import os

import hypothesis
import pytest

from boa.util.sqlitedb import SqliteCache

# disable hypothesis deadline globally
hypothesis.settings.register_profile("ci", deadline=None)
hypothesis.settings.load_profile("ci")

# disable ignoring certain exceptions, see note in
# `SqliteCache.acquire_write_lock()`.
SqliteCache._debug = True


@pytest.fixture(scope="module")
def get_filepath(request):
    def _get_filepath(filename):
        test_dir = os.path.dirname(request.module.__file__)
        return os.path.join(test_dir, filename)

    return _get_filepath
