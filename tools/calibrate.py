"""Fit the acceleration model's constants (accel.G, A_MAX, INERTIA) to in-game stopwatch times.

Measurements: 0 -> 62 mph shown (100 km/h), full throttle from standstill, full game restart,
three runs each. The EV side is simulated from the build that was driven (engine records and
curves read from the saved copy of the build that was driven, build/measured_<commit>).

Three constants are fitted to three measured means; any further measurement is an
independent check, reported as an error.
  G        from vehicle 0 vanilla time
  A_MAX    from vehicle 1 vanilla time (grip-limited car)
  INERTIA  from vehicle 0 EV time
Print the fitted values, then copy them into accel.py.

Model findings (Oct 2026, macOS 2.5): a fixed shift gap plus constant G could not explain
both cars. What did: an engine-inertia load that grows with each gear's RPM rise per unit of
speed (short gears are expensive), and tyre grip as a fixed force (a heavier car grips less
per kg). Longer shift gaps (gearChangeTime + cooldown, or scaled) did not fit.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import accel  # noqa: E402
import build_ev as b  # noqa: E402
import curveset  # noqa: E402
import rdar  # noqa: E402
from tweakdb import TweakDB  # noqa: E402

# (engine record, drive model record, vanilla times, EV times)
MEASUREMENTS = [
    ("v_standard2_archer_hella_getto_inline5", "VehicleDriveModelData_Archer_Players",
     [8.69, 8.46, 8.95], [7.08, 6.97, 6.94]),
    ("v_sport1_quadra_sport_r7_rocket_inline3", "VehicleDriveModelData_SportR7_Rocket",
     [4.34, 4.29, 4.34], [4.22, 4.13, 4.22]),
]
# The EV times above were measured on this build (gear/curve/torque values come from it).
MEASURED_BUILD = "04e9af7"
# Validation: EV times on the build fitted from the data above (not used for fitting).
# Target = vanilla times above. Hella 8.59 s (-1.3%), Sport R-7 4.42 s (+2.3%).
VALIDATION = {
    "build": "4415aa3",
    "v_standard2_archer_hella_getto_inline5": [8.72, 8.49, 8.55],
    "v_sport1_quadra_sport_r7_rocket_inline3": [4.46, 4.39, 4.41],
}
# Copy of that build kept for re-fitting (build/EVConversion is overwritten by every build).
BUILD = os.path.join(b.ROOT, "build", f"measured_{MEASURED_BUILD}")


def mean(xs):
    return sum(xs) / len(xs)


def load():
    recs = b.load_records()
    tdb = TweakDB()
    eng = {c: (f, g) for c, _l, f, g, _o in b.find_engines(recs, tdb)}
    drv = {c: f for c, _l, f, _g, _o in b.find_drive_models(recs, tdb)}
    ev = json.load(open(os.path.join(BUILD, "r6", "tweaks", "EVConversion.json")))
    arc = os.path.join(BUILD, "archive", "EVConversion.archive")
    idx = rdar.read_index(arc)
    cars = []
    for e, d, tv, te in MEASUREMENTS:
        f, g = eng[e]
        rec = ev[f"Vehicle.{e}"]
        cars.append(dict(
            name=e, f=f, g=g, mass=b.num(drv[d], "total_mass", "1300"),
            van_curve=f["gearCurvesPath"].split("\\")[-1][:-9],
            ev_rec=rec, ev_pts=curveset.read_curve(rdar.extract(arc, rec["gearCurvesPath"], idx)),
            t_van=mean(tv), t_ev=mean(te)))
    return cars


def times(car, G, a_max, inertia):
    """(vanilla, EV) seconds to 100 km/h shown for one measured car."""
    f, g = car["f"], car["g"]
    mn, mx = b.num(f, "minRPM", "800"), b.num(f, "maxRPM", "5000")
    fw = b.num(f, "flyWheelMomentOfInertia", "0.3")
    tv = accel.time_to(accel.TARGET_MS, b.vanilla_bands(f, g), b.num(f, "engineMaxTorque", "180"),
                       car["mass"], car["van_curve"], mn, mx, b.num(f, "gearChangeTime", "0.3"), G,
                       a_max=a_max, inertia=inertia * fw)
    r = car["ev_rec"]
    mf = b.CHASSIS["mass_factor"]
    te = accel.time_to(accel.TARGET_MS, r["gears"][1:], r["engineMaxTorque"], car["mass"] * mf,
                       car["ev_pts"], mn, mx, r.get("gearChangeTime", b.num(f, "gearChangeTime", "0.3")),
                       G, a_max=a_max / mf, inertia=inertia * r.get("flyWheelMomentOfInertia", fw))
    return tv, te


def bisect(fn, lo, hi, target, increasing, iters=40):
    for _ in range(iters):
        mid = (lo + hi) / 2
        if (fn(mid) < target) == increasing:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def fit(cars):
    ref, grip = cars[0], cars[1]

    def g_and_a(inertia):
        G, a = 25.0, 5.5
        for _ in range(10):
            G = bisect(lambda x: times(ref, x, a, inertia)[0], 1e-2, 1e4, ref["t_van"], increasing=False)
            a = bisect(lambda x: times(grip, G, x, inertia)[0], 0.3, 200.0, grip["t_van"], increasing=False)
        return G, a

    def ev_ref(inertia):
        G, a = g_and_a(inertia)
        return times(ref, G, a, inertia)[1]

    inertia = bisect(ev_ref, 0.0, 5000.0, ref["t_ev"], increasing=False, iters=30)
    G, a = g_and_a(inertia)
    return G, a, inertia


def main():
    cars = load()
    G, a, inertia = fit(cars)
    print(f"EV times measured on build {MEASURED_BUILD}; simulating {BUILD}")
    print(f"G = {G:.3f}\nA_MAX = {a:.3f}\nINERTIA = {inertia:.2f}")
    for car in cars:
        tv, te = times(car, G, a, inertia)
        print(f"  {car['name']:42} vanilla {tv:5.2f} (measured {car['t_van']:.2f})"
              f"  EV {te:5.2f} (measured {car['t_ev']:.2f}, error {te - car['t_ev']:+.2f} s)")


if __name__ == "__main__":
    main()
