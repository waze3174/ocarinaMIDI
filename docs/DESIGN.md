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

## The game's song matcher (main 1.1.1, found statically)

Notes are codes: the semitone above A#3, so B3 = 1, D4 = 4, F4 = 7, A4 = 11, B4 = 13, D5 = 16, F5 = 19.
`main+0x32941c0` gives a button's natural code. The ocarina object keeps two histories of the notes
played, rings of 8 codes:

| | |
|---|---|
| +0x138 (write index +0x258, count +0x250) | Each note's start: its button's natural code, +1 or -1 for the D-pad modifier, and +2 or -2 for the left stick's digital up or down (sead's LS bits 0x100000, 0x200000). |
| +0x158 (index +0x25c, count +0x254) | Each new press of a note button (`main+0x329558c` to `main+0x329583c`). In the modes in mask 0x1c8c of the mode at +0x230 (2, 3, 7, 10, 11, 12), the button's natural code. In the other modes, the natural code only when both stick bytes are within 0x7b..0x85 and neither modifier is held; otherwise the whole history is cleared (+0x158..+0x178 zeroed, index reset). |

The matcher, `main+0x3298510(song, history, write index)`, compares a song's notes (`main+0x3293fd0`,
its length from `main+0x46f450`) with the history, newest entry first, and needs every note to match in
a row. Its caller (`main+0x3297490` to `main+0x32975e4`) tries each song against +0x158, then +0x138;
either match sets the song off. The scarecrow's song comes from the save (`main+0x32985d0`, hash
0xcc535536).

