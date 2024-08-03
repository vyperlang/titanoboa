import boa


def test_load_partial_vvm():
    contract_deployer = boa.load_partial_vvm("contracts/vvm/mock_3_10.vy", "0.3.10")
    contract = contract_deployer.deploy(43)

    assert contract.foo() == 42
    assert contract.bar() == 43


def test_loads_partial_vvm():
    with open("contracts/vvm/mock_3_10.vy") as f:
        code = f.read()

    contract_deployer = boa.loads_partial_vvm(code, "0.3.10")
    contract = contract_deployer.deploy(43)

    assert contract.foo() == 42
    assert contract.bar() == 43


def test_load_vvm():
    contract = boa.load_vvm("contracts/vvm/mock_3_10.vy", "0.3.10", 43)

    assert contract.foo() == 42
    assert contract.bar() == 43


def test_loads_vvm():
    with open("contracts/vvm/mock_3_10.vy") as f:
        code = f.read()

    contract = boa.loads_vvm(code, "0.3.10", 43)

    assert contract.foo() == 42
    assert contract.bar() == 43
