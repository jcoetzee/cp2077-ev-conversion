"""Vehicles that stay vanilla internal-combustion (ICE): Nomad vehicles and the Porsche 911.

Lore (in-game texts): Night City's cars run on CHOOH2 combustion; Nomad rigs ("give it a
little CHOOH", "leaking CHOOH2") live off-grid in the Badlands, and Johnny's 911 Turbo (930)
is a period classic. The mod converts the city to electric and leaves these as they are.

An excluded vehicle keeps everything vanilla together: engine, drive model (mass, brakes),
wheel presets (brake torque, grip) and sound profiles. A record shared between an excluded
and a converted vehicle cannot be both, so shared records are reported (and fail the build).

Usage: python3 tools/ice_exclusions.py    (prints the exclusion set and any conflicts)
"""
import os

import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Base models that stay ICE. Every vehicle using one of their engine records (scripted,
# quest and police-heat variants of the same car) stays ICE with them. The Thorton Galena
# "bobas" is the "Rattler", the Nomad lifepath's starting car.
ICE_BASE_MODELS = [
    "v_sport2_porsche_911turbo",           # Porsche 911 Turbo (930), Johnny's car
    "v_standard2_archer_quartz_nomad",     # Archer Quartz "Bandit"
    "v_standard2_thorton_galena_nomad",    # Thorton Galena "Locust" / "Gecko"
    "v_standard2_thorton_galena_bobas",    # Thorton Galena "Rattler"
    "v_standard25_thorton_colby_nomad",    # Thorton Colby "Little Mule" / "Vulture"
    "v_sport2_mizutani_shion_nomad",       # Mizutani Shion "Samum"
    "v_sport2_quadra_type66_nomad",        # Quadra Type-66 nomad
    "v_standard3_thorton_mackinaw_nomad",  # Thorton Mackinaw nomad
]
# Not excluded: the Brennan Apollo nomad bike uses the same engine, chassis and sound records
# as every other Apollo, so it cannot differ from them without new records.


def _wheel_presets_by_owner(b, recs, tdb):
    """{drive model record (compiled name) or inline owner: [compiled wheel preset names]}."""
    out = {}
    for compiled, label, _f in b.find_wheel_presets(recs, tdb):
        owner = label.split(".")[0].split(" ")[0] if "inline" in label else None
        if owner:
            out.setdefault(owner, []).append(compiled)
    return out


def analyse(b, recs, tdb, vehicles, drives):
    """vehicles: {vehicle: (engine record, drive record)} as built by build_ev.main.

    Returns dict with excluded vehicles and the engine / drive / wheel / sound records to
    keep vanilla, plus conflicts (records also used by converted vehicles)."""
    missing = [m for m in ICE_BASE_MODELS if m not in vehicles]
    if missing:
        raise ValueError(f"ICE base models not found: {missing}")
    seed_pairs = {vehicles[m] for m in ICE_BASE_MODELS}
    bases = set(ICE_BASE_MODELS)
    # ICE: the base models, vehicles inheriting from them, and scripted/quest/heat variants
    # that use exactly the same engine and drive model as a base model.
    ice = {v for v, ed in vehicles.items() if ed in seed_pairs or bases & set(b.chain_of(recs, v))}
    ev = set(vehicles) - ice

    def users(index):
        res = {}
        for v, (e, d) in vehicles.items():
            res.setdefault(index(e, d), set()).add(v)
        return res

    eng_users = users(lambda e, d: e)
    drv_users = users(lambda e, d: d)
    engines = {vehicles[v][0] for v in ice}
    drive_models = {vehicles[v][1] for v in ice}

    # wheel presets hang off a drive model: inline ones are named <owner>_inlineN, where the
    # owner is the record declaring the drive model; named ones are referenced by name
    inline_owner = {d: d.rsplit("_inline", 1)[0] if "_inline" in d else d for d in drives}
    presets_by_owner = _wheel_presets_by_owner(b, recs, tdb)
    named_presets = {}
    for d in drives:
        f = drives[d][1]
        for side in ("frontPreset", "backPreset"):
            p = f.get(side)
            if p and not p.startswith("{"):
                named_presets.setdefault(d, set()).add(p.split(".")[-1])

    def presets_of(d):
        return set(presets_by_owner.get(inline_owner[d], [])) | named_presets.get(d, set())

    wheel_users = {}
    for v, (_e, d) in vehicles.items():
        for p in presets_of(d):
            wheel_users.setdefault(p, set()).add(v)
    wheels = set().union(*(presets_of(d) for d in drive_models)) if drive_models else set()

    sounds, sound_users = set(), {}
    for v in vehicles:
        f, _g = b.resolve(recs, v)
        for k in ("player_audio_resource", "traffic_audio_resource"):
            s = f.get(k)
            if s:
                sound_users.setdefault(s, set()).add(v)
                if v in ice:
                    sounds.add(s)

    conflicts, engine_splits = [], {}
    for kind, keep, use in (("engine", engines, eng_users), ("drive model", drive_models, drv_users),
                            ("wheel preset", wheels, wheel_users), ("sound profile", sounds, sound_users)):
        for r in sorted(keep):
            shared = sorted(use.get(r, set()) & ev)
            if not shared:
                continue
            if kind == "engine":
                # resolvable: converted users get their own copy of the engine record
                engine_splits[r] = shared
            else:
                conflicts.append((kind, r, shared))
    return dict(vehicles=sorted(ice), engines=engines, drive_models=drive_models,
                wheels=wheels, sounds=sounds, conflicts=conflicts, engine_splits=engine_splits)


def main():
    import build_ev as b
    from tweakdb import TweakDB

    tdb = TweakDB()
    recs = b.load_records()
    vehicles, drives = b.vehicle_map(recs, tdb)
    a = analyse(b, recs, tdb, vehicles, drives)
    print(f"{len(a['vehicles'])} ICE vehicles: {', '.join(a['vehicles'])}")
    for k in ("engines", "drive_models", "wheels", "sounds"):
        print(f"  keep vanilla {k}: {len(a[k])}  {sorted(a[k])}")
    print(f"conflicts (also used by converted vehicles): {len(a['conflicts'])}")
    for kind, r, shared in a["conflicts"]:
        print(f"  {kind} {r}: shared with {shared[:6]}{' ...' if len(shared) > 6 else ''}")
    print(f"engine records split (converted users get their own copy): {len(a['engine_splits'])}")
    for r, shared in a["engine_splits"].items():
        print(f"  {r}: {shared}")


if __name__ == "__main__":
    main()
