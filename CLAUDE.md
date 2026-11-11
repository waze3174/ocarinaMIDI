# ocarinaMIDI

A subsdk8 module for Ocarina of Time (Switch 2, program id 0400486024DEC000) that replays converted MIDI
songs as ocarina input, and the PC converter. See README.md, docs/DESIGN.md (how it works), docs/FORMAT.md
(.oca), docs/TESTING.md (live test plan), docs/BUILDING.md.

## Commands

- Build: `C:\devkitPro\msys2\usr\bin\bash.exe -lc "cd /c/dev/ocarina-midi && make"` (`make dist` for the
  install folders). Never while the emulator (ryuchii.exe, lichii.exe) runs on the owner's PC.
- Tests: `make test`, or `python -I -m unittest discover -s tests -t .` from the repo root.

## Rules

- No game offsets in the module: main's base comes from `nnMain`, its imports by name (`got.c`).
- Every hook calls what its slot held before (other add-ons, e.g. sloperinaGZ, hook the same slots).
- Music logic lives in the converter; the module only replays input.
- GPL-3. Code adapted from sloperinaGZ keeps its notice; credit it and gz in the README.
- No remote, no push.
