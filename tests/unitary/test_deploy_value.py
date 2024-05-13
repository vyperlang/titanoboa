import pytest

import boa

fund_me_source = """
@external
@payable
def __init__():
    pass
"""


# deploy with funds
def test_deploy_with_endowment():
    deployer = boa.loads_partial(fund_me_source)
    boa.env.set_balance(boa.env.eoa, 1000)
    assert boa.env.get_balance(boa.env.eoa) == 1000
    c = deployer.deploy(value=1000)

    assert boa.env.get_balance(boa.env.eoa) == 0
    assert boa.env.get_balance(c.address) == 1000


# try to call ctor with skip_init=True - must raise
def test_deploy_with_endowment_must_init():
    deployer = boa.loads_partial(fund_me_source)
    boa.env.set_balance(boa.env.eoa, 1000)
    with pytest.raises(Exception):
        deployer.deploy(value=1000, skip_init=True)
