"""Package the mod into the single mod.io upload zip used for every platform.

Layout (as in console-approved mods): about.json, r6/tweaks/*, archive/* at the root.
The zip is made from build/EVConversion_pc (python3 tools/build_ev.py pc): PC-labelled
resources built from the Windows game data. Approved mods ship PC-labelled archives
byte-identical to Mac, PlayStation 5, Xbox Series X|S and Nintendo Switch 2, and some use one
file for all platforms, so this one file is requested for all five.

Usage: python3 tools/package.py            -> dist/EVConversion-<version>.zip (prints MD5)

build/EVConversion (python3 tools/build_ev.py mac, Mac-labelled) is kept for local testing
on the Mac only and is not uploaded.
"""
import hashlib
import json
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_ev as b  # noqa: E402

SOURCE = os.path.join(b.ROOT, "build", b.TARGETS["pc"]["out"])
DIST = os.path.join(b.ROOT, "dist")
EXPECTED = ["about.json", "r6/tweaks/EVConversion.yaml", "r6/tweaks/EVConversion.json",
            "r6/tweaks/EVConversion_Chassis.yaml", "r6/tweaks/EVConversion_Chassis.json",
            f"archive/{b.MOD_NAME}.archive"]
FIXED_TIME = (2026, 1, 1, 0, 0, 0)  # reproducible zips


def main():
    files = sorted(os.path.relpath(os.path.join(r, f), SOURCE).replace(os.sep, "/")
                   for r, _d, fs in os.walk(SOURCE) for f in fs)
    if sorted(EXPECTED) != files:
        sys.exit(f"unexpected build contents: {files}")
    about = json.load(open(os.path.join(SOURCE, "about.json")))
    if about["ModInfo"]["ModID"] != b.MOD_ID:
        sys.exit("about.json ModID does not match build_ev.MOD_ID; rebuild first")
    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, f"{b.MOD_NAME}-{b.VERSION}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in EXPECTED:
            info = zipfile.ZipInfo(rel, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, open(os.path.join(SOURCE, rel), "rb").read())
    md5 = hashlib.md5(open(out, "rb").read()).hexdigest()
    print(f"{out}  {os.path.getsize(out)} bytes  md5 {md5}")


if __name__ == "__main__":
    main()
