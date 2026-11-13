# Building

- [devkitA64](https://devkitpro.org/wiki/Getting_Started), with `DEVKITPRO` set: devkitPro's MSYS2 shell
  sets it (`/opt/devkitpro`).
- Python 3 for `make test`, and a C compiler for the PC for the player's tests (`$CC`, or `cc`, `gcc` or
  `clang` on the PATH, or LLVM in its default place on Windows); without one they are skipped.

```
make            # bin/subsdk8
make dist       # dist/emulator/load/0400486024DEC000/ocarinaMIDI/exefs/subsdk8, dist/atmosphere/...,
                # dist/emulator-converter (the drop bat and converter, to put next to an emulator's exe)
make test       # the converter's and the player's tests
make release    # dist, then dist/ocarinaMIDI-<version>.zip for a GitHub release
```

On Windows without the MSYS2 shell open:

```
C:\devkitPro\msys2\usr\bin\bash.exe -lc "cd /c/path/to/ocarinaMIDI && make"
```

The link step fails if the module needs a symbol that's neither defined nor in `lib/imports.txt` (the
imports sloperinaGZ has used on this game, and `memcmp`, checked in the game's sdk: all
exported by main or sdk).

## Checking a build loads

In the emulator's log, at boot:

```
ocarinaMIDI: loaded 0.3.0 (...); controller hooks go in at the game's first controller setup
ocarinaMIDI: GetNpadStates style 0 hooked from InitializeNpad: calls the sdk at 0x...
...
ocarinaMIDI: counting frames from reads of controller style 0, NpadIdType 0x0
```

"calls another module" instead of "calls the sdk" means another add-on (sloperinaGZ) hooked that import
first and ours wraps it. The first time songs are switched it logs the game's files being read (`ui
shader: programs N and M ...`, `game fonts: Clarimo UD PE loaded (N KiB, N ms)`), then `gpu drawing ready (...)`
when the first frame is drawn. If the game-style drawing can't be used it says why and the plain panel logs
`swapchain: ...`, `song list ready (...)` and `song list on screen (plain): ...` instead;
`song list off: <why>` means the list gave up altogether, and the rest of the module carries on without
it.
