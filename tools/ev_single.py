"""Single-gear EV engine design.

One forward gear spans 0 -> vanilla top speed, with RPM rising linearly from minRPM to
maxRPM, so the torque curve (defined over normalised RPM) becomes force against speed:

    y(x) = 1          for x <= xb      constant torque up to base speed
    y(x) = xb / x     for x >  xb      constant power above it
    x = speed / top speed

Two numbers per engine are fitted against vanilla:
  k  : engineMaxTorque multiplier, chosen so 0-100 km/h (speedometer) matches vanilla
       at the EV's higher mass.
  xb : base speed fraction, chosen so acceleration just below top speed matches
       vanilla (same top-end pull, so the top of the speed range keeps its character).
"""
import accel

N_POINTS = 19


def ev_curve(xb, cap=1.0):
    """EV torque curve over normalised RPM. With cap < 1 the gear only uses RPM range
    [0, cap], so the speed shape is squeezed into that span and held flat beyond it."""
    xb = min(max(xb, 0.02), 1.0)
    n = N_POINTS - (1 if cap < 0.999 else 0)
    if xb >= 0.999:
        pts = [(i / (n - 1), 1.0) for i in range(n)]
    else:
        tail = n - 2
        xs = [xb + (1.0 - xb) * ((i + 1) / tail) ** 1.3 for i in range(tail)]
        pts = [(0.0, 1.0), (xb, 1.0)] + [(x, xb / x) for x in xs]
    if cap < 0.999:
        pts = [(x * cap, y) for x, y in pts] + [(1.0, pts[-1][1])]
    return pts


def vanilla_force_factor(f_curve_pts, bands, min_rpm, max_rpm, v):
    """curve(rpm) * torqueMultiplier in the band an accelerating car is in at speed v."""
    band = next((b for b in bands if v < b["maxSpeed"]), bands[-1])
    span = max(band["maxSpeed"] - band["minSpeed"], 1e-6)
    frac = min(max((v - band["minSpeed"]) / span, 0.0), 1.0)
    rpm = band["minEngineRPM"] + frac * (band["maxEngineRPM"] - band["minEngineRPM"])
    x = (rpm - min_rpm) / max(max_rpm - min_rpm, 1.0)
    return accel.interp(f_curve_pts, x) * band["torqueMultiplier"]


def design(curve_name, vanilla_bands, T, min_rpm, max_rpm, vanilla_shift, masses,
           mass_factor, ev_shift, G, xb_min=0.15, k_max=3.0, high_frac=0.8, rpm_cap=1.0):
    """Returns dict(k, xb, curve, band, timing=[(mass, t_van, t_ev, t_van_hi, t_ev_hi)]).

    Constraints, in priority order:
      1. 0-100 km/h (speedometer) equals vanilla: solved exactly for k.
      2. 0 -> high_frac * top speed equals vanilla: best effort via xb in [xb_min, 1].
    """
    vmax = vanilla_bands[-1]["maxSpeed"]
    band = [{"minSpeed": 0.0, "maxSpeed": vmax, "minEngineRPM": min_rpm,
             "maxEngineRPM": round(min_rpm + rpm_cap * (max_rpm - min_rpm)), "torqueMultiplier": 1.0}]
    v_hi = high_frac * vmax
    m_ref = masses[len(masses) // 2]

    def t_van(m, target):
        return accel.time_to(target, vanilla_bands, T, m, curve_name, min_rpm, max_rpm,
                             vanilla_shift, G)

    def t_ev(k, xb, m, target):
        return accel.time_to(target, band, T * k, m * mass_factor, ev_curve(xb, rpm_cap),
                             min_rpm, max_rpm, ev_shift, G)

    def k_for(xb, m):
        return accel.solve(lambda kk: t_ev(kk, xb, m, accel.TARGET_MS), 0.1, k_max, t_van(m, accel.TARGET_MS))

    goal_hi = t_van(m_ref, v_hi)
    # t_ev_hi decreases as xb rises (more power above base speed); bisect on xb
    lo, hi = xb_min, 1.0
    if t_ev(k_for(lo, m_ref), lo, m_ref, v_hi) <= goal_hi:
        xb = lo
    elif t_ev(k_for(hi, m_ref), hi, m_ref, v_hi) >= goal_hi:
        xb = hi
    else:
        for _ in range(25):
            mid = (lo + hi) / 2
            if t_ev(k_for(mid, m_ref), mid, m_ref, v_hi) > goal_hi:
                lo = mid
            else:
                hi = mid
        xb = (lo + hi) / 2
    ks = sorted(k_for(xb, m) for m in masses)
    k = ks[len(ks) // 2]
    timing = [(m, t_van(m, accel.TARGET_MS), t_ev(k, xb, m, accel.TARGET_MS),
               t_van(m, v_hi), t_ev(k, xb, m, v_hi)) for m in masses]
    return dict(k=k, xb=xb, curve=ev_curve(xb, rpm_cap), band=band[0], vmax=vmax, timing=timing)
