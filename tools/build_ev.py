"""Build the EV Conversion mod from vanilla game data.

Reads the vanilla REDmod tweak sources and the compiled TweakDB, and writes the mod to
build/EVConversion/:
  r6/tweaks/EVConversion.yaml/.json          engines (one record per compiled engine)
  r6/tweaks/EVConversion_Chassis.yaml/.json  drive models and wheel (brake) presets
  archive/EVConversion.archive               EV torque curves + hybrid vehicle sound profiles

Per engine (all cars, variants and motorcycles):
  * One forward gear from 0 to vanilla top speed; reverse untouched.
  * Custom EV torque curve: flat to a base speed, then constant power (see ev_single.py).
  * engineMaxTorque scaled so 0-100 km/h (speedometer) and 0-80% of top speed match vanilla
    at the EV's higher mass (see accel.py).
  * Lower flywheel inertia (snappier response), higher resistance torque (regen-like lift-off).
Per drive model / wheel preset: mass, inertia and brake torque scaled by CHASSIS mass_factor;
centre of mass lowered on cars. Drivetrains are unchanged.
"""
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TWEAKS = os.path.join(ROOT, "redmod", "tools", "redmod", "tweaks")
sys.path.insert(0, HERE)
import curveset  # noqa: E402

EV = {
    "flywheel_scale": 0.5,   # x vanilla flyWheelMomentOfInertia
    "resistance_scale": 1.5,  # x vanilla resistanceTorque (lift-off regen feel)
    # gearChangeTime/gearChangeCooldown override (None keeps each engine's vanilla values).
    # Applies to the launch-gear change and to reverse <-> forward. Vanilla 0.2-0.4 s leaves
    # a drive gap at the launch gear. Never use 0: the engine revs but never drives.
    # 0.01 s tested in-game: drives, brakes to a stop and reverses (0.05 s also worked).
    "shift_time": 0.01,
    # Short first gear (m/s). Required: with a single forward gear down to 0 the game cannot
    # switch from braking to reverse, and holding brake hovers at ~11 mph (found in-game,
    # fixed by a 3 m/s launch gear). RPM is continuous across it, and the hybrid sound
    # profiles have no gear-shift events, so the change is silent. Calibration includes it.
    "launch_gear_speed": 3.0,
}

SOUND = {
    # Fraction of the vanilla idle->redline range the single gear sweeps from 0 to top
    # speed. 1.0 keeps vanilla engine volume; 0.4 was too quiet over city noise.
    "rpm_cap": 1.0,
    # Hybrid profiles (tools/audio_hybrid.py): every car/bike keeps its own sound profile
    # (brakes, tyres, horn, doors, radio) with the engine section replaced by the Basilisk's.
    # Ships as a replacement of base\sound\metadata\cooked_metadata.audio_metadata.
    "hybrid": True,
}

# Custom torque curves
CURVE_DIR = "base\\gameplay\\vehicles\\curves\\engine_torque\\ev_conversion"
CURVE_STEP = 0.01   # base-speed fractions are rounded to this, so engines share curve files
PLATFORM = "PLATFORM_Mac"  # cooking platform stamped into curve files
# Files are stored raw in the archive (stored size == real size). The game cannot read
# a Kraken header wrapped around uncompressed data.

CHASSIS = {
    "mass_factor": 1.10,  # battery pack (2077 cell density assumed): +10% mass, also inertia and brakes
    "com_drop_m": 0.05,   # floor-mounted pack lowers the centre of mass (cars only)
}

import accel  # noqa: E402
import audio_hybrid  # noqa: E402
import curvewriter  # noqa: E402
import ev_single  # noqa: E402
import rdar  # noqa: E402

MOD_NAME = "EVConversion"


def load_records(package="Vehicle"):
    """Return {record_name: (parent, body_text)} for every record in one tweak package.

    Names collide across packages (e.g. UI icons reuse vehicle names), so only files
    declaring `package <package>` are read.
    """
    recs = {}
    head = re.compile(r"^([A-Za-z0-9_]+)\s*:\s*([A-Za-z0-9_.]+)\s*$", re.M)
    pkg_line = re.compile(r"^\s*package\s+(\w+)", re.M)
    for dirpath, _, files in os.walk(TWEAKS):
        for fn in files:
            if not fn.endswith(".tweak"):
                continue
            text = open(os.path.join(dirpath, fn), encoding="utf-8", errors="replace").read()
            pm = pkg_line.search(text)
            if not pm or pm.group(1) != package:
                continue
            for m in head.finditer(text):
                start = text.find("{", m.end())
                end = match_brace(text, start)
                recs.setdefault(m.group(1), (m.group(2).split(".")[-1], text[start + 1 : end]))
    return recs


