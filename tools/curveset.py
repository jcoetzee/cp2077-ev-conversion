"""Decode the single Float curve stored in a cooked CurveSet (.curveset) CR2W file.

Layout found by inspection: ... uint32 point_count, then point_count pairs of
(float x, float y), then uint32 interpolation type. x is normalised RPM (0..1),
y is the torque fraction.
"""
import struct
import sys


def find_curve(data: bytes):
    best = None
    for off in range(0, len(data) - 4, 1):
        (n,) = struct.unpack_from("<I", data, off)
        if not 2 <= n <= 64:
            continue
        end = off + 4 + n * 8
        if end + 4 > len(data):
            continue
        pts = [struct.unpack_from("<ff", data, off + 4 + i * 8) for i in range(n)]
        xs = [p[0] for p in pts]
        if xs[0] != 0.0 or abs(xs[-1] - 1.0) > 1e-4:
            continue
        if any(b <= a for a, b in zip(xs, xs[1:])):
            continue
        if not all(0.0 <= y <= 2.0 for _, y in pts):
            continue
        (interp,) = struct.unpack_from("<I", data, end)
        best = (off, pts, interp)
    return best


def platform(data: bytes) -> str:
    i = data.find(b"PLATFORM_")
    return data[i : data.index(b"\0", i)].decode() if i >= 0 else "?"


def read_curve(data: bytes, name=None):
    """Points of a named Float curve in a CurveSet, read by walking the CR2W properties
    (works for any x range, unlike find_curve which expects x in 0..1).
    Value layout: u32 count, count x (f32 x, f32 y), u8 interpolation, u8 link type."""
    from cr2w_walk import CR2W

    c = CR2W(data)
    props = {p[0]: p for p in c.export_props(0)}
    _n, _t, off, size = props["curves"]
    (count,) = struct.unpack_from("<I", data, off)
    pos = off + 4
    for _ in range(count):
        entry = {p[0]: p for p in c.read_struct(pos + 1, off + size)}
        ename = c.value(*entry["name"][1:])
        _cn, _ct, coff, csize = entry["curve"]
        if name is None or ename == name:
            (n,) = struct.unpack_from("<I", data, coff)
            return [struct.unpack_from("<ff", data, coff + 4 + 8 * k) for k in range(n)]
        last = list(entry.values())[-1]
        pos = last[2] + last[3] + 2
    raise KeyError(name)


if __name__ == "__main__":
    for path in sys.argv[1:]:
        data = open(path, "rb").read()
        found = find_curve(data)
        name = path.rsplit("/", 1)[-1].replace(".curveset", "")
        if not found:
            print(f"{name}: curve not found")
            continue
        off, pts, interp = found
        print(f"{name}  ({len(pts)} points, interp={interp}, {platform(data)}, offset=0x{off:x})")
        print("   rpm%  " + " ".join(f"{x*100:5.0f}" for x, _ in pts))
        print("   torq% " + " ".join(f"{y*100:5.0f}" for _, y in pts))
