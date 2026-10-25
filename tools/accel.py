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

Speeds in the gear tables are in m/s. The in-game speedometer reads about twice the
real speed (community research), so "100 km/h on the speedometer" is 50 km/h real.
"""
import glob
import os

import curveset

HERE = os.path.dirname(os.path.abspath(__file__))
CURVE_DIR = os.path.join(os.path.dirname(HERE), "extracted", "curves")

SPEEDO_FACTOR = 2.0                      # speedometer reading / real speed
TARGET_KMH_SPEEDO = 100.0
TARGET_MS = TARGET_KMH_SPEEDO / SPEEDO_FACTOR / 3.6

# Reference used to fix G until we have in-game measurements: the player's starting
# Hella reaching 100 km/h on the speedometer in this many seconds (vanilla).
REFERENCE_SECONDS = 4.0

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


def time_to(target, bands, torque, mass, curve, min_rpm, max_rpm, shift_time, G, dt=0.002):
    """Seconds from standstill to `target` m/s. bands: forward gear dicts.
    curve: curve name, or a list of (x, y) points."""
    pts = curve if isinstance(curve, list) else curve_points(curve)
    v, t, idx, gap = 0.0, 0.0, 0, 0.0
    while v < target:
        if t > 120:
            return float("inf")
        b = bands[idx]
        if v >= b["maxSpeed"] and idx + 1 < len(bands):
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
        v += G * torque * interp(pts, x) * b["torqueMultiplier"] / mass * dt
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
