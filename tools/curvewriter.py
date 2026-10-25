"""Write cooked CurveSet (.curveset) CR2W files holding one Float curve.

Layout (reverse-engineered from vanilla engine torque curves, CR2W version 195):
  header (40 bytes) + 10 table descriptors (offset, count, crc32)
  strings table, names table (string offset + FNV-1a 32 hash), properties (16 zero
  bytes), one export entry, then the export's data chunk.
  Header CRC = crc32 of the first 160 bytes with the CRC field set to 0xDEADBEEF.
  Table CRCs = crc32 of the table bytes.

Data chunk:
  00
  prop cookingPlatform : ECookingPlatform = <PLATFORM_*>
  prop curves : array:CurveSetEntry = [ { name: CName "1", curve: curveData:Float } ]
  00 00
A property is: name index u16, type index u16, size u32 (includes itself), value.
curveData:Float value: u32 count, count x (f32 x, f32 y), u8 interpolation, u8 link type.
"""
import struct
import zlib

STRINGS = ["", "CurveSet", "cookingPlatform", "ECookingPlatform", None, "curves",
           "array:CurveSetEntry", "name", "CName", "1", "curve", "curveData:Float"]
PLATFORM_IDX = 4


def fnv1a32(s: str) -> int:
    """Name-table hash: FNV-1a 64 folded to 32 bits (high ^ low). Empty name -> 0."""
    if not s:
        return 0
    h = 0xCBF29CE484222325
    for b in s.encode():
        h = ((h ^ b) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return (h >> 32) ^ (h & 0xFFFFFFFF)


def prop(name_idx, type_idx, value: bytes) -> bytes:
    return struct.pack("<HHI", name_idx, type_idx, len(value) + 4) + value


def build(points, platform="PLATFORM_Mac", interpolation=3, link_type=0) -> bytes:
    strings = list(STRINGS)
    strings[PLATFORM_IDX] = platform

    curve = struct.pack("<I", len(points)) + b"".join(struct.pack("<ff", x, y) for x, y in points)
    curve += bytes([interpolation, link_type])
    entry = b"\x00" + prop(7, 8, struct.pack("<H", 9)) + prop(10, 11, curve) + b"\x00\x00"
    chunk = (b"\x00" + prop(2, 3, struct.pack("<H", PLATFORM_IDX))
             + prop(5, 6, struct.pack("<I", 1) + entry) + b"\x00\x00")

    str_blob, offsets = b"", []
    for s in strings:
        offsets.append(len(str_blob))
        str_blob += s.encode() + b"\0"
    names_blob = b"".join(struct.pack("<II", o, fnv1a32(s)) for o, s in zip(offsets, strings))
    props_blob = b"\0" * 16

    off_strings = 160
    off_names = off_strings + len(str_blob)
    off_props = off_names + len(names_blob)
    off_exports = off_props + len(props_blob)
    off_chunk = off_exports + 24
    export_blob = struct.pack("<HHIIIII", 1, 0, 0, len(chunk), off_chunk, 0, 0)
    total = off_chunk + len(chunk)

    tables = [(off_strings, len(str_blob), zlib.crc32(str_blob)),
              (off_names, len(strings), zlib.crc32(names_blob)),
              (0, 0, 0),
              (off_props, 1, zlib.crc32(props_blob)),
              (off_exports, 1, zlib.crc32(export_blob))] + [(0, 0, 0)] * 5
    header = bytearray(struct.pack("<4sIIQIIIII", b"CR2W", 195, 0, 0, 0, total, total, 0xDEADBEEF, 6))
    header += b"".join(struct.pack("<III", *t) for t in tables)
    struct.pack_into("<I", header, 0x20, zlib.crc32(bytes(header)))
    return bytes(header) + str_blob + names_blob + props_blob + export_blob + chunk


if __name__ == "__main__":
    import sys

    import curveset

    ok = True
    for path in sys.argv[1:]:
        data = open(path, "rb").read()
        _off, pts, interp = curveset.find_curve(data)
        rebuilt = build(pts, curveset.platform(data), interp & 0xFF)
        same = rebuilt == data
        ok &= same
        print(f"{'identical' if same else 'DIFFERENT'}  {path.rsplit('/', 1)[-1]}")
    sys.exit(0 if ok else 1)
