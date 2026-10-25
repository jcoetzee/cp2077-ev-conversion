"""Rewrite CR2W (v195) files with some export chunks replaced.

Supports files laid out as: header + tables + export chunks stored contiguously in export
order, with no buffers (true for cooked audio metadata). Strings, names, imports and
properties tables are copied unchanged, so replacement chunks may only reference names
that already exist in the file.
"""
import struct
import zlib

HEADER_FMT = "<4sIIQIIIII"
CRC_OFFSET = 0x20


def _tables(data):
    return [list(struct.unpack_from("<III", data, 40 + i * 12)) for i in range(10)]


def rebuild(data: bytes, replace: dict) -> bytes:
    """replace: {export index: new chunk bytes}. Returns the new file."""
    tables = _tables(data)
    e_off, e_cnt, _ = tables[4]
    if tables[5][1]:
        raise ValueError("files with buffers are not supported")
    exports = [list(struct.unpack_from("<HHIIIII", data, e_off + i * 24)) for i in range(e_cnt)]
    chunks_start = min(e[4] for e in exports)
    if chunks_start != e_off + e_cnt * 24:
        raise ValueError("unexpected gap between export table and chunks")
    for a, b in zip(exports, exports[1:]):
        if a[4] + a[3] != b[4]:
            raise ValueError("export chunks are not contiguous")

    body, pos = bytearray(), chunks_start
    for i, e in enumerate(exports):
        chunk = replace.get(i, data[e[4] : e[4] + e[3]])
        e[3], e[4] = len(chunk), pos
        body += chunk
        pos += len(chunk)

    export_blob = b"".join(struct.pack("<HHIIIII", *e) for e in exports)
    tables[4][2] = zlib.crc32(export_blob)
    head = bytearray(data[:e_off])
    total = chunks_start + len(body)
    magic, ver, flags, ts, build, _oe, _be, _crc, nchunks = struct.unpack_from(HEADER_FMT, data, 0)
    struct.pack_into(HEADER_FMT, head, 0, magic, ver, flags, ts, build, total, total, 0xDEADBEEF, nchunks)
    for i, t in enumerate(tables):
        struct.pack_into("<III", head, 40 + i * 12, *t)
    struct.pack_into("<I", head, CRC_OFFSET, zlib.crc32(bytes(head[:160])))
    return bytes(head) + export_blob + bytes(body)


if __name__ == "__main__":
    import sys

    src = open(sys.argv[1], "rb").read()
    out = rebuild(src, {})
    print("identical" if out == src else "DIFFERENT", len(src), len(out))
    sys.exit(0 if out == src else 1)
