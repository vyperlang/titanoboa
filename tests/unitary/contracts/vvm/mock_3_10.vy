# pragma version 0.3.10

foo: public(uint256)
bar: public(uint256)

@external
def __init__(bar: uint256):
    self.foo = 42
    self.bar = bar