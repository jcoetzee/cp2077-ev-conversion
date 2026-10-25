# EV Conversion for Cyberpunk 2077

Converts every car and motorcycle in Cyberpunk 2077 to electric-vehicle behaviour, aimed at
the official cross-platform mod support (mod.io, Update 2.5), so it can also run on consoles.

Each vehicle keeps its own character: top speed and 0-100 km/h are unchanged, drivetrains
(FWD/RWD/AWD) are unchanged, and the conversion is applied uniformly so no vehicle gains an
advantage.

## What the mod changes

| Area | Change |
|---|---|
| Gearbox | One forward gear from standstill to vanilla top speed. No shifts. |
| Torque | Custom torque curve per engine: flat to a base speed, then constant power (falls with 1/speed). |
| Calibration | Engine torque is scaled so 0-100 km/h (speedometer) and 0-80% of top speed match vanilla. |
| Response | Flywheel inertia halved; lift-off resistance x1.5 (regen-like). |
| Chassis | Mass and moment of inertia +10% (battery pack, 2077 cell density assumed); centre of mass 5 cm lower on cars. |
| Brakes | Brake and handbrake torque +10%, so stopping distances match vanilla. |
| Sound | Work in progress: borrowing the Basilisk's engine sound (see Status). |

## Status

Tested on the macOS build (GOG, Update 2.5).

- Engines, chassis and brakes: working in-game.
- Custom torque curves: working. Curve files must be stored raw in the archive (stored size ==
  real size). A Kraken header around uncompressed data is not readable by the game.
- Sound: hybrid profiles (`tools/audio_hybrid.py`). Every car and bike keeps its own sound
  profile (brakes, tyres, horn, doors, radio) with the engine section replaced by the
  Basilisk hover tank's, and gear-shift sweeteners removed. Ships as a replacement of
  `base\sound\metadata\cooked_metadata.audio_metadata`, so it conflicts with other mods that
  replace that file. In-game test pending.
- Not yet done: PC/console-stamped curve files, standalone mod folder, mod.io upload.

## Repository layout

| Path | Purpose |
|---|---|
| `tools/build_ev.py` | Main generator: reads vanilla tweak sources, writes the mod (tweaks + archive) to `build/EVConversion/`. Settings (`EV`, `CHASSIS`, `SOUND`) are at the top. |
| `tools/ev_single.py` | Single-gear EV engine design and fitting. |
| `tools/accel.py` | Straight-line acceleration model used for calibration. |
| `tools/tweakdb.py` | Checks which record names exist in the compiled `tweakdb.bin`. |
| `tools/rdar.py` | Reader and writer for REDengine 4 `.archive` files. |
| `tools/curveset.py`, `tools/curvewriter.py` | Read and write cooked `.curveset` (CR2W) files. Writer reproduces vanilla files byte for byte. |
| `tools/cr2w_walk.py`, `tools/cr2w_probe.py` | Read-only CR2W inspection. |
| `tools/cr2w_edit.py` | Rebuilds a CR2W file with export chunks replaced (round-trips vanilla files byte for byte). |
| `tools/audio_hybrid.py` | Builds the hybrid vehicle sound profiles. |
| `tools/extract_audio_meta.py` | Extracts the vehicle audio metadata for inspection. |
| `tools/extract_curves.py` | Extracts the vanilla engine torque curves (setup step 4). |
| `tools/diag*_build.py` | Diagnostic builds used to isolate in-game problems (kept for reference). |
| `tools/ooz_port/` | macOS/Apple Silicon build of the ooz Kraken decompressor (fetched at build time). |

## Setup (macOS)

Requirements: a copy of Cyberpunk 2077 (the scripts were written against the GOG Mac build),
Python 3 (standard library only), Xcode command line tools, Homebrew.

1. Install tools: `brew install innoextract lgogdownloader`
2. Get the vanilla tweak sources from the free REDmod DLC (Windows installer):
   ```
   lgogdownloader --login
   lgogdownloader --download-file "gogdownloader://cyberpunk_2077_game/cyberpunk_2077_redmod/en1installer0" --directory installers
   lgogdownloader --download-file "gogdownloader://cyberpunk_2077_game/cyberpunk_2077_redmod/en1installer1" --directory installers
   innoextract --gog -d redmod "installers/cyberpunk_2077_game/dlc/cyberpunk_2077_redmod/setup_cyberpunk_2077_redmod_2.5_redmodfix_(64bit)_(94742).exe"
   ```
3. Build the Kraken decompressor: `sh tools/ooz_port/build.sh`
4. Extract the vanilla torque curves: `python3 tools/extract_curves.py`
5. Generate the mod: `python3 tools/build_ev.py` (about 90 s the first time, about 15 s after
   that: TweakDB lookups are cached in `build/tweakdb_lookup_cache.json`, and lookups and
   engine fitting run on all CPU cores).

Paths to the game install are currently hard-coded for the GOG Mac build
(`/Applications/Cyberpunk 2077`).

## Format notes

Findings from reverse engineering, for anyone extending the tools:

- Console mods on mod.io ship `r6/tweaks/<Name>.yaml` plus a JSON mirror with full type
  names (`gamedataVehicleGear_Record`), and `archive/*.archive`. Only compiled scripts
  (`r6/cache/*.redscripts`) differ per platform.
- TweakDB records are compiled as independent copies: overriding a parent preset does not
  change records that inherit from it. Inline records are named `<record>_inline<N>`.
- `gearChangeTime = 0` stops the engine from engaging (revs, no drive). 0.05 s works.
- CR2W name-table hash: FNV-1a 64 folded to 32 bits (high ^ low); empty name = 0.
  Header CRC: CRC-32 of the first 160 bytes with the CRC field set to `0xDEADBEEF`.
- Archive index CRC: CRC-64/XZ over the counts, file entries and segments. Alignment
  padding byte is `0xD9`. File SHA-1 fields are not checked.

## Not included

This repository contains no game files. Vanilla data (REDmod tweak sources, extracted
archives) stays on your machine and is excluded by `.gitignore`. Mods must follow the
CD PROJEKT RED Fan Content Guidelines and User Agreement.

## Licence

MIT, see [LICENSE](LICENSE). This covers the scripts in this repository only.

`tools/ooz_port/build.sh` downloads and compiles [ooz](https://github.com/powzix/ooz)
(GPLv3) and [sse2neon](https://github.com/DLTcollab/sse2neon) (MIT) at build time. Neither
is included here, and the compiled `libooz.dylib` falls under ooz's GPLv3 licence.
Cyberpunk 2077 game data is not covered by this licence and is not included.
