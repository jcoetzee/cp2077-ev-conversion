"""Diagnostic 2: why did the game not load our curve file?

  Sport R-7 "Vigilante" (v_sport1_quadra_sport_r7_rocket_inline3):
      vanilla engine, gearCurvesPath -> NEW path in our archive, holding vanilla's own
      Kraken-COMPRESSED bytes of its curve (copied verbatim from the game archive).
      Drives like vanilla  -> our archive loads and new paths work; uncompressed
                              blocks were the problem.
      Broken again         -> archive not loaded, or new paths don't resolve.
  Hella EC-D I360 (v_standard2_archer_hella_getto_inline5):
      single forward gear (known good), vanilla gearCurvesPath (med_torquey_na).
      Our archive ALSO holds a file at that VANILLA path: a flat 50% curve stored as an
      uncompressed block. Every engine using med_torquey_na (Regular_Medium, Utility
      and the cars built on them) would lose about half its torque.
      Clearly weaker       -> archive loads, overrides vanilla paths, uncompressed OK.
      Same as last test    -> override ignored (uncompressed rejected or lower priority).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_ev as b  # noqa: E402
import curvewriter  # noqa: E402
import rdar  # noqa: E402
from tweakdb import TweakDB  # noqa: E402

GAME_ARC = "/Applications/Cyberpunk 2077/archive/Mac/content/basegame_4_gamedata.archive"
HELLA = "v_standard2_archer_hella_getto_inline5"
R7 = "v_sport1_quadra_sport_r7_rocket_inline3"
CURVES = "base\\gameplay\\vehicles\\curves\\engine_torque"


def main():
    recs = b.load_records()
    engines = {c: (l, f, g) for c, l, f, g, _o in b.find_engines(recs, TweakDB())}

    _l, hf, hg = engines[HELLA]
    hella = {
        "gearChangeTime": b.EV["shift_time"],
        "gearChangeCooldown": b.EV["shift_time"],
        "finalGearTorqueDecimationScalor": 1.0,
        "gears": [dict(hg[0]), {"minSpeed": 0.0, "maxSpeed": hg[-1]["maxSpeed"],
                                "minEngineRPM": b.num(hf, "minRPM", "800"),
                                "maxEngineRPM": b.num(hf, "maxRPM", "5000"),
                                "torqueMultiplier": 0.6}],
    }
    assert hf["gearCurvesPath"] == f"{CURVES}\\med_torquey_na.curveset"

    # R-7: verbatim compressed segment of vanilla large_balanced_sc at a new path
    _v, files, segs = rdar.read_index(GAME_ARC)
    s0, s1, _n = files[rdar.depot_hash(f"{CURVES}\\large_balanced_sc.curveset")]
    assert s1 - s0 == 1
    seg_bytes, size = rdar.read_segment(GAME_ARC, segs[s0])
    assert seg_bytes[:4] == b"KARK"
    r7_path = f"{b.CURVE_DIR}\\diag2_large_balanced_sc.curveset"

    # Hella: flat 50% curve, uncompressed, at the VANILLA med_torquey_na path
    flat = curvewriter.build([(i / 12, 0.5) for i in range(13)], platform="PLATFORM_Mac")

    out = os.path.join(b.ROOT, "build", "diag2")
    os.makedirs(os.path.join(out, "r6", "tweaks"), exist_ok=True)
    os.makedirs(os.path.join(out, "archive"), exist_ok=True)
    recs_out = {HELLA: hella, R7: {"gearCurvesPath": r7_path}}
    open(os.path.join(out, "r6", "tweaks", "EVConversion.yaml"), "w").write(b.to_yaml(recs_out, "DIAGNOSTIC 2"))
    open(os.path.join(out, "r6", "tweaks", "EVConversion.json"), "w").write(b.to_json(recs_out) + "\n")
    arc = os.path.join(out, "archive", "EVConversion.archive")
    rdar.write_archive(arc, [
        (r7_path, seg_bytes, size),
        (f"{CURVES}\\med_torquey_na.curveset", rdar.kark_stored(flat), len(flat)),
    ])
    idx = rdar.read_index(arc)
    assert rdar.extract(arc, r7_path, idx) == rdar.extract(GAME_ARC, f"{CURVES}\\large_balanced_sc.curveset")
    assert rdar.extract(arc, f"{CURVES}\\med_torquey_na.curveset", idx) == flat
    print(f"R-7  -> {r7_path}: vanilla compressed bytes ({len(seg_bytes)} -> {size})")
    print(f"Hella-> {CURVES}\\med_torquey_na.curveset overridden with flat 50% curve, uncompressed")


if __name__ == "__main__":
    main()
