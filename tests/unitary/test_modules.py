import pytest
from pathlib import Path

import boa

FIXTURES = Path(__file__).parent / "fixtures"

@pytest.fixture
def module_contract():
    return boa.load(FIXTURES / "module_contract.vy")

def test_user_raise(module_contract):
    with boa.reverts("Error with message"):
        module_contract.fail()

def test_dev_reason(module_contract):
    with boa.reverts("some dev reason"):
        module_contract.fail_dev_reason()
