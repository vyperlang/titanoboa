# pragma version 0.3.10

foo: public(uint256)
bar: public(uint256)

map: HashMap[address, uint256]
is_empty: bool

@external
def __init__(bar: uint256):
    self.foo = 42
    self.bar = bar
    self.is_empty = True

@external
def set_map(x: uint256):
    self._set_map(msg.sender, x)

@internal
def _set_map(addr: address, x: uint256):
    self.map[addr] = x
    self.is_empty = False
