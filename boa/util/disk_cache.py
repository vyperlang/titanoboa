import hashlib
import os
import pickle
import time
from pathlib import Path

_ONE_WEEK = 7 * 24 * 3600


class DiskCache:
    def __init__(self, cache_dir, version_salt, ttl=_ONE_WEEK):
        self.cache_dir = Path(cache_dir).expanduser()
        self.version_salt = version_salt
        self.ttl = ttl

        self.last_gc = 0

    def gc(self, force=False):
        for root, dirs, files in os.walk(self.cache_dir):
            # delete items older than ttl
            for f in files:
                p = Path(root).joinpath(Path(f))
                if time.time() - p.stat().st_atime > self.ttl or force:
                    p.unlink()
            for d in dirs:
                # prune empty directories
                try:
                    Path(root).joinpath(Path(d)).rmdir()
                # pypy throws FileNotFoundError
                except (OSError, FileNotFoundError):  # noqa: B014
                    pass

        self.last_gc = time.time()

    # content-addressable location
    def cal(self, string):
        preimage = (self.version_salt + string).encode("utf-8")
        digest = hashlib.sha256(preimage).digest().hex()
        return self.cache_dir.joinpath(f"{self.version_salt}/{digest}.pickle")

    # look up x in the cal; on a miss, write back to the cache
    def caching_lookup(self, string, func):
        gc_interval = self.ttl // 10
        if time.time() - self.last_gc >= gc_interval:
            self.gc()

        p = self.cal(string)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            with p.open("rb") as f:
                return pickle.loads(f.read())
        except OSError:
            res = func()
            tmp_p = p.with_suffix(".unfinished")
            with tmp_p.open("wb") as f:
                f.write(pickle.dumps(res))
            # rename is atomic, don't really need to care about fsync
            # because worst case we will just rebuild the item
            tmp_p.rename(p)
            return res