def match_brace(text, start):
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
    return len(text)


def chain_of(recs, name):
    """Inheritance chain starting at name, cycle-safe (some records name themselves as parent)."""
    chain, seen = [], set()
    while name in recs and name not in seen:
        seen.add(name)
        chain.append(name)
        name = recs[name][0]
    return chain


def parse_fields(body):
    return {k: v.strip().strip('"') for k, v in re.findall(r"(\w+)\s*=\s*([^;]+);", top_level(body))}


def parse_gears(body):
    gm = re.search(r"gears\s*=\s*\[(.*?)\];", body, re.S)
    if not gm:
        return None
    return [
        {k: float(v.rstrip("f")) for k, v in re.findall(r"(\w+)\s*=\s*([-\d.]+)f?;", blk)}
        for blk in re.findall(r"\{(.*?)\}", gm.group(1), re.S)
    ]


def top_level(body):
    """Strip nested blocks so only the record's own scalar fields remain."""
    out, depth = [], 0
    for ch in body:
        if ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def resolve(recs, name, extra_body=None):
    """Walk inheritance; child values override parent. Returns (fields, gears).

    extra_body: an inline block body applied on top of the chain (for inline engines).
    """
    bodies = [recs[r][1] for r in reversed(chain_of(recs, name))]
    if extra_body is not None:
        bodies.append(extra_body)
    fields, gears = {}, None
    for body in bodies:
        fields.update(parse_fields(body))
        gears = parse_gears(body) or gears
    return fields, gears


def find_records(recs, tdb, root, block_key, probe, default_parent):
    """Every compiled record of one kind (engine or drive model).

    root:      base record name of that kind (e.g. "VehicleEngineData").
    block_key: vehicle field holding an inline block of that kind (e.g. "vehEngineData").
    probe:     field names that must exist on the compiled record (e.g. ["gears"]).
    Returns [(compiled_name, label, fields, gears, owner)] where owner is the vehicle
    record for inline blocks, else None. Each compiled record holds its own copy of
    every field, so each one must be overridden directly.
    """
    roots = root if isinstance(root, (list, tuple)) else [root]
    out = []
    for name in recs:
        chain = chain_of(recs, name)
        if any(r in chain[1:] or recs[chain[-1]][0] == r for r in roots):
            if all(tdb.has(f"Vehicle.{name}.{p}") for p in probe):
                f, g = resolve(recs, name)
                out.append((name, name, f, g, None))
    pat = re.compile(block_key + r"\s*=\s*\{")
    for name, (_parent, body) in recs.items():
        m = pat.search(body)
        if not m:
            continue
        start = m.end() - 1
        end = match_brace(body, start)
        tail = re.match(r"\s*:\s*([A-Za-z0-9_.]+)", body[end + 1 :])
        parent = tail.group(1).split(".")[-1] if tail else default_parent
        compiled = next(
            (f"{name}_inline{i}" for i in range(150)
             if all(tdb.has(f"Vehicle.{name}_inline{i}.{p}") for p in probe)),
            None,
        )
        if compiled is None:
            print(f"WARNING: no compiled {block_key} record found for {name}")
            continue
        f, g = resolve(recs, parent, body[start + 1 : end])
        out.append((compiled, f"{name} (inline : {parent})", f, g, name))
    return out


def find_engines(recs, tdb):
    return find_records(recs, tdb, "VehicleEngineData", "vehEngineData",
                        ["engineMaxTorque", "gears"], "VehicleEngineData_4_Default")


def find_drive_models(recs, tdb):
    out = []
    for key in ("vehDriveModelData", "bikeDriveModelData"):
        out += find_records(recs, tdb, ["VehicleDriveModelData", "BikeDriveModelData"],
                            key, ["total_mass", "chassis_mass"],
                            "VehicleDriveModelDataDefault_4w")
    seen, unique = set(), []
    for rec in out:
        if rec[0] not in seen:
            seen.add(rec[0])
            unique.append(rec)
    return unique


