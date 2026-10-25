"""Diagnostic 3: are RAW segments (stored size == real size, no Kraken header) readable?

  Sport R-7 "Vigilante": vanilla engine; gearCurvesPath -> new path holding its vanilla
      curve stored RAW.            Drives like vanilla -> raw storage works.
  Hella EC-D I360: the full EV engine from the main build (single gear, EV torque curve
      stored RAW, calibrated torque).  Drives            -> the EV design itself works.
All other engines stay vanilla; chassis/brakes from the main build.
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_ev as b  # noqa: E402
import curveset  # noqa: E402
import curvewriter  # noqa: E402
import rdar  # noqa: E402

HELLA = "v_standard2_archer_hella_getto_inline5"
R7 = "Vehicle.v_sport1_quadra_sport_r7_rocket_inline3"
CURVES = "base\\gameplay\\vehicles\\curves\\engine_torque"


def main():
    assert b.STORAGE == "raw"
    b.main()  # full build -> build/EVConversion (all engines, raw curves)
    full = os.path.join(b.ROOT, "build", "EVConversion")
    engines = json.load(open(os.path.join(full, "r6", "tweaks", "EVConversion.json")))
    hella = engines[f"Vehicle.{HELLA}"]
    hella_curve = hella["gearCurvesPath"]
    full_arc = os.path.join(full, "archive", "EVConversion.archive")
    hella_raw = rdar.extract(full_arc, hella_curve)

    van = open(os.path.join(b.ROOT, "extracted", "curves", "large_balanced_sc.curveset"), "rb").read()
    r7_path = f"{b.CURVE_DIR}\\diag3_large_balanced_sc.curveset"

    out = os.path.join(b.ROOT, "build", "diag3")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(os.path.join(out, "r6", "tweaks"))
    os.makedirs(os.path.join(out, "archive"))
    # rebuild YAML/JSON from the JSON record (strip $type so to_yaml/to_json re-add it)
    hrec = {k: v for k, v in hella.items() if k != "gears"}
    hrec["gears"] = [{k: v for k, v in g.items() if k != "$type"} for g in hella["gears"]]
    recs_out = {HELLA: hrec, R7.split(".", 1)[1]: {"gearCurvesPath": r7_path}}
    open(os.path.join(out, "r6", "tweaks", "EVConversion.yaml"), "w").write(b.to_yaml(recs_out, "DIAGNOSTIC 3"))
    open(os.path.join(out, "r6", "tweaks", "EVConversion.json"), "w").write(b.to_json(recs_out) + "\n")
    for f in ("EVConversion_Chassis.yaml", "EVConversion_Chassis.json"):
        shutil.copy(os.path.join(full, "r6", "tweaks", f), os.path.join(out, "r6", "tweaks", f))
    arc = os.path.join(out, "archive", "EVConversion.archive")
    rdar.write_archive(arc, [(r7_path, van, len(van)), (hella_curve, hella_raw, len(hella_raw))])
    idx = rdar.read_index(arc)
    assert rdar.extract(arc, r7_path, idx) == van
    assert rdar.extract(arc, hella_curve, idx) == hella_raw
    pts = curveset.find_curve(hella_raw)[1]
    print(f"Hella: torque {hella['engineMaxTorque']}, curve {hella_curve.split(chr(92))[-1]} (raw): "
          + " ".join(f"{x*100:.0f}:{y*100:.0f}" for x, y in pts[:6]) + " ...")
    print(f"R-7:   vanilla engine, curve -> {r7_path} (raw copy, {len(van)} bytes)")


if __name__ == "__main__":
    main()