So the game takes a song only from plain presses of its buttons, with the stick near centre. The
converter breaks each match with an **alternate fingering** on one of its notes: the same button with
the lowering modifier and a half tilt up (+1 semitone), which sounds the same pitch. In free play that
clears +0x158 (a modifier held, the stick off centre) and puts a code that isn't a natural note in
+0x138 (natural - 1, or natural + 1 if the half tilt sets sead's up bit), so neither history matches.
`notes_to_alter` picks the fewest such notes (one per game song, or one for overlapping ones). Every other
note the converter plays already avoids natural codes unless it is the natural note played plainly, so
matching pitches (`GAME_SONGS`) finds exactly the places to break.

Proven from the code: the two histories, what they record, the reset, and the exact match. Inferred:
the free-play mode is outside mask 0x1c8c (modifier notes played in the 0.1.1 live test); the game's
songs are the N64 melodies (Saria's Song confirmed live); the stick bend still applies in the modes
inside the mask. In those modes (the press test, `main+0x3294030`, refuses a button with a modifier),
the alternate note would play as its natural note and a song could still match; they look like the
modes where the game teaches a song. The scarecrow's song can't be predicted, so it isn't avoided.

## The module

- **Loading.** `subsdk8` in the game's exefs. rtld links it (imports: `nnMain`, `aligned_alloc` and
  `free` from main; nn::fs, `nvnBootstrapLoader`, `vsnprintf` and a few libc functions from sdk; the
  list in `lib/imports.txt` is checked at link time) and calls `ocarina_midi_module_init` (DT_INIT).
  No IPS patch and no game offsets: main's base comes from the memory region holding `nnMain`, and its
  imports are found by name through its MOD0 and dynamic section (`got.c`).
- **Controller hooks, installed late.** Module init only points two of main's setup imports at small
  wrappers: `nn::hid::InitializeNpad` and `nn::hid::GetNpadStyleSet`. The game calls them from its own
  code, after rtld has run every module's DT_INIT. The first call to either points main's five
  `nn::hid::GetNpadStates` GOT slots at our wrappers, each saving what the slot held then and calling it.
- **NVN hook, installed at init.** Module init also points main's `nvnBootstrapLoader` slot at a
  wrapper (`nvn.c`), since the game may set up NVN before its first controller call.
- **Lazy binding.** main has no `BIND_NOW`, so rtld binds its imports (JUMP_SLOTs) at their first call:
  until then a slot holds main's PLT0, which passes rtld's resolver the slot address that the import's
  own PLT stub left in x16. Called from anywhere else, the resolver reads a garbage relocation and
  returns 0 (0.1.0 crashed this way: its GetNpadStyleSet hook tail-called PLT0 with x16 = PLT0). When
  x16 happens to still hold the slot, rtld binds it and writes the function over the hook. So a hook
  never calls a slot value that points into main. It calls the function itself, which this module
  imports from sdk (rtld binds this module's imports at load). Only code in another module, the sdk's
  function or another add-on's wrapper, is chained to (`got_hook`).
- **Next to sloperinaGZ.** sloperinaGZ (subsdk9) hooks the same five slots and `nvnBootstrapLoader` at
  its own DT_INIT. Our controller hooks go in after every DT_INIT, so they wrap whatever is there:
  game -> ocarinaMIDI -> sloperinaGZ -> sdk, whichever DT_INIT runs first, and whether sloperinaGZ's
  wrappers chain (its `feature/chain-hooks` branch) or call the sdk directly (0.0.4.1 and before).
  sloperinaGZ's own menu reads `nn::hid::detail::GetNpadStates`, which we don't touch. We see the states
  after sloperinaGZ has edited them: blank while its menu is open, and without R3 while its levitate
  floats, so our controls don't respond then; a playing song still replaces them.
  The NVN hook goes in at our DT_INIT, so its order follows rtld's: sloperinaGZ's DT_INIT has run first
  in the logs so far, and ours then wraps its loader. Each module wraps the functions the loader and
  `nvnDeviceGetProcAddress` hand out, so the game's present goes through both wrappers, each drawing its
  own panel and calling the next once: one present. If ours ran first, a chaining sloperinaGZ would wrap
  ours the same way, while 0.0.4.1 (which calls the sdk's loader directly) would cut ours out: no song
  list, and nothing else lost.
  Different mount name (`ocamidi`, not `ootgz`), different slot, no IPS: nothing else is shared.
- **Frames.** The module has no frame hook. It counts frames from the game's controller reads: the
  first controller (style and NpadIdType) the game reads is the anchor, and a read of it at least 8 ms
  after the last starts a frame (`poll.c`).
- **Timing** is by the clock: the system tick (`cntpct_el0`), in milliseconds. At each frame the song
  gives the game the next event once its time has come, one event per frame at most (FORMAT.md,
  Playback). 0.1 stepped one tick per counted frame, so the tempo followed the game's frame rate, which
  the 0.1.1 live test measured at 24.6 to 39 frames a second. A frame-counting mode wasn't kept: it would
  need a flag in the file or a control, and a second path through the player.
- **Each frame** (`app.c`): the song moves on (`player.c`), then the buttons held during the frame that
  ended are checked for the controls (`controls.c`), and the song list's text is handed to the
  overlay. The playlist is read when R3 goes down (not while a song plays) and a song when it starts,
  from the SD card on the game's thread (a few milliseconds).
- **Each state the game reads**, connected ones only: while a song plays, its buttons and sticks
  replace the controller's, plus the stick-direction bits the emulator would set for those sticks
  (beyond half tilt). Otherwise, while R3 is held, the D-pad is taken out.

## The song list on screen

For 3 s after the selection changes (R3 + D-pad Right / Left), and never while a song plays (playing
hides it at once), a panel at the top centre shows the selected song, its
place in the playlist, the songs before and after it (dimmed) and whether a song plays, with its time
(`songlist.c`). File names are shown without `.oca`, `_` as a space and anything outside ASCII as `?`,
cut with `...` to fit.

Drawing is sloperinaGZ's, cut down to one opaque panel (`nvn.c`, `overlay.c`, `font.c`). The wrapper on
`nvnBootstrapLoader` wraps `nvnDeviceGetProcAddress` and, through it, `nvnQueuePresentTexture` (draw,
then present), `nvnWindowBuilderSetTextures` (the swapchain textures) and `nvnDeviceInitialize` (the
device). No shaders: the text is rasterised on the CPU into a buffer in the swapchain's format and
copied into the texture about to be presented with `nvnCommandBufferCopyBufferToTexture`, from two
slots that alternate, each reused only once its sync says the GPU is done. Nothing is read back from
the picture, so there's no wait on the game's rendering. A slot is only rasterised again when its text
changes. The controller thread hands the text to the present thread through a sequence lock.

## The converter

`tools/midi2oca.py` does everything musical, so the module only replays input: picking the melody,
fitting the range, the button for each semitone (`NOTE_PLAN`, `LAYOUTS`), the stick tilts, the
alternate fingerings, rounding to ticks, and a released tick between two notes on the same button.
Changing how a note is played needs no new module build. The file format is in [FORMAT.md](FORMAT.md).

It reports each place the melody holds one of the game's songs note for note (`GAME_SONGS`, the N64
melodies) and the note it played differently there; with `--allow-songs` it plays them plainly and
warns instead. `tools/live_test_songs.py` writes the songs for the live test ([TESTING.md](TESTING.md)).

## Known limits

- One note at a time; no velocity, no MIDI pitch bend.
- One event per counted frame: if the game read its anchor controller twice in one frame, at least
  8 ms apart, a song catching up could give two events in that frame.
- The controller reads are assumed to come from one thread; frames counted from two threads at once
  could step the song twice.
- The game's songs are only avoided in free play (see the matcher), and the scarecrow's not at all.
- With `--invert-stick` (not needed on this game: the 0.1.1 live test bent the right way without it),
  the alternate F4 and D5 could read as D4 and B4 in +0x138 if the half tilt sets sead's down bit.
