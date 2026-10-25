"""Diagnostic build: test the two new pieces of the single-gear build separately.

  Hella EC-D I360 (v_standard2_archer_hella_getto_inline5):
      single forward gear, but the VANILLA torque curve path (no custom archive needed).
      -> tests whether the game accepts one forward gear.
  Sport R-7 "Vigilante" (v_sport1_quadra_sport_r7_rocket_inline3):
      completely vanilla engine EXCEPT gearCurvesPath, which points at a byte-identical
      copy of its vanilla curve inside our archive (uncompressed Kraken block).
      -> tests whether the game loads curve files from our archive.
All other engines stay vanilla. Chassis/brake file from the main build is kept (it worked).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_ev as b  # noqa: E402
import curveset  # noqa: E402
import curvewriter  # noqa: E402
import rdar  # noqa: E402
from tweakdb import TweakDB  # noqa: E402

HELLA = "v_standard2_archer_hella_getto_inline5"
R7 = "v_sport1_quadra_sport_r7_rocket_inline3"


def main():
    recs = b.load_records()
    engines = {c: (l, f, g) for c, l, f, g, _o in b.find_engines(recs, TweakDB())}

    # Hella: one forward gear 0 -> top speed, vanilla curve, multiplier ~ vanilla mid gear
    _l, hf, hg = engines[HELLA]
    vmax = hg[-1]["maxSpeed"]
    hella = {
        "gearChangeTime": b.EV["shift_time"],
        "gearChangeCooldown": b.EV["shift_time"],
        "finalGearTorqueDecimationScalor": 1.0,
        "gears": [dict(hg[0]), {"minSpeed": 0.0, "maxSpeed": vmax,
                                "minEngineRPM": b.num(hf, "minRPM", "800"),
                                "maxEngineRPM": b.num(hf, "maxRPM", "5000"),
                                "torqueMultiplier": 0.6}],
    }

    # R-7: vanilla curve copied to a new path inside our archive
    _l, rf, _g = engines[R7]
    vanilla_path = rf["gearCurvesPath"]
    name = vanilla_path.split("\\")[-1]
    copy_path = f"{b.CURVE_DIR}\\diag_{name}"
    raw = open(os.path.join(b.ROOT, "extracted", "curves", name), "rb").read()
    _o, pts, interp = curveset.find_curve(raw)
    assert curvewriter.build(pts, curveset.platform(raw), interp & 0xFF) == raw
    r7 = {"gearCurvesPath": copy_path}

    out = os.path.join(b.ROOT, "build", "diag")
    os.makedirs(os.path.join(out, "r6", "tweaks"), exist_ok=True)
    os.makedirs(os.path.join(out, "archive"), exist_ok=True)
    recs_out = {HELLA: hella, R7: r7}
    open(os.path.join(out, "r6", "tweaks", "EVConversion.yaml"), "w").write(b.to_yaml(recs_out, "DIAGNOSTIC"))
    open(os.path.join(out, "r6", "tweaks", "EVConversion.json"), "w").write(b.to_json(recs_out) + "\n")
    arc = os.path.join(out, "archive", "EVConversion.archive")
    rdar.write_archive(arc, [(copy_path, rdar.kark_stored(raw), len(raw))])
    assert rdar.extract(arc, copy_path) == raw
    print(f"Hella: 1 forward gear 0-{vmax} m/s, curve {vanilla_path.split(chr(92))[-1]} (vanilla path)")
    print(f"R-7:   vanilla engine, curve -> {copy_path} (copy of {name}, {len(raw)} bytes)")
    print(json.dumps(recs_out, indent=1)[:1200])


if __name__ == "__main__":
    main()
