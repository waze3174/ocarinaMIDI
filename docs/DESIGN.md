# How ocarinaMIDI works

## The game's ocarina (main 1.1.1, found statically)

| | |
|---|---|
| Notes | 19 semitones, B3 to F5. The note table at the ocarina object's +0x40 (built at `main+0xe7c570`) holds the stream names `Ocarina_LowB` ... `Ocarina_HighF`. |
| Buttons | Five buttons play the natural notes D4, F4, A4, B4, D5 (`main+0x32941c0`). "Game" layout (the default): L, R, A, Y, X. "Performance": R, B, A, Y, X. |
| Modifiers | +1 / -1 semitone: D-pad Up / Down ("Game"), L / ZL ("Performance"). The tests are at `main+0x3294030`, called from `main+0x3294df0` on. |
| Stick | A stick byte (0..255, centre 128) at +0x238 moves the note up to two semitones: steps at tilt -1, -0.5, 0, +0.5, +1. The sound is bent by `exp2f((byte - 128) / 768)`, so half tilt is one semitone and full tilt two. |
| Notes start | on a press of the note's button (or of a modifier while its button is held) and stop on release. |

The game's internal button bits are sead's layout (A 0x1, B 0x2, ZL 0x4, X 0x8, Y 0x10, ZR 0x20,
L 0x2000, R 0x4000, D-pad 0x10000..0x80000), read from its ainb button-mask node at `main+0x7550b0`;
the converter assumes they map one to one to the controller's buttons.

## The module

- **Loading.** `subsdk8` in the game's exefs. rtld links it (imports: `nnMain` from main; nn::fs,
  `vsnprintf` and a few libc functions from sdk; the list in `lib/imports.txt` is checked at link time)
  and calls `ocarina_midi_module_init` (DT_INIT). No IPS patch and no game offsets: main's base comes
  from the memory region holding `nnMain`, and its imports are found by name through its MOD0 and
  dynamic section (`got.c`).
- **Hooks, installed late.** Module init only points two of main's setup imports at small wrappers:
  `nn::hid::InitializeNpad` and `nn::hid::GetNpadStyleSet`. The game calls them from its own code,
  after rtld has run every module's DT_INIT. The first call to either points main's five
  `nn::hid::GetNpadStates` GOT slots at our wrappers, each saving what the slot held then and calling it.
- **Lazy binding.** main has no `BIND_NOW`, so rtld binds its imports (JUMP_SLOTs) at their first call:
  until then a slot holds main's PLT0, which passes rtld's resolver the slot address that the import's
  own PLT stub left in x16. Called from anywhere else, the resolver reads a garbage relocation and
  returns 0 (0.1.0 crashed this way: its GetNpadStyleSet hook tail-called PLT0 with x16 = PLT0). When
  x16 happens to still hold the slot, rtld binds it and writes the function over the hook. So a hook
  never calls a slot value that points into main. It calls the function itself, which this module
  imports from sdk (rtld binds this module's imports at load). Only code in another module, the sdk's
  function or another add-on's wrapper, is chained to (`got_hook`).
- **Next to sloperinaGZ.** sloperinaGZ (subsdk9) hooks the same five slots and `nvnBootstrapLoader` at
  its own DT_INIT. Since ours go in after every DT_INIT, they wrap whatever is there:
  game -> ocarinaMIDI -> sloperinaGZ -> sdk. That holds whichever DT_INIT runs first, and whether
  sloperinaGZ's wrappers chain (its `feature/chain-hooks` branch) or call the sdk directly (0.0.4.1 and
  before). sloperinaGZ's own menu reads `nn::hid::detail::GetNpadStates`, which we don't touch. We see
  the states after sloperinaGZ has edited them: blank while its menu is open, and without R3 while its
  levitate floats, so our controls don't respond then; a playing song still replaces them.
  Different mount name (`ocamidi`, not `ootgz`), different slot, no IPS: nothing else is shared.
- **Frames.** The module has no frame hook. It counts frames from the game's controller reads: the
  first controller (style and NpadIdType) the game reads is the anchor, and a read of it at least 8 ms
  after the last starts a frame (`poll.c`).
- **Each frame** (`app.c`): the song moves on one frame (`player.c`), then the buttons held during the
  frame that ended are checked for the controls (`controls.c`). Loading a song reads the playlist and
  the file from the SD card on the game's thread (a few milliseconds, once).
- **Each state the game reads**, connected ones only: while a song plays, its buttons and sticks
  replace the controller's, plus the stick-direction bits the emulator would set for those sticks
  (beyond half tilt). Otherwise, while R3 is held, the D-pad is taken out.

## The converter

`tools/midi2oca.py` does everything musical, so the module only replays input: picking the melody,
fitting the range, the button for each semitone (`NOTE_PLAN`, `LAYOUTS`), the stick tilts, frame
rounding, and a released frame between two notes on the same button. Changing how a note is played
needs no new module build. The file format is in [FORMAT.md](FORMAT.md).

It also warns when the melody holds one of the game's songs note for note (`GAME_SONGS`, the N64
melodies, assumed unchanged), since playing it with the ocarina out may set the song off.
`tools/live_test_songs.py` writes the songs for the live test ([TESTING.md](TESTING.md)).

## Known limits

- One note at a time; no velocity, no MIDI pitch bend.
- Timing follows the game's frame rate (frames are counted, not time).
- The controller reads are assumed to come from one thread; frames counted from two threads at once
  could step the song twice.
- Song names only show in the log; there's no on-screen display.
