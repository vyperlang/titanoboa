from pathlib import Path

import boa

FIXTURES = Path(__file__).parent / "fixtures"


def test_throw():
    c = boa.load(FIXTURES / "module_contract.vy")
    with boa.reverts("Error with message"):
        c.fail()
