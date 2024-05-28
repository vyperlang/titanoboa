import contextlib
import hashlib
import os
import pickle
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Generic, Optional, TypeVar

from vyper.compiler import CompilerData

if TYPE_CHECKING:
    from boa.network import TraceObject


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


T = TypeVar("T")


class _DiskCache(Generic[T]):
    _instance: Optional["_DiskCache"] = None

    def __init__(self, cache_dir: str | Path, version_salt: str, ttl=_ONE_WEEK):
        self.cache_dir = Path(cache_dir).expanduser()
        self.version_salt = version_salt
        self.ttl = ttl  # time to live
        self.last_gc = 0.0  # last garbage collection

    def _collect_garbage(self, force=False) -> None:
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
    def _get_location(self, key: str) -> Path:
        preimage = (self.version_salt + key).encode("utf-8")
        digest = hashlib.sha256(preimage).digest().hex()
        return self.cache_dir.joinpath(f"{self.version_salt}/{digest}.pickle")

    # look up x in the cal; on a miss, write back to the cache
    def _lookup(self, key: str, func: Callable[[], T]) -> T:
        gc_interval = self.ttl // 10
        if time.time() - self.last_gc >= gc_interval:
            self._collect_garbage()

        p = self._get_location(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            with p.open("rb") as f:
                return pickle.loads(f.read())
        except OSError:
            res = func()
            tid = threading.get_ident()
            tmp_p = p.with_suffix(f".{tid}.unfinished")
            with tmp_p.open("wb") as f:
                f.write(pickle.dumps(res))
            # rename is atomic, don't really need to care about fsync
            # because worst case we will just rebuild the item
            tmp_p.rename(p)
            return res

    @classmethod
    def has(cls, key: str) -> bool | None:
        """
        Check if the cache contains the given key.
        :param key: The key to check
        :return: None if cache is disabled, True if key is in cache, False otherwise
        """
        if cls._instance is None:
            return None
        return cls._instance._get_location(key).exists()

    @classmethod
    def lookup(cls, key: str, func: Callable[[], T]) -> T:
        """
        Lookup the string in the cache, if it is not found, call the function to get the value.
        :param key: The string to look up
        :param func: The function to call if the string is not found
        :return: The value and whether it was found in the cache:
            - True if the value was found in the cache
            - False if the value was added to the cache
            - None if the cache is disabled
        """
        if cls._instance is None:
            return func()
        return cls._instance._lookup(key, func)


class CompileCache(_DiskCache[CompilerData]):
    _instance: Optional["CompileCache"] = None


class DeployCache(_DiskCache[tuple[dict, Optional["TraceObject"]]]):
    _instance: Optional["DeployCache"] = None
