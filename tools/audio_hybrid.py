"""Hybrid vehicle sound profiles: each car/bike keeps its own sound profile, with only
the engine section replaced by a donor's (default: the Basilisk hover tank).

In base\\sound\\metadata\\cooked_metadata.audio_metadata, every audioVehicleMetadata
export has the properties
  generalData     brakes, handbrake, skid, horn, doors, rain, ignition, radio...  KEPT
  wheelData       tyre roll, suspension bumps and landings                         KEPT
  mechanicalData  engine loop start/stop, gear up/down, rpm/throttle inputs        REPLACED
  gearSweeteners  extra sounds played on gear changes                              REMOVED
Everything else (collisions, radio receiver, emitter positions) is kept.

Only bytes from the vanilla file are reused (the donor's mechanicalData property is copied
verbatim), so no new names are added and the strings/names tables stay unchanged.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cr2w_edit  # noqa: E402
from cr2w_walk import CR2W  # noqa: E402

DEPOT_PATH = "base\\sound\\metadata\\cooked_metadata.audio_metadata"
GAME_ARCHIVE = "/Applications/Cyberpunk 2077/archive/Mac/content/audio_1_general.archive"
TARGET_PREFIXES = ("v_car_", "v_mbike_")
# Donor engine sections. Traffic profiles (names ending "_traffic") use the Basilisk's
# traffic profile, whose engine section starts no engine loop: NPC EVs then make only tyre,
# road and brake noise, like real EVs at city speeds. Set TRAFFIC_DONOR to DONOR to give
# traffic the same audible hum as the player's car.
DONOR = "v_av_basilisk_tank"
TRAFFIC_DONOR = "v_av_basilisk_tank_traffic"

# A/B crossover: profile name prefix -> donor (player profile). Traffic profiles of the
# same family use the donor's "_traffic" profile. Everything not listed uses DONOR.
# Result of session 1 (Hella = Basilisk, Sport R-7 = Caliburn): the Caliburn engine keeps
# combustion pops and crackles, so every vehicle uses the Basilisk. AB_SESSION = 0 disables
# overrides; the families are kept for future auditions.
AB_SESSION = 0
AB_FAMILIES = {
    1: {"v_car_archer_hella": "v_av_basilisk_tank", "v_car_quadra_sport_r7": "v_car_rayfield_caliburn"},
    2: {"v_car_archer_hella": "v_car_rayfield_caliburn", "v_car_quadra_sport_r7": "v_av_basilisk_tank"},
}
# Engine sub-fields never copied from a donor: we have a single gear, so no shift sounds.
STRIP_MECH_FIELDS = ("gearUpBeginEvent", "gearDownBeginEvent")
# General-data fields naming the engine sound banks; switched to the donor's so its engine
# events are loaded (the Basilisk has none, so targets keep their own banks for it).
BANK_FIELDS = ("revSoundbankName", "revElectricSoundbankName")


def _prop_bytes(c, prop):
    _name, _type, voff, vsize = prop
    return c.d[voff - 8 : voff + vsize]


def _chunk_span(c, i):
    _cls, _f, _p, size, off, _t, _crc = c.exports[i]
    return off, size


def rebuild_chunk(c, i, props):
    """Serialise a chunk from (name, type, value_off, value_size) props taken from c."""
    off, size = _chunk_span(c, i)
    original = c.d[off : off + size]
    head = original[:1]                       # leading 0x00
    last = c.export_props(i)[-1]
    tail = c.d[last[2] + last[3] : off + size]  # terminator after the last property
    return head + b"".join(_prop_bytes(c, p) for p in props) + tail


def donor_for(name, session=None):
    """Donor profile for a target profile: A/B family override, else the default."""
    families = AB_FAMILIES.get(AB_SESSION if session is None else session, {})
    player = next((d for prefix, d in families.items() if name.startswith(prefix)), DONOR)
    if name.endswith("_traffic"):
        return TRAFFIC_DONOR if player == DONOR else f"{player}_traffic"
    return player


def _struct_bytes(c, prop, subprops):
    """Re-serialise a struct-valued property with the given sub-properties (all from c)."""
    name, typ, voff, vsize = prop
    original = c.read_struct(voff + 1, voff + vsize)
    last = original[-1]
    tail = c.d[last[2] + last[3] : voff + vsize]          # struct terminator
    value = b"\x00" + b"".join(_prop_bytes(c, p) for p in subprops) + tail
    name_idx = c.name_index[name]
    type_idx = c.name_index[typ]
    return struct.pack("<HHI", name_idx, type_idx, len(value) + 4) + value


def _subprops(c, prop):
    _n, _t, voff, vsize = prop
    return c.read_struct(voff + 1, voff + vsize)


def _assemble(c, i, parts):
    """Chunk bytes from a list of raw property byte strings."""
    off, size = _chunk_span(c, i)
    last = c.export_props(i)[-1]
    tail = c.d[last[2] + last[3] : off + size]
    return c.d[off : off + 1] + b"".join(parts) + tail


def build_hybrid(data: bytes):
    c = CR2W(data)
    profiles = {}
    for i in range(len(c.exports)):
        if c.export_class(i) == "audioVehicleMetadata":
            props = c.export_props(i)
            pmap = {p[0]: p for p in props}
            profiles[c.value(*pmap["name"][1:])] = (i, props, pmap)

    # Self-checks: chunks and struct properties must re-serialise unchanged.
    for name, (i, props, pmap) in profiles.items():
        off, size = _chunk_span(c, i)
        if rebuild_chunk(c, i, props) != c.d[off : off + size]:
            raise ValueError(f"cannot round-trip profile {name}")
        for key in ("generalData", "mechanicalData"):
            if key in pmap and _struct_bytes(c, pmap[key], _subprops(c, pmap[key])) != _prop_bytes(c, pmap[key]):
                raise ValueError(f"cannot round-trip {name}.{key}")

    def donor_parts(donor):
        _di, _dprops, dmap = profiles[donor]
        mech = [p for p in _subprops(c, dmap["mechanicalData"]) if p[0] not in STRIP_MECH_FIELDS]
        banks = {p[0]: p for p in _subprops(c, dmap["generalData"]) if p[0] in BANK_FIELDS} \
            if "generalData" in dmap else {}
        rpm = {k: dmap[k] for k in ("minRpm", "maxRpm") if k in dmap}
        return _struct_bytes(c, dmap["mechanicalData"], mech), banks, rpm

    replace, report = {}, []
    for name, (i, props, pmap) in sorted(profiles.items()):
        if not name.startswith(TARGET_PREFIXES):
            continue
        donor = donor_for(name)
        mech_bytes, banks, rpm = donor_parts(donor)
        parts = []
        for p in props:
            if p[0] == "gearSweeteners":
                continue
            if p[0] in ("minRpm", "maxRpm") and rpm:
                continue  # replaced by the donor's below
            if p[0] == "mechanicalData":
                parts.append(mech_bytes)
                for k in ("minRpm", "maxRpm"):
                    if k in rpm:
                        parts.append(_prop_bytes(c, rpm[k]))
                continue
            if p[0] == "generalData" and banks:
                subs = _subprops(c, p)
                have = {s[0] for s in subs}
                subs = [banks.get(s[0], s) for s in subs] + [b for k, b in banks.items() if k not in have]
                parts.append(_struct_bytes(c, p, subs))
                continue
            parts.append(_prop_bytes(c, p))
        if "mechanicalData" not in pmap:
            parts.insert(1, mech_bytes)
        replace[i] = _assemble(c, i, parts)
        report.append((name, donor, "gearSweeteners" in pmap, "wheelData" in pmap))

    return cr2w_edit.rebuild(data, replace), report


def verify(out: bytes, report, src: bytes):
    """Re-parse the output and check every converted profile against its donor as it is
    in the vanilla file (a donor can itself be a converted target)."""
    c = CR2W(out)
    v = CR2W(src)

    def profile_map(cw):
        res = {}
        for i in range(len(cw.exports)):
            if cw.export_class(i) == "audioVehicleMetadata":
                pmap = {p[0]: p for p in cw.export_props(i)}
                res[cw.value(*pmap["name"][1:])] = pmap
        return res

    profiles, vanilla = profile_map(c), profile_map(v)

    def mech_of(cw, pm, n):
        m = cw.value(*pm[n]["mechanicalData"][1:])
        return {k: val for k, val in m.items() if k not in STRIP_MECH_FIELDS}

    seen = 0
    for name, donor, _sw, _wh in report:
        pmap, dmap = profiles[name], vanilla[donor]
        seen += 1
        assert "gearSweeteners" not in pmap, name
        assert "generalData" in pmap, name
        assert mech_of(c, profiles, name) == mech_of(v, vanilla, donor), (name, donor)
        assert not any(k in c.value(*pmap["mechanicalData"][1:]) for k in STRIP_MECH_FIELDS), name
        if "maxRpm" in dmap:
            assert c.value(*pmap["maxRpm"][1:]) == v.value(*dmap["maxRpm"][1:]), name
        dgen = v.value(*dmap["generalData"][1:]) if "generalData" in dmap else {}
        tgen = c.value(*pmap["generalData"][1:])
        for k in BANK_FIELDS:
            if k in dgen:
                assert tgen.get(k) == dgen[k], (name, k)
        # everything outside the engine section and banks must be untouched
        vt = vanilla[name]
        for k in pmap:
            if k in ("mechanicalData", "minRpm", "maxRpm", "generalData"):
                continue
            assert c.value(*pmap[k][1:]) == v.value(*vt[k][1:]), (name, k)
        vgen = v.value(*vt["generalData"][1:])
        assert {k: x for k, x in tgen.items() if k not in BANK_FIELDS} == \
               {k: x for k, x in vgen.items() if k not in BANK_FIELDS}, name
    return seen


def platform(data: bytes) -> str:
    c = CR2W(data)
    return next((n for n in c.names if n.startswith("PLATFORM_")), "none")


if __name__ == "__main__":
    import collections

    import rdar

    src = rdar.extract(GAME_ARCHIVE, DEPOT_PATH)
    out, report = build_hybrid(src)
    n = verify(out, report, src)
    by_donor = collections.Counter(r[1] for r in report)
    print(f"A/B session {AB_SESSION}: {n} profiles converted; donors: {dict(by_donor)}")
    for r in report:
        if r[0].startswith(tuple(AB_FAMILIES.get(AB_SESSION, {}))):
            print(f"   {r[0]:40} <- {r[1]}")
