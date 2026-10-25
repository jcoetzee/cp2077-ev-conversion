"""How far is the current build from vanilla at other target speeds?

Re-runs the build's engine fitting (same inputs as build_ev.main), then reports the modelled
EV vs vanilla time from 0 to each given speed (game units), per engine and mass.
Usage: python3 tools/check_target.py 13.89 19.5 22.0
"""
import multiprocessing as mp
import os
import sys
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import accel  # noqa: E402
import build_ev as b  # noqa: E402
import ev_single  # noqa: E402
from tweakdb import TweakDB  # noqa: E402


def job(args):
    curve, vb, T, mn, mx, vshift, masses, G, targets = args
    shift = b.EV["shift_time"] if b.EV["shift_time"] is not None else vshift
    dz = ev_single.design(curve, vb, T, mn, mx, vshift, masses, b.CHASSIS["mass_factor"], shift, G,
                          rpm_cap=b.SOUND["rpm_cap"], launch_speed=b.EV["launch_gear_speed"])
    pts = ev_single.ev_curve(dz["xb"], b.SOUND["rpm_cap"])
    out = []
    for m in masses:
        row = []
        for v in targets:
            if v >= vb[-1]["maxSpeed"]:
                row.append(None)
                continue
            tv = accel.time_to(v, vb, T, m, curve, mn, mx, vshift, G)
            te = accel.time_to(v, dz["bands"], T * dz["k"], m * b.CHASSIS["mass_factor"], pts, mn, mx, shift, G)
            row.append((te - tv) / tv)
        out.append(row)
    return out


def main():
    targets = [float(x) for x in sys.argv[1:]] or [accel.TARGET_MS]
    tdb = TweakDB()
    recs = b.load_records()
    fe, fd = b.find_engines(recs, tdb), b.find_drive_models(recs, tdb)
    engines = {c: (l, f, g) for c, l, f, g, _o in fe if g and len(g) >= 2}
    drives = {c: (l, f) for c, l, f, _g, _o in fd}
    ie = {o: c for c, *_r, o in fe if o}
    idr = {o: c for c, *_r, o in fd if o}
    el = b.vehicle_links(recs, "vehEngineData")
    dl = {**b.vehicle_links(recs, "bikeDriveModelData"), **b.vehicle_links(recs, "vehDriveModelData")}

    def comp(link, m):
        return None if not link else (m.get(link[1]) if link[0] == "inline" else link[1])

    users = {}
    for v in recs:
        e, d = comp(el.get(v), ie), comp(dl.get(v), idr)
        if e in engines and d in drives:
            users.setdefault(e, set()).add(b.num(drives[d][1], "total_mass", "1300"))
    ref = "v_standard2_archer_hella_getto_inline5"
    _l, rf, rg = engines[ref]
    G = accel.solve(lambda g: b.engine_time(rf, rg, b.vanilla_bands(rf, rg), b.num(rf, "engineMaxTorque", "180"),
                                            1800.0, b.num(rf, "gearChangeTime", "0.3"), g),
                    1e-3, 1e3, accel.REFERENCE_SECONDS)
    args = []
    for e, (_l, f, g) in engines.items():
        curve = f.get("gearCurvesPath", "small_torquey_na").split("\\")[-1].replace(".curveset", "")
        args.append((curve, b.vanilla_bands(f, g), b.num(f, "engineMaxTorque", "180"), b.num(f, "minRPM", "800"),
                     b.num(f, "maxRPM", "5000"), b.num(f, "gearChangeTime", "0.3"),
                     sorted(users.get(e, {1500.0})), G, targets))
    with ProcessPoolExecutor(os.cpu_count(), mp_context=mp.get_context("spawn")) as pool:
        results = list(pool.map(job, args))
    for j, v in enumerate(targets):
        errs = [row[j] for res in results for row in res if row[j] is not None]
        errs.sort()
        within = sum(abs(e) <= 0.02 for e in errs)
        print(f"0 -> {v:5.2f} units: EV vs vanilla median {errs[len(errs)//2]:+.1%}, "
              f"range {errs[0]:+.1%} to {errs[-1]:+.1%}, within 2%: {within}/{len(errs)}")


if __name__ == "__main__":
    main()
