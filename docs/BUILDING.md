# Building

- [devkitA64](https://devkitpro.org/wiki/Getting_Started), with `DEVKITPRO` set: devkitPro's MSYS2 shell
  sets it (`/opt/devkitpro`).
- Python 3 for `make test`.

```
make            # bin/subsdk8
make dist       # dist/ryuchii/load/0400486024DEC000/ocarinaMIDI/exefs/subsdk8, dist/atmosphere/...
make test       # the converter's tests
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
ocarinaMIDI: loaded 0.2.0 (...); controller hooks go in at the game's first controller setup
ocarinaMIDI: GetNpadStates style 0 hooked from InitializeNpad: calls the sdk at 0x...
...
ocarinaMIDI: counting frames from reads of controller style 0, NpadIdType 0x0
```

"calls another module" instead of "calls the sdk" means another add-on (sloperinaGZ) hooked that import
first and ours wraps it. The first time the song list shows, it logs `swapchain: ...`,
`song list ready (...)` and `song list on screen: ...`; `song list off: <why>` means it gave up, and the
rest of the module carries on without it.
