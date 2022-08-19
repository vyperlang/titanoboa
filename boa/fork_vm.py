from boa.util.lrudict import lrudict



class AccountDBFork(AccountDB):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._balance_cache = lrudict(0x10000)
        self._transactionCount_cache = lrudict(0x10000)
        self._code_cache = lrudict(0x10000)
        self._storage_cache = lrudict(0x10000)

    def get_balance(self, address):
        lamb = lambda: self._rpc.fetch("eth_getBalance", {"address": address})
        return self._balance_cache.setdefault(address, lamb)

    def get_nonce(self, address):
        lamb = lambda: self._rpc.fetch("eth_getTransactionCount", {"address": address})
        return self._transactionCount_cache.setdefault(address, lamb)

    def get_code(self, address):
        lamb = lambda: self._rpc.fetch("eth_getCode", {"address": address})
        return self._code_cache.setdefault(address, lamb)

    def set_code(self, address, code):
        super().set_code(address, code)
        self._code_cache[address] = code

    def get_storage(self, address, slot):
        lamb = lambda: self._rpc.fetch("eth_getStorageAt", {"params": [address, slot]})
        return self._storage_cache.setdefault((address, slot), lamb)

    def set_storage(self, address, slot, value):
        super().set_storage(address, slot, value)
        self._storage_cache[(address, slot)] = value

    def account_exists(self, address):
        if super().account_exists(address):
            return True

        return self.get_balance(address) > 0 or self.get_nonce(address) > 0
