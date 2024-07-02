import boa

code = """
crvUSD: constant(address) = 0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E
integer: constant(uint256) = 1518919871651
integer2: constant(uint256) = integer + 1
"""


def test_get_constant():
    deployer = boa.loads_partial(code)
    assert deployer._constants.crvUSD == "0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E"
    assert deployer._constants.integer == 1518919871651
    assert deployer._constants.integer2 == 1518919871652
    contract = deployer.deploy()
    assert contract._constants.crvUSD == "0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E"