WHEEL_PROBE = ("maxBrakingTorque", "frictionMulLateral", "springStiffness")


def find_wheel_presets(recs, tdb):
    """Every compiled wheel preset (front/back) record, which is where brake torque lives.

    Named presets are found by inheritance; inline `frontPreset = {...}` / `backPreset = {...}`
    blocks are matched, in textual order, to the owning record's compiled `_inlineN`
    records that carry maxBrakingTorque.
    Returns [(compiled_name, label, fields)].
    """
    pat = re.compile(r"(frontPreset|backPreset)\s*=\s*\{")
    named, inline = [], []
    for name in recs:
        chain = chain_of(recs, name)
        if any("WheelDrivingPreset" in r or "WheelPreset" in r for r in chain + [recs[chain[-1]][0]]):
            named.append(name)
    for name, (_parent, body) in recs.items():
        blocks = []
        for m in pat.finditer(body):
            start = m.end() - 1
            end = match_brace(body, start)
            tail = re.match(r"\s*:\s*([A-Za-z0-9_.]+)", body[end + 1 :])
            if tail and "Dimension" not in tail.group(1):
                blocks.append((m.group(1), tail.group(1).split(".")[-1], body[start + 1 : end]))
        if blocks:
            inline.append((name, blocks))

    # Warm the lookup cache in parallel with every name the checks below will evaluate
    # first (all() short-circuits, so later probes only run where the first one matched).
    tdb.has_many([f"Vehicle.{n}.{WHEEL_PROBE[0]}" for n in named]
                 + [f"Vehicle.{n}_inline{i}.{WHEEL_PROBE[0]}" for n, _b in inline for i in range(200)])

    out = []
    for name in named:
        if all(tdb.has(f"Vehicle.{name}.{p}") for p in WHEEL_PROBE):
            out.append((name, name, resolve(recs, name)[0]))
    for name, blocks in inline:
        compiled = [f"{name}_inline{i}" for i in range(200)
                    if all(tdb.has(f"Vehicle.{name}_inline{i}.{p}") for p in WHEEL_PROBE)]
        if len(compiled) != len(blocks):
            print(f"WARNING: {name}: {len(blocks)} wheel preset blocks but "
                  f"{len(compiled)} compiled brake records; skipped")
            continue
        for c, (side, parent, blk) in zip(compiled, blocks):
            out.append((c, f"{name}.{side} (inline : {parent})", resolve(recs, parent, blk)[0]))
    return out


def vehicle_links(recs, key):
    """{vehicle record: compiled record its `key` field points to} following inheritance.

    Inline blocks are keyed by the record that declares them; string refs by preset name.
    """
    inline_owner_pat = re.compile(key + r"\s*=\s*(\{|\"([^\"]*)\")")
    own = {}
    for name, (_p, body) in recs.items():
        m = inline_owner_pat.search(body)
        if m:
            own[name] = ("inline", None) if m.group(1) == "{" else ("ref", (m.group(2) or "").split(".")[-1])
    links = {}
    for name in recs:
        for rec in chain_of(recs, name):
            if rec in own:
                kind, target = own[rec]
                links[name] = ("inline", rec) if kind == "inline" else ("ref", target)
                break
    return links


def num(fields, key, default):
    return float(fields.get(key, default).rstrip("f"))



def fmt(v):
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return s if "." in s else s + ".0"


def yaml_value(v):
    if isinstance(v, str):  # single quotes: YAML keeps backslashes in paths literally
        return "'" + v.replace("'", "''") + "'"
    if isinstance(v, dict):  # Vector3
        return "{ " + ", ".join(f"{k}: {fmt(x)}" for k, x in v.items()) + " }"
    return fmt(v)


def to_yaml(records, title):
    lines = [f"# EV Conversion - {title}. Generated by tools/build_ev.py, do not edit by hand", ""]
    for name, rec in records.items():
        lines.append(f"Vehicle.{name}:")
        for k, v in rec.items():
            if k == "gears":
                continue
            lines.append(f"  {k}: {yaml_value(v)}")
        if "gears" in rec:
            lines.append("  gears:")
            for g in rec["gears"]:
                lines.append("    - $type: VehicleGear")
                for k, v in g.items():
                    lines.append(f"      {k}: {fmt(v)}")
        lines.append("")
    return "\n".join(lines)


