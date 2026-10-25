"""Check which TweakDB names exist in the compiled tweakdb.bin, without a full parser.

A TweakDBID is crc32(name) (uint32 LE) followed by len(name) (uint8). Flats are keyed
by "<record>.<property>", so a record name is confirmed by finding e.g.
"<record>.gears" in the binary.

Each lookup scans ~94 MB, so batches are spread across all CPU cores (has_many) and
results are cached on disk, keyed by the size and mtime of the .bin files. The matching
rule is identical for single lookups, batches and cached results.
"""
import json
import multiprocessing as mp
import os
import struct
import zlib

DEFAULT_BINS = [
    "/Applications/Cyberpunk 2077/r6/cache/tweakdb.bin",
    "/Applications/Cyberpunk 2077/r6/cache/tweakdb_ep1.bin",
]
CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "build", "tweakdb_lookup_cache.json")

_WORKER_BLOBS = None


def tdbid_bytes(name: str) -> bytes:
    b = name.encode("utf-8")
    return struct.pack("<IB", zlib.crc32(b) & 0xFFFFFFFF, len(b))


def _worker_init(paths):
    global _WORKER_BLOBS
    _WORKER_BLOBS = [open(p, "rb").read() for p in paths]


def _worker_has(name):
    key = tdbid_bytes(name)
    return any(key in blob for blob in _WORKER_BLOBS)


class TweakDB:
    def __init__(self, paths=DEFAULT_BINS, cache_path=CACHE_PATH, workers=None):
        self.paths = list(paths)
        self.blobs = [open(p, "rb").read() for p in self.paths]
        self.workers = workers or os.cpu_count() or 1
        self.cache_path = cache_path
        stamp = [[p, os.path.getsize(p), os.path.getmtime(p)] for p in self.paths]
        self._stamp = stamp
        self._cache = {}
        if cache_path and os.path.exists(cache_path):
            try:
                saved = json.load(open(cache_path))
                if saved.get("stamp") == stamp:
                    self._cache = saved["results"]
            except (ValueError, KeyError):
                self._cache = {}

    def has(self, name: str) -> bool:
        if name not in self._cache:
            key = tdbid_bytes(name)
            self._cache[name] = any(key in blob for blob in self.blobs)
        return self._cache[name]

    def has_many(self, names) -> dict:
        """{name: bool} for every name, computed in parallel for names not yet cached."""
        todo = sorted({n for n in names if n not in self._cache})
        if len(todo) > 50 and self.workers > 1:
            ctx = mp.get_context("spawn")
            with ctx.Pool(self.workers, initializer=_worker_init, initargs=(self.paths,)) as pool:
                for n, found in zip(todo, pool.map(_worker_has, todo, chunksize=16)):
                    self._cache[n] = found
        else:
            for n in todo:
                self.has(n)
        return {n: self._cache[n] for n in names}

    def save(self):
        if not self.cache_path:
            return
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        tmp = self.cache_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"stamp": self._stamp, "results": self._cache}, f)
        os.replace(tmp, self.cache_path)
