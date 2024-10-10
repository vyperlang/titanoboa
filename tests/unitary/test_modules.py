from pathlib import Path

import pytest

import boa

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(params=["vyz", "vy", "b64"])
def module_contract(request):
    return boa.load(FIXTURES / f"module_contract.{request.param}")


def test_user_raise(module_contract):
    with boa.reverts("Error with message"):
        module_contract.fail()


def test_dev_reason(module_contract):
    with boa.reverts("some dev reason"):
        module_contract.fail_dev_reason()
