from typing import Any, Optional

from eth_utils import to_canonical_address, to_checksum_address
from vyper.utils import keccak256


# TODO replace return type with upcoming AddressType wrapper
def get_create2_address(
    blueprint_bytecode: bytes, deployer_address: Any, salt: bytes
) -> str:
    _, _, initcode = parse_erc5202(blueprint_bytecode)

    initcode_hash = keccak256(initcode)

    prefix = b"\xFF"
    addr = to_canonical_address(deployer_address)
    if len(salt) != 32:
        raise ValueError(f"bad salt (must be bytes32): {salt!r}")

    create2_hash = keccak256(prefix + addr + salt + initcode_hash)

    return to_checksum_address(create2_hash[12:])


# basically copied from ERC5202 reference implementation
def parse_erc5202(blueprint_bytecode: bytes) -> tuple[int, Optional[bytes], bytes]:
    """
    Given bytecode as a sequence of bytes, parse the blueprint preamble and
    deconstruct the bytecode into:
        the ERC version, preamble data and initcode.
    Raises an exception if the bytecode is not a valid blueprint contract
    according to this ERC.
    arguments:
        blueprint_bytecode: a `bytes` object representing the blueprint bytecode
    returns:
        (version,
         None if <length encoding bits> is 0, otherwise the bytes of the data section,
         the bytes of the initcode,
        )
    """
    if blueprint_bytecode[:2] != b"\xFE\x71":
        raise ValueError("Not a blueprint!")

    erc_version = (blueprint_bytecode[2] & 0b11111100) >> 2

    n_length_bytes = blueprint_bytecode[2] & 0b11
    if n_length_bytes == 0b11:
        raise ValueError("Reserved bits are set")

    data_length = int.from_bytes(
        blueprint_bytecode[3 : 3 + n_length_bytes], byteorder="big"
    )

    if n_length_bytes == 0:
        preamble_data = None
    else:
        data_start = 3 + n_length_bytes
        preamble_data = blueprint_bytecode[data_start : data_start + data_length]

    initcode = blueprint_bytecode[3 + n_length_bytes + data_length :]

    if len(initcode) == 0:
        raise ValueError("Empty initcode!")

    return erc_version, preamble_data, initcode
