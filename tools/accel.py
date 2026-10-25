"""Straight-line acceleration model used to hold 0-100 km/h constant through the conversion.

Model (per vehicle):
    accel = G * engineMaxTorque * curve(rpm) * torqueMultiplier(band) / mass
  * band selection: start in the first forward band, upshift when speed reaches the
    band's maxSpeed; vanilla loses drive for gearChangeTime on every shift, EV never.
  * rpm is linear in speed within a band; curve() is the engine's torque curve over the
    normalised range [minRPM, maxRPM].
  * no drag or rolling resistance: below speedo-100 km/h both versions see the same
    small losses, and they are not modelled by the game data we can read.
  * G is one global constant that converts the game's torque units to acceleration.
    Its only effect on the result is how much a fixed-length shift gap costs, so it is
    set from one reference time and refined from in-game stopwatch measurements.

Speeds in the gear tables are in game units. The HUD shows mph = speed x m(speed), where m
is the vanilla curve 'speed_to_multiplier' (vehicle_ui curve set, see car_hud.script),
interpolated linearly here. km/h shown = mph shown x 1.60934. So "100 km/h on the
speedometer" is about 21.1 game units, the same for every vehicle.
"""
import glob
import os

import curveset

HERE = os.path.dirname(os.path.abspath(__file__))
CURVE_DIR = os.path.join(os.path.dirname(HERE), "extracted", "curves")
SPEEDO_CURVE_FILE = os.path.join(CURVE_DIR, "vehicle_ui_speed_to_multiplier.bin")


def shown_mph(speed, pts=None):
    """Speedometer reading (mph) for a speed in game units."""
    pts = pts or _speedo_points()
    if speed >= pts[-1][0]:
        return speed * pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= speed <= x1:
            return speed * (y0 + (y1 - y0) * (speed - x0) / (x1 - x0))
    return speed * pts[0][1]


def units_for_shown_kmh(kmh):
    """Game-unit speed at which the speedometer shows `kmh` (shown_mph is increasing)."""
    target_mph = kmh / 1.60934
    lo, hi = 0.0, 200.0
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if shown_mph(mid) < target_mph else (lo, mid)
    return (lo + hi) / 2


def _speedo_points():
    if not _SPEEDO:
        _SPEEDO.extend(curveset.read_curve(open(SPEEDO_CURVE_FILE, "rb").read(), "speed_to_multiplier"))
    return _SPEEDO


_SPEEDO = []
TARGET_KMH_SPEEDO = 100.0
TARGET_MS = units_for_shown_kmh(TARGET_KMH_SPEEDO)  # name kept for callers: game units

# Fitted by tools/calibrate.py to in-game stopwatch times (0 -> 62 mph shown, full restart,
# 3 runs each):
#   Archer Hella EC-D I360        vanilla 8.69 8.46 8.95 (8.70)   EV build 04e9af7 7.08 6.97 6.94 (7.00)
#   Quadra Sport R-7 "Vigilante"  vanilla 4.34 4.29 4.34 (4.32)   EV build 04e9af7 4.22 4.13 4.22 (4.19)
# Three constants are fitted to the first three of those four means; the fourth (R-7 EV) is
# the check: the model gives 4.20 s.
#   G          torque units -> acceleration
#   A_MAX      tyre-grip limit on acceleration at vanilla mass; grip is a fixed force, so a
#              vehicle carrying mass_factor more weight is limited to A_MAX / mass_factor
#   INERTIA    engine inertia load per unit of flyWheelMomentOfInertia (see time_to)
G = 30.078
A_MAX = 5.543       # game units/s^2
INERTIA = 152.08

_CURVES = {}


def curve_points(name):
    if not _CURVES:
        for path in glob.glob(os.path.join(CURVE_DIR, "*.curveset")):
            key = os.path.basename(path)[: -len(".curveset")]
            _CURVES[key] = curveset.find_curve(open(path, "rb").read())[1]
    return _CURVES[name]


def interp(pts, x):
    x = min(max(x, 0.0), 1.0)
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0) if x1 > x0 else y1
    return pts[-1][1]


def time_to(target, bands, torque, mass, curve, min_rpm, max_rpm, shift_time, G, dt=0.002,
            a_max=None, inertia=0.0, upshift=1.0):
    """Seconds from standstill to `target` m/s. bands: forward gear dicts.
    curve: curve name, or a list of (x, y) points. a_max: optional tyre-grip limit on
    acceleration (game units/s^2); grip scales with weight, so it does not depend on mass.
    inertia: drivetrain (flywheel) inertia coefficient. Spinning the engine up adds
    inertia x (dRPM/dspeed of the band / 100)^2 to the mass being accelerated, so short
    gears (steep RPM rise) carry a large hidden load and the EV's long gear carries little.
    upshift: where in the overlap with the next gear the gearbox changes up
    (1.0 = at this gear's maxSpeed, 0.0 = at the next gear's minSpeed)."""
    if a_max is None:
        a_max = A_MAX
    pts = curve if isinstance(curve, list) else curve_points(curve)
    v, t, idx, gap = 0.0, 0.0, 0, 0.0
    while v < target:
        if t > 120:
            return float("inf")
        b = bands[idx]
        if idx + 1 < len(bands):
            nxt = bands[idx + 1]["minSpeed"]
            shift_at = nxt + upshift * (b["maxSpeed"] - nxt) if nxt < b["maxSpeed"] else b["maxSpeed"]
        if idx + 1 < len(bands) and v >= shift_at:
            idx += 1
            gap = shift_time
            continue
        if gap > 0:
            gap -= dt
            t += dt
            continue
        span = max(b["maxSpeed"] - b["minSpeed"], 1e-6)
        frac = min(max((v - b["minSpeed"]) / span, 0.0), 1.0)
        rpm = b["minEngineRPM"] + frac * (b["maxEngineRPM"] - b["minEngineRPM"])
        x = (rpm - min_rpm) / max(max_rpm - min_rpm, 1.0)
        slope = (b["maxEngineRPM"] - b["minEngineRPM"]) / span / 100.0
        m_eff = mass + inertia * slope * slope
        v += min(G * torque * interp(pts, x) * b["torqueMultiplier"] / m_eff, a_max) * dt
        t += dt
    return t


def solve(fn, lo, hi, target, iters=50):
    """Bisection for fn(x) == target where fn is decreasing in x."""
    for _ in range(iters):
        mid = (lo + hi) / 2
        if fn(mid) > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2
