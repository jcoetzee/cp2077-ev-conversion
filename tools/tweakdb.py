"""Check which TweakDB names exist in the compiled tweakdb.bin, without a full parser.

A TweakDBID is crc32(name) (uint32 LE) followed by len(name) (uint8). Flats are keyed
by "<record>.<property>", so a record name is confirmed by finding e.g.
"<record>.gears" in the binary.
"""
import struct
import zlib

DEFAULT_BINS = [
    "/Applications/Cyberpunk 2077/r6/cache/tweakdb.bin",
    "/Applications/Cyberpunk 2077/r6/cache/tweakdb_ep1.bin",
]


def tdbid_bytes(name: str) -> bytes:
    b = name.encode("utf-8")
    return struct.pack("<IB", zlib.crc32(b) & 0xFFFFFFFF, len(b))


class TweakDB:
    def __init__(self, paths=DEFAULT_BINS):
        self.blobs = [open(p, "rb").read() for p in paths]

    def has(self, name: str) -> bool:
        key = tdbid_bytes(name)
        return any(key in blob for blob in self.blobs)
