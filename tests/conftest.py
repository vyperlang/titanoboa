import os

import pytest


@pytest.fixture
def get_filepath(request):
    def _get_filepath(filename):
        test_dir = os.path.dirname(request.module.__file__)
        return os.path.join(test_dir, filename)

    return _get_filepath
