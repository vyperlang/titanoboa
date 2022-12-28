interface ERC20:
    def name() -> String[2]: view

@external
def test() -> String[2]:
    return ERC20(0xdBdb4d16EdA451D0503b854CF79D55697F90c8DF).name()

@external
def test2() -> Bytes[32]:
    x: uint256 = 0
    return  raw_call(
    0xdBdb4d16EdA451D0503b854CF79D55697F90c8DF,
    b'\xc6a\x06W\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00',
    max_outsize=32,
    )
