import boa

mock_3_10_path = "tests/unitary/contracts/vvm/mock_3_10.vy"
with open(mock_3_10_path) as f:
    mock_3_10_code = f.read()


def test_load_partial_vvm():
    contract_deployer = boa.load_partial(mock_3_10_path)
    contract = contract_deployer.deploy(43)

    assert contract.foo() == 42
    assert contract.bar() == 43


def test_loads_partial_vvm():
    contract_deployer = boa.loads_partial(mock_3_10_code)
    contract = contract_deployer.deploy(43)

    assert contract.foo() == 42
    assert contract.bar() == 43


def test_load_vvm():
    contract = boa.load(mock_3_10_path, 43)

    assert contract.foo() == 42
    assert contract.bar() == 43


def test_loads_vvm():
    contract = boa.loads(mock_3_10_code, 43)

    assert contract.foo() == 42
    assert contract.bar() == 43


def test_vvm_storage():
    contract = boa.loads(mock_3_10_code, 43)
    assert contract._storage.is_empty.get()
    assert contract._storage.map.get(boa.env.eoa) == 0
    contract.set_map(69)
    assert not contract._storage.is_empty.get()
    assert contract._storage.map.get(boa.env.eoa) == 69


def test_vvm_internal():
    contract = boa.loads(mock_3_10_code, 43)
    assert not hasattr(contract.internal, "set_map")
    address = boa.env.generate_address()
    contract.internal._set_map(address, 69)
    assert contract._storage.map.get(address) == 69


def test_vvm_eval():
    contract = boa.loads(mock_3_10_code, 43)
    assert contract.eval("self.bar", "uint256") == 43
    assert contract.eval("self.bar = 44") is None
    assert contract.bar() == 44
