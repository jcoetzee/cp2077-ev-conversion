"""Minimal read-only reader for REDengine 4 .archive (RDAR) files.

Usage: python3 rdar.py <archive> <depot path> [<depot path> ...]
Prints where each file's data segments are and how they are compressed.
"""
import struct
import sys


def fnv1a64(s: str) -> int:
    h = 0xCBF29CE484222325
    for b in s.encode("utf-8"):
        h ^= b
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def depot_hash(path: str) -> int:
    return fnv1a64(path.lower().replace("/", "\\"))


def read_index(path):
    with open(path, "rb") as f:
        magic, version, idx_pos, idx_size = struct.unpack("<4sIQI", f.read(20))
        if magic != b"RDAR":
            raise ValueError(f"not an RDAR archive: {magic!r}")
        f.seek(idx_pos)
        _ft_off, _ft_size, _crc, n_files, n_segs, _n_deps = struct.unpack(
            "<IIQIII", f.read(28)
        )
        files = {}
        for _ in range(n_files):
            h, _ts, ninl, s0, s1, _d0, _d1 = struct.unpack("<QqIIIII", f.read(36))
            f.read(20)  # sha1
            files[h] = (s0, s1, ninl)
        segs = [struct.unpack("<QII", f.read(16)) for _ in range(n_segs)]
    return version, files, segs


def read_segment(arc, seg):
    off, zsize, size = seg
    with open(arc, "rb") as f:
        f.seek(off)
        return f.read(zsize), size


_OOZ = None


def _ooz():
    global _OOZ
    if _OOZ is None:
        import ctypes
        import os

        lib = os.path.join(os.path.dirname(__file__), "ooz_port", "libooz.dylib")
        _OOZ = ctypes.CDLL(lib)
        _OOZ.ooz_kraken_decompress.restype = ctypes.c_int
        _OOZ.ooz_kraken_decompress.argtypes = [
            ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_size_t
        ]
    return _OOZ


def decompress_segment(data: bytes, size: int) -> bytes:
    """Segments are either stored raw or as 'KARK' + uint32 size + Kraken stream."""
    if len(data) == size:
        return data
    if data[:4] != b"KARK":
        raise ValueError(f"unknown segment encoding {data[:4]!r}")
    import ctypes

    (raw_size,) = struct.unpack("<I", data[4:8])
    out = ctypes.create_string_buffer(raw_size + 64)  # decoder may overrun slightly
    n = _ooz().ooz_kraken_decompress(data[8:], len(data) - 8, out, raw_size)
    if n != raw_size:
        raise ValueError(f"Kraken decode failed: got {n}, expected {raw_size}")
    return out.raw[:raw_size]


def extract(arc, depot_path, index=None) -> bytes:
    """Return the full file (main segment followed by its buffers)."""
    _version, files, segs = index or read_index(arc)
    e = files.get(depot_hash(depot_path))
    if not e:
        raise KeyError(depot_path)
    s0, s1, _ninl = e
    return b"".join(decompress_segment(*read_segment(arc, seg)) for seg in segs[s0:s1])


EMPTY_SHA1 = bytes.fromhex("da39a3ee5e6b4b0d3255bfef95601890afd80709")
DATA_START = 0xAC
ALIGN = 0x1000
PAD_BYTE = bytes([0xD9])  # alignment filler used by the official packer


def crc64_xz(data: bytes) -> int:
    poly = 0xC96C5795D7870F42  # reflected ECMA-182
    crc = 0xFFFFFFFFFFFFFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ (poly if crc & 1 else 0)
    return crc ^ 0xFFFFFFFFFFFFFFFF


def write_archive(path, files, timestamp=133428308453933857):
    """files: list of (depot_path, segment_bytes, uncompressed_size). One segment per file."""
    pad = lambda n: (-n) % ALIGN  # noqa: E731
    body, segs, entries = bytearray(), [], []
    for i, (depot, seg, size) in enumerate(sorted(files, key=lambda f: depot_hash(f[0]))):
        segs.append((DATA_START + len(body), len(seg), size))
        entries.append((depot_hash(depot), timestamp, 0, i, i + 1, 0, 0))
        body += seg
    data_end = DATA_START + len(body)
    idx_pos = data_end + pad(data_end)
    tail = struct.pack("<III", len(entries), len(segs), 0)
    tail += b"".join(struct.pack("<QqIIIII", *e) + EMPTY_SHA1 for e in entries)
    tail += b"".join(struct.pack("<QII", *s) for s in segs)
    index = struct.pack("<IIQ", 8, 8 + len(tail), crc64_xz(tail)) + tail
    total = idx_pos + len(index)
    total += pad(total)
    header = struct.pack("<4sIQIQIQ", b"RDAR", 12, idx_pos, len(index), 0, 0, total)
    out = bytearray(header) + b"\0" * (DATA_START - len(header)) + body
    out += PAD_BYTE * (idx_pos - len(out)) + index
    out += PAD_BYTE * (total - len(out))
    with open(path, "wb") as f:
        f.write(out)


if __name__ == "__main__":
    arc, *paths = sys.argv[1:]
    version, files, segs = read_index(arc)
    print(f"version={version} files={len(files)} segments={len(segs)}")
    for p in paths:
        e = files.get(depot_hash(p))
        if not e:
            print("MISSING", p)
            continue
        s0, s1, _ninl = e
        print(p, f"segments {s0}-{s1}")
        for seg in segs[s0:s1]:
            data, size = read_segment(arc, seg)
            print(f"   off={seg[0]} zsize={seg[1]} size={size} head={data[:4]!r}")
