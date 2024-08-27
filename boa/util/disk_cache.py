import contextlib
import hashlib
import os
import pickle
import threading
import time
from pathlib import Path

_ONE_WEEK = 7 * 24 * 3600


@contextlib.contextmanager
# silence errors which can be thrown when handling a file that does
# not exist
def _silence_io_errors():
    try:
        yield
    # pypy throws FileNotFoundError
    except (OSError, FileNotFoundError):  # noqa: B014
        pass


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
                # squash errors, file might have been removed in race
                # (both p.stat() and p.unlink() can throw)
                with _silence_io_errors():
                    p = Path(root).joinpath(Path(f))
                    if time.time() - p.stat().st_atime > self.ttl or force:
                        p.unlink()

            # prune empty directories
            for d in dirs:
                # squash errors, directory might have been removed in race
                with _silence_io_errors():
                    Path(root).joinpath(Path(d)).rmdir()

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
            pass  # discard the stack trace in case of other errors

        res = func()
        # use process ID and thread ID to avoid race conditions
        job_id = f"{os.getpid()}.{threading.get_ident()}"
        tmp_p = p.with_suffix(f".{job_id}.unfinished")
        with tmp_p.open("wb") as f:
            f.write(pickle.dumps(res))
        # rename is atomic, don't really need to care about fsync
        # because worst case we will just rebuild the item
        tmp_p.rename(p)
        return res
