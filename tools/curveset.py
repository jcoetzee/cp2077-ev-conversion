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
