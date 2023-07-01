from eth.vm.memory import Memory

from boa.vm.utils import ceil32, to_bytes, to_int


# a py-evm eth.vm.Memory compatible implementation of memory.
# most memory is aligned. add a cache which avoids converting
# between bytes and ints where possible
class FastMem(Memory):
    __slots__ = ("mem_cache", "_bytes", "needs_writeback")

    def __init__(self):
        # XXX: check if this would be faster as dict?
        self.mem_cache = []  # cached words

        # words which are in the cache but have not been written
        # to the backing bytes
        self.needs_writeback = []

        super().__init__()

    _DIRTY = object()

    def extend(self, start_position, size_bytes):
        # i.e. ceil32(len(self)) // 32
        new_size = (start_position + size_bytes + 31) // 32
        if (size_difference := new_size - len(self.mem_cache)) > 0:
            self.mem_cache.extend([self._DIRTY] * size_difference)
            self.needs_writeback.extend([False] * size_difference)
            super().extend(start_position, size_bytes)

    def read_word(self, start_position):
        if start_position % 32 == 0:
            if (ret := self.mem_cache[start_position // 32]) is not self._DIRTY:
                return ret

        ret = to_int(self.read_bytes(start_position, 32))
        self.mem_cache[start_position // 32] = ret
        return ret

    def _writeback(self, start_position, size):
        start = start_position // 32
        end = ceil32(start_position + size) // 32
        for ix in range(start, end):
            if self.needs_writeback[ix]:
                word = self.mem_cache[ix]
                assert ix + 32 <= len(self._bytes)
                self._bytes[ix * 32 : ix * 32 + 32] = to_bytes(word)
                self.needs_writeback[ix] = False

    def read_bytes(self, start_position, size):
        self._writeback(start_position, size)
        return super().read_bytes(start_position, size)

    def read(self, start_position, size):
        self._writeback(start_position, size)
        return super().read(start_position, size)

    def write_word(self, start_position, int_val):
        if start_position % 32 == 0:
            self.mem_cache[start_position // 32] = int_val
            self.needs_writeback[start_position // 32] = True
        else:
            self.write(start_position, 32, to_bytes(int_val))

    def write(self, start_position, size, value):
        start = start_position // 32
        end = (start_position + size + 31) // 32

        # need to write back, in case this is not an aligned write.
        self._writeback(start_position, size)
        for i in range(start, end):
            self.mem_cache[i] = self._DIRTY
            assert self.needs_writeback[i] is False

        super().write(start_position, size, value)
