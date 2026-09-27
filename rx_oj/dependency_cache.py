"""Bounded, process-safe dependency snapshots. Archives are never extracted on the host."""

import fcntl
import hashlib
import os
import re
import tempfile
import time
from contextlib import contextmanager


class DependencyCache:
    def __init__(self, settings):
        self.directory = settings.data_dir / "dependency-cache"
        self.capacity = settings.dependency_cache_mb * 1024 * 1024
        self.entry_limit = settings.dependency_entry_mb * 1024 * 1024
        self.max_age = settings.dependency_cache_days * 86400

    @contextmanager
    def locked(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / ".lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def path(self, key):
        if not re.fullmatch(r"[0-9a-f]{64}", key):
            raise ValueError("Invalid dependency cache key")
        return self.directory / (key + ".cache")

    def prune(self, reserve=0):
        # Writers hold this same lock, so temporary files here belong to interrupted writes.
        for path in self.directory.glob(".write-*"):
            path.unlink()
        now = time.time()
        entries = []
        for path in self.directory.glob("*.cache"):
            stat = path.stat()
            if now - stat.st_mtime > self.max_age or stat.st_size > self.entry_limit + 65:
                path.unlink()
            else:
                entries.append((stat.st_mtime, stat.st_size, path))
        total = sum(size for _, size, _ in entries)
        for _, size, path in sorted(entries):
            if total + reserve <= self.capacity:
                break
            path.unlink()
            total -= size

    def get(self, key):
        if not self.capacity or not self.max_age:
            return None
        with self.locked():
            self.prune()
            path = self.path(key)
            if not path.exists():
                return None
            payload = path.read_bytes()
            digest, separator, data = payload.partition(b"\n")
            if not separator or digest != hashlib.sha256(data).hexdigest().encode():
                path.unlink()
                return None
            os.utime(path, None)
            return data

    def put(self, key, data):
        size = len(data) + 65
        if not self.max_age or len(data) > self.entry_limit or size > self.capacity:
            return
        with self.locked():
            path = self.path(key)
            if path.exists():
                path.unlink()
            self.prune(reserve=size)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    dir=self.directory, prefix=".write-", delete=False
                ) as stream:
                    temporary = stream.name
                    stream.write(hashlib.sha256(data).hexdigest().encode() + b"\n" + data)
                os.replace(temporary, path)
            finally:
                if temporary and os.path.exists(temporary):
                    os.unlink(temporary)