def to_json(records):
    out = {}
    for name, rec in records.items():
        r = {k: v for k, v in rec.items() if k != "gears"}
        if "gears" in rec:
            r["gears"] = [{"$type": "gamedataVehicleGear_Record", **g} for g in rec["gears"]]
        out[f"Vehicle.{name}"] = r
    return json.dumps(out, indent=4)


def vec3(fields, key):
    v = fields.get(key)
    if not v:
        return None
    parts = [float(p.strip().rstrip("f")) for p in v.strip("() ").split(",")]
    return dict(zip("xyz", parts)) if len(parts) == 3 else None


def convert_chassis(f, is_bike):
    """Battery pack: heavier, more rotational inertia, lower centre of mass (cars only)."""
    rec = {
        "total_mass": round(num(f, "total_mass", "1300") * CHASSIS["mass_factor"], 1),
        "chassis_mass": round(num(f, "chassis_mass", "1300") * CHASSIS["mass_factor"], 1),
    }
    if "handbrakeBrakingTorque" in f:
        rec["handbrakeBrakingTorque"] = round(num(f, "handbrakeBrakingTorque", "0") * CHASSIS["mass_factor"], 1)
    moi = vec3(f, "momentOfInertia")
    if moi:
        rec["momentOfInertia"] = {k: round(x * CHASSIS["mass_factor"], 1) for k, x in moi.items()}
    com = vec3(f, "center_of_mass_offset")
    if com and not is_bike:
        rec["center_of_mass_offset"] = {**com, "z": round(com["z"] - CHASSIS["com_drop_m"], 3)}
    return rec


def vanilla_bands(f, gears):
    decim = num(f, "finalGearTorqueDecimationScalor", "1.0")
    fwd = [dict(g) for g in gears[1:]]
    fwd[-1]["torqueMultiplier"] *= decim
    return fwd


def engine_time(f, gears, bands, torque, mass, shift_time, G):
    curve = f.get("gearCurvesPath", "small_torquey_na").split("\\")[-1].replace(".curveset", "")
    return accel.time_to(accel.TARGET_MS, bands, torque, mass, curve,
                         num(f, "minRPM", "800"), num(f, "maxRPM", "5000"), shift_time, G)


