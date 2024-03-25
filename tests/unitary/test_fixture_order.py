import pytest

# cf. https://github.com/pytest-dev/pytest/issues/12135
# if the finalizers run out of order, should hit some errors like:
#   File "../.venvs/boa/lib/python3.11/site-packages/eth/db/journal.py", line 172, in discard
# eth_utils.exceptions.ValidationError: No checkpoint 31 was found


@pytest.fixture(scope="module", autouse=True, params=[7, 8, 9])
def fixture_autouse(request):
    print(f"SETUP FIXTURE AUTOUSE {request.param}")
    yield
    print(f"TEARDOWN FIXTURE AUTOUSE {request.param}")


@pytest.fixture(scope="module", params=[1, 2, 3])
def fixture_test(request):
    print(f"SETUP FIXTURE TEST {request.param}")
    yield
    print(f"TEARDOWN FIXTURE TEST {request.param}")


def test_1(fixture_test):
    pass


def test_2():
    pass
