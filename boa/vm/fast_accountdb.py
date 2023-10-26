from eth.db.account import AccountDB


def _touch_account_patcher(self, address):
    self._accessed_accounts.add(address)


_BOA_PATCHED = object()


def patch_pyevm_state_object(state_object):
    if getattr(state_object, "__boa_patched__", None) == _BOA_PATCHED:
        return
    accountdb = state_object._account_db
    accountdb._restore_touch_account = accountdb.touch_account
    accountdb.touch_account = _touch_account_patcher.__get__(accountdb, AccountDB)
    state_object.__boa_patched__ = _BOA_PATCHED


def unpatch_pyevm_state_object(state_object):
    if not getattr(state_object, "__boa_patched__", None) == _BOA_PATCHED:
        return
    accountdb = state_object._account_db
    accountdb.touch_account = accountdb._restore_touch_account
    delattr(accountdb, "_restore_touch_account")
    delattr(state_object, "__boa_patched__")
