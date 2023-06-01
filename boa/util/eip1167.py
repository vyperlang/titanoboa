EIP1167_PREFIX = bytes.fromhex("363d3d373d3d3d363d73")
EIP1167_SUFFIX = bytes.fromhex("5af43d82803e903d91602b57fd5bf3")


def is_eip1167_contract(bytecode):
    return bytecode.startswith(EIP1167_PREFIX) and bytecode.endswith(EIP1167_SUFFIX)


def extract_eip1167_address(bytecode):
    assert is_eip1167_contract(bytecode)
    ret = bytecode.strip(EIP1167_PREFIX).strip(EIP1167_SUFFIX)
    assert len(ret) == 20
    return ret
