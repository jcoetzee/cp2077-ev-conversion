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


def donor_for(name):
    return TRAFFIC_DONOR if name.endswith("_traffic") else DONOR


def build_hybrid(data: bytes):
    c = CR2W(data)
    profiles = {}
    for i in range(len(c.exports)):
        if c.export_class(i) == "audioVehicleMetadata":
            props = c.export_props(i)
            pmap = {p[0]: p for p in props}
            profiles[c.value(*pmap["name"][1:])] = (i, props, pmap)

    # Self-check: every profile chunk must re-serialise unchanged from its parsed props.
    for name, (i, props, _pm) in profiles.items():
        off, size = _chunk_span(c, i)
        if rebuild_chunk(c, i, props) != c.d[off : off + size]:
            raise ValueError(f"cannot round-trip profile {name}")

    donors = {d: profiles[d][2]["mechanicalData"] for d in {DONOR, TRAFFIC_DONOR}}
    replace, report = {}, []
    for name, (i, props, pmap) in sorted(profiles.items()):
        if not name.startswith(TARGET_PREFIXES):
            continue
        mech = donors[donor_for(name)]
        new_props = [mech if p[0] == "mechanicalData" else p
                     for p in props if p[0] != "gearSweeteners"]
        if "mechanicalData" not in pmap:
            new_props.insert(1, mech)
        replace[i] = rebuild_chunk(c, i, new_props)
        report.append((name, "gearSweeteners" in pmap, "wheelData" in pmap))

    return cr2w_edit.rebuild(data, replace), report


def verify(out: bytes, report):
    """Re-parse the output and check every converted profile against its donor."""
    c = CR2W(out)
    profiles = {}
    for i in range(len(c.exports)):
        if c.export_class(i) == "audioVehicleMetadata":
            pmap = {p[0]: p for p in c.export_props(i)}
            profiles[c.value(*pmap["name"][1:])] = pmap
    mech = {d: c.value(*profiles[d]["mechanicalData"][1:]) for d in {DONOR, TRAFFIC_DONOR}}
    seen = 0
    for name, pmap in profiles.items():
        if not name.startswith(TARGET_PREFIXES):
            continue
        seen += 1
        assert "gearSweeteners" not in pmap, name
        assert "generalData" in pmap, name
        assert c.value(*pmap["mechanicalData"][1:]) == mech[donor_for(name)], name
    assert seen == len(report)
    return seen


def platform(data: bytes) -> str:
    c = CR2W(data)
    return next((n for n in c.names if n.startswith("PLATFORM_")), "none")


if __name__ == "__main__":
    import rdar

    src = rdar.extract(GAME_ARCHIVE, DEPOT_PATH)
    out, report = build_hybrid(src)
    n = verify(out, report)
    traffic = sum(1 for r in report if r[0].endswith("_traffic"))
    print(f"{n} profiles converted ({n - traffic} player, {traffic} traffic); "
          f"{sum(r[1] for r in report)} had gear sweeteners removed; "
          f"{sum(r[2] for r in report)} keep wheel sounds; size {len(src)} -> {len(out)}; "
          f"platform stamp: {platform(src)}")
