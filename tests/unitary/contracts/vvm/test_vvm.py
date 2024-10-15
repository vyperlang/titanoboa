import boa

mock_3_10_path = "tests/unitary/contracts/vvm/mock_3_10.vy"


def test_load_partial_vvm():
    contract_deployer = boa.load_partial(mock_3_10_path)
    contract = contract_deployer.deploy(43)

    assert contract.foo() == 42
    assert contract.bar() == 43


def test_loads_partial_vvm():
    with open(mock_3_10_path) as f:
        code = f.read()

    contract_deployer = boa.loads_partial(code)
    contract = contract_deployer.deploy(43)

    assert contract.foo() == 42
    assert contract.bar() == 43


def test_load_vvm():
    contract = boa.load(mock_3_10_path, 43)

    assert contract.foo() == 42
    assert contract.bar() == 43


def test_loads_vvm():
    with open(mock_3_10_path) as f:
        code = f.read()

    contract = boa.loads(code, 43)

    assert contract.foo() == 42
    assert contract.bar() == 43


def test_forward_args_on_deploy():
    with open(mock_3_10_path) as f:
        code = f.read()

    contract_vvm_deployer = boa.loads_partial(code)

    random_addy = boa.env.generate_address()

    contract = contract_vvm_deployer.deploy(43, override_address=random_addy)

    assert random_addy == contract.address
