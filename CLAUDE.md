# ocarinaMIDI

A subsdk8 module for Ocarina of Time (Switch 2, program id 0400486024DEC000) that replays converted MIDI
songs as ocarina input, and the PC converter. See README.md, docs/DESIGN.md (how it works), docs/FORMAT.md
(.oca), docs/TESTING.md (live test plan), docs/BUILDING.md.

## Commands

- Build: `make` from devkitPro's MSYS2 shell (`make dist` for the install folders); see docs/BUILDING.md.
  Don't build while the emulator is running on the machine you test on.
- Tests: `make test`, or `python -I -m unittest discover -s tests -t .` from the repo root.

## Rules

- No game offsets in the module: main's base comes from `nnMain`, its imports by name (`got.c`).
- Every hook calls what its slot held before (other add-ons, e.g. sloperinaGZ, hook the same slots),
  unless the slot still points into main: main binds its imports lazily, and a hook must never call
  its PLT. The hook then calls the function itself, imported by this module (docs/DESIGN.md).
- Music logic lives in the converter; the module only replays input.
- The song list draws by copying CPU-rasterised pixels into the presented texture; never read the
  picture back (it would wait on the game's rendering) and never present twice.
- GPL-3. Code adapted from sloperinaGZ keeps its notice; credit it and gz in the README.
