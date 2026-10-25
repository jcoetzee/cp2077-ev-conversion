"""Package build/EVConversion into a mod.io upload zip, in the layout used by console-approved
mods: about.json, r6/tweaks/*, archive/* at the root of the zip.

Usage: python3 tools/package.py <platform>     (platform: mac, windows, ps5, xboxseriesx, switch2)
Writes dist/EVConversion-<version>-<platform>.zip and prints its MD5.
Only "mac" can be built today: the archive is made from Mac game data (curve platform stamp
and the Mac copy of the audio metadata).
"""
import hashlib
import json
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_ev as b  # noqa: E402

SOURCE = os.path.join(b.ROOT, "build", b.MOD_NAME)
DIST = os.path.join(b.ROOT, "dist")
SUPPORTED = {"mac"}
EXPECTED = ["about.json", "r6/tweaks/EVConversion.yaml", "r6/tweaks/EVConversion.json",
            "r6/tweaks/EVConversion_Chassis.yaml", "r6/tweaks/EVConversion_Chassis.json",
            f"archive/{b.MOD_NAME}.archive"]
FIXED_TIME = (2026, 1, 1, 0, 0, 0)  # reproducible zips


def main():
    platform = sys.argv[1] if len(sys.argv) > 1 else "mac"
    if platform not in SUPPORTED:
        sys.exit(f"{platform}: not supported yet (build data is from the Mac game)")
    files = sorted(os.path.relpath(os.path.join(r, f), SOURCE).replace(os.sep, "/")
                   for r, _d, fs in os.walk(SOURCE) for f in fs)
    if sorted(EXPECTED) != files:
        sys.exit(f"unexpected build contents: {files}")
    about = json.load(open(os.path.join(SOURCE, "about.json")))
    if about["ModInfo"]["ModID"] != b.MOD_ID:
        sys.exit("about.json ModID does not match build_ev.MOD_ID; rebuild first")
    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, f"{b.MOD_NAME}-{b.VERSION}-{platform}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in EXPECTED:
            info = zipfile.ZipInfo(rel, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, open(os.path.join(SOURCE, rel), "rb").read())
    md5 = hashlib.md5(open(out, "rb").read()).hexdigest()
    print(f"{out}  {os.path.getsize(out)} bytes  md5 {md5}")


if __name__ == "__main__":
    main()
