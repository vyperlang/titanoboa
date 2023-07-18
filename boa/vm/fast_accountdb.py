from eth.db.account import AccountDB

class FastAccountDB(AccountDB):
    # this is a hotspot in super().
    def touch_account(self, address):
        self._accessed_accounts.add(address)
