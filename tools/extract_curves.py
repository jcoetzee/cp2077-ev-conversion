"""Extract the vanilla curves the build needs into extracted/curves/:
  * every engine torque curve referenced by gearCurvesPath in the tweak sources
  * the HUD speedometer curve set (vehicle_ui, curve 'speed_to_multiplier'), used to
    convert "100 km/h on the speedometer" into game units

Requires tools/ooz_port/libooz.dylib.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import curveset  # noqa: E402
import rdar  # noqa: E402

TWEAKS = os.path.join(ROOT, "redmod", "tools", "redmod", "tweaks")
GAME_ARC = "/Applications/Cyberpunk 2077/archive/Mac/content/basegame_4_gamedata.archive"
ENGINE_ARC = "/Applications/Cyberpunk 2077/archive/Mac/content/basegame_1_engine.archive"
# The vehicle_ui curve set's depot path is not referenced anywhere readable; it was found by
# searching archive contents for 'speed_to_multiplier' (tools/find_in_archives.py).
SPEEDO_HASH = 0xA14C10FC10024C4A
OUT = os.path.join(ROOT, "extracted", "curves")


def main():
    paths = set()
    for dirpath, _, files in os.walk(TWEAKS):
        for fn in files:
            if fn.endswith(".tweak"):
                text = open(os.path.join(dirpath, fn), encoding="utf-8", errors="replace").read()
                paths.update(re.findall(r'gearCurvesPath\s*=\s*"([^"]+)"', text))
    os.makedirs(OUT, exist_ok=True)
    idx = rdar.read_index(GAME_ARC)
    for p in sorted(paths):
        data = rdar.extract(GAME_ARC, p, idx)
        name = p.split("\\")[-1]
        open(os.path.join(OUT, name), "wb").write(data)
        print(f"{len(data):6} bytes  {name}")

    _v, files, segs = rdar.read_index(ENGINE_ARC)
    s0, s1, _n = files[SPEEDO_HASH]
    data = b"".join(rdar.decompress_segment(*rdar.read_segment(ENGINE_ARC, s)) for s in segs[s0:s1])
    pts = curveset.read_curve(data, "speed_to_multiplier")
    open(os.path.join(OUT, "vehicle_ui_speed_to_multiplier.bin"), "wb").write(data)
    print(f"{len(data):6} bytes  vehicle_ui_speed_to_multiplier.bin ({len(pts)} points)")


if __name__ == "__main__":
    main()
