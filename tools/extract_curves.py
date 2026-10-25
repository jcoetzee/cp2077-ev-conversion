"""Extract every vanilla engine torque curve referenced by the tweak sources.

Reads gearCurvesPath values from the REDmod tweak sources and writes the decompressed
.curveset files to extracted/curves/. Requires tools/ooz_port/libooz.dylib.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import rdar  # noqa: E402

TWEAKS = os.path.join(ROOT, "redmod", "tools", "redmod", "tweaks")
GAME_ARC = "/Applications/Cyberpunk 2077/archive/Mac/content/basegame_4_gamedata.archive"
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


if __name__ == "__main__":
    main()
