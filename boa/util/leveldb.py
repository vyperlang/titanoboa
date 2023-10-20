# copy py-evm LevelDB implementation, removed in
# https://github.com/ethereum/py-evm/commit/c2ca44a1212a287
import plyvel
from eth.db.backends.base import BaseDB


class LevelDB(BaseDB):
    # Creates db as a class variable to avoid level db lock error
    def __init__(self, db_path, max_open_files: int = None) -> None:
        self.db = plyvel.DB(
            db_path,
            create_if_missing=True,
            error_if_exists=False,
            max_open_files=max_open_files,
        )

    def __getitem__(self, key: bytes) -> bytes:
        v = self.db.get(key)
        if v is None:
            raise KeyError(key)
        return v

    def __setitem__(self, key: bytes, value: bytes) -> None:
        self.db.put(key, value)

    def _exists(self, key: bytes) -> bool:
        return self.db.get(key) is not None

    def __delitem__(self, key: bytes) -> None:
        if self.db.get(key) is None:
            raise KeyError(key)
        self.db.delete(key)
