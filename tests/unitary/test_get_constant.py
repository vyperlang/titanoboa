import boa

code = """
crvUSD: constant(address) = 0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E
integer: constant(uint256) = 1518919871651
"""


def test_get_constant():
    deployer = boa.loads_partial(code)
    deployer._constants.crvUSD == "0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E"
    deployer._constants.crvUSD == 1518919871651
    contract = deployer.deploy()
    contract._constants.crvUSD == "0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E"
    contract._constants.crvUSD == 1518919871651