def main():
    import time
    from concurrent.futures import ProcessPoolExecutor
    import multiprocessing as mp

    from tweakdb import TweakDB

    sys.stdout.reconfigure(line_buffering=True)  # progress shows up when redirected to a log
    t0 = time.time()

    def step(msg):
        print(f"[{time.time() - t0:6.1f}s] {msg}")

    tdb = TweakDB()
    recs = load_records()
    found_engines = find_engines(recs, tdb)
    found_drives = find_drive_models(recs, tdb)
    step(f"found {len(found_engines)} engine and {len(found_drives)} drive-model records")
    engines = {c: (lbl, f, g) for c, lbl, f, g, _o in found_engines if g and len(g) >= 2}
    drives = {c: (lbl, f) for c, lbl, f, _g, _o in found_drives}
    inline_engine = {o: c for c, _l, _f, _g, o in found_engines if o}
    inline_drive = {o: c for c, _l, _f, _g, o in found_drives if o}

    def compiled(link, inline_map):
        if not link:
            return None
        kind, target = link
        return inline_map.get(target) if kind == "inline" else target

    # vehicle -> (engine record, drive record): records that end up with both are vehicles
    e_links = vehicle_links(recs, "vehEngineData")
    d_links = {**vehicle_links(recs, "bikeDriveModelData"), **vehicle_links(recs, "vehDriveModelData")}
    vehicles = {}
    for v in recs:
        e, d = compiled(e_links.get(v), inline_engine), compiled(d_links.get(v), inline_drive)
        if e in engines and d in drives:
            vehicles[v] = (e, d)

    # Global G from the reference car (player's starting Hella), vanilla
    ref_e, ref_d = vehicles["v_standard2_archer_hella_player"]
    _, rf, rg = engines[ref_e]
    ref_mass = num(drives[ref_d][1], "total_mass", "1300")
    ref_shift = num(rf, "gearChangeTime", "0.3")
    G = accel.solve(
        lambda g: engine_time(rf, rg, vanilla_bands(rf, rg), num(rf, "engineMaxTorque", "180"),
                              ref_mass, ref_shift, g),
        1e-3, 1e3, accel.REFERENCE_SECONDS)

    # Per engine: single gear + custom curve, fitted to vanilla 0-100 and top-end pull
    users = {}
    for v, (e, d) in vehicles.items():
        users.setdefault(e, []).append((v, d))
    designs, jobs = {}, {}
    workers = os.cpu_count() or 1
    step(f"fitting {len(engines)} engines on {workers} processes")
    with ProcessPoolExecutor(workers, mp_context=mp.get_context("spawn")) as pool:
        for e, (lbl, f, g) in engines.items():
            curve = f.get("gearCurvesPath", "small_torquey_na").split("\\")[-1].replace(".curveset", "")
            masses = sorted({num(drives[d][1], "total_mass", "1300") for _v, d in users.get(e, [])}) or [1500.0]
            jobs[e] = pool.submit(
                ev_single.design,
                curve, vanilla_bands(f, g), num(f, "engineMaxTorque", "180"),
                num(f, "minRPM", "800"), num(f, "maxRPM", "5000"), num(f, "gearChangeTime", "0.3"),
                masses, CHASSIS["mass_factor"],
                EV["shift_time"] if EV["shift_time"] is not None else num(f, "gearChangeTime", "0.3"),
                G, rpm_cap=SOUND["rpm_cap"], launch_speed=EV["launch_gear_speed"])
        for e, job in jobs.items():  # collected in submission order, so output order is unchanged
            designs[e] = job.result()
    step("engines fitted")

    # One curve file per distinct base-speed fraction (rounded), shared between engines
    curve_files = {}
    engine_recs = {}
    cap_tag = f"c{round(SOUND['rpm_cap'] * 100):03d}"
    for e, (lbl, f, g) in engines.items():
        dz = designs[e]
        key = round(dz["xb"] / CURVE_STEP) * CURVE_STEP
        depot = f"{CURVE_DIR}\\ev_{cap_tag}_xb{round(key * 1000):04d}.curveset"
        curve_files[depot] = ev_single.ev_curve(key, SOUND["rpm_cap"])
        engine_recs[e] = {
            "engineMaxTorque": round(num(f, "engineMaxTorque", "180") * dz["k"], 2),
            "gearCurvesPath": depot,
            **({"gearChangeTime": EV["shift_time"], "gearChangeCooldown": EV["shift_time"]}
               if EV["shift_time"] is not None else {}),
            "finalGearTorqueDecimationScalor": 1.0,
            "flyWheelMomentOfInertia": round(num(f, "flyWheelMomentOfInertia", "0.3") * EV["flywheel_scale"], 4),
            "resistanceTorque": round(num(f, "resistanceTorque", "100") * EV["resistance_scale"], 2),
            "gears": [dict(g[0])] + [{k: float(v) for k, v in band.items()} for band in dz["bands"]],
        }
    bike_drives = {d for v, (e, d) in vehicles.items() if "bike" in v or "_2w" in d}
    chassis_recs = {d: convert_chassis(f, d in bike_drives or "2w" in d) for d, (lbl, f) in drives.items()}
    # Brakes: same braking torque per kg as vanilla, so stopping distances are unchanged
    wheel_presets = find_wheel_presets(recs, tdb)
    tdb.save()
    step(f"found {len(wheel_presets)} wheel preset records")
    for c, _lbl, f in wheel_presets:
        if "maxBrakingTorque" in f:
            chassis_recs[c] = {"maxBrakingTorque": round(num(f, "maxBrakingTorque", "0") * CHASSIS["mass_factor"], 1)}
    n_brakes = sum(1 for r in chassis_recs.values() if "maxBrakingTorque" in r)

    out = os.path.join(ROOT, "build", MOD_NAME)
    shutil.rmtree(out, ignore_errors=True)  # never ship stale files from an earlier build
    tw = os.path.join(out, "r6", "tweaks")
    os.makedirs(tw, exist_ok=True)
    for stem, recs_out, title in [(MOD_NAME, engine_recs, "engines"),
                                  (f"{MOD_NAME}_Chassis", chassis_recs, "chassis")]:
        open(os.path.join(tw, f"{stem}.yaml"), "w").write(to_yaml(recs_out, title))
        open(os.path.join(tw, f"{stem}.json"), "w").write(to_json(recs_out) + "\n")
    about = {"ModInfo": {"ModName": MOD_NAME, "ModID": -1}}
    open(os.path.join(out, "about.json"), "w").write(json.dumps(about, indent="\t") + "\n")

    # Torque curves: cooked CurveSet files packed into one archive
    os.makedirs(os.path.join(out, "archive"), exist_ok=True)
    packed = []
    for depot, pts in sorted(curve_files.items()):
        raw = curvewriter.build(pts, platform=PLATFORM)
        packed.append((depot, raw, len(raw)))
    hybrid_audio = None
    if SOUND["hybrid"]:
        vanilla_audio = rdar.extract(audio_hybrid.GAME_ARCHIVE, audio_hybrid.DEPOT_PATH)
        hybrid_audio, audio_report = audio_hybrid.build_hybrid(vanilla_audio)
        audio_hybrid.verify(hybrid_audio, audio_report, vanilla_audio)
        packed.append((audio_hybrid.DEPOT_PATH, hybrid_audio, len(hybrid_audio)))
    arc_path = os.path.join(out, "archive", f"{MOD_NAME}.archive")
    rdar.write_archive(arc_path, packed)
    step(f"archive written ({len(packed)} files)")
    # read every file back through the archive reader + curve decoder
    idx = rdar.read_index(arc_path)
    for depot, pts in curve_files.items():
        back = curveset.find_curve(rdar.extract(arc_path, depot, idx))[1]
        assert len(back) == len(pts) and all(abs(a - c) < 1e-5 and abs(b - d) < 1e-5
                                             for (a, b), (c, d) in zip(back, pts)), depot
    if hybrid_audio is not None:
        assert rdar.extract(arc_path, audio_hybrid.DEPOT_PATH, idx) == hybrid_audio

    with open(os.path.join(ROOT, "build", "engine_report.txt"), "w") as rpt:
        rpt.write(f"G={G:.5f}  target={accel.TARGET_KMH_SPEEDO:.0f} km/h speedometer "
                  f"({accel.TARGET_MS:.2f} m/s)  mass x{CHASSIS['mass_factor']}\n\n")
        for e, (lbl, f, g) in sorted(engines.items()):
            dz = designs[e]
            rpt.write(f"{lbl}\n  -> Vehicle.{e}  torque x{dz['k']:.3f}  base speed {dz['xb']:.0%} of "
                      f"{dz['vmax']:.1f} m/s  curve {engine_recs[e]['gearCurvesPath'].split(chr(92))[-1]}\n")
            for m, tv, te, tvh, teh in dz["timing"]:
                rpt.write(f"     mass {m:6.0f}: 0-100 vanilla {tv:5.2f}s EV {te:5.2f}s | "
                          f"0-80% top vanilla {tvh:5.2f}s EV {teh:5.2f}s\n")
    ks = sorted(d["k"] for d in designs.values())
    xbs = sorted(d["xb"] for d in designs.values())
    errs = [abs(r[2] - r[1]) / r[1] for d in designs.values() for r in d["timing"]]
    errs_hi = [(r[4] - r[3]) / r[3] for d in designs.values() for r in d["timing"]]
    print(f"{len(engine_recs)} engines, {len(curve_files)} curve files, {len(drives)} drive models, "
          f"{n_brakes} brake presets, {len(vehicles)} vehicles; G={G:.4f}")
    print(f"torque x: min {ks[0]:.3f} median {ks[len(ks)//2]:.3f} max {ks[-1]:.3f}; "
          f"base speed: min {xbs[0]:.0%} median {xbs[len(xbs)//2]:.0%} max {xbs[-1]:.0%}; "
          f"0-100 error: max {max(errs):.1%}, within 2%: {sum(e <= 0.02 for e in errs)}/{len(errs)}; "
          f"0-80% top: EV slower by median {sorted(errs_hi)[len(errs_hi)//2]:+.0%}, "
          f"range {min(errs_hi):+.0%} to {max(errs_hi):+.0%}")
    for v in ["v_standard2_archer_hella_player", "v_sport1_quadra_sport_r7_player"]:
        e, d = vehicles[v]
        dz = designs[e]
        m = num(drives[d][1], "total_mass", "1300")
        _m, tv, te, tvh, teh = next(r for r in dz["timing"] if r[0] == m)
        print(f"{v}: torque x{dz['k']:.3f}, base speed {dz["xb"]:.0%}, 0-100 {tv:.2f}s -> {te:.2f}s, 0-80% top {tvh:.2f}s -> {teh:.2f}s")
    print("wrote", out)


if __name__ == "__main__":
    main()
