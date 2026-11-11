# Live test plan

Nothing here has run in the game yet. Each step says what to look for and what to change if it's wrong.
The steps answer the open questions: init order (1), frame counting (3), stick direction and tuning (5),
sustain (7), rests (8), and whether a melody can set off one of the game's songs (10).

## Setup

1. **Back up the save.** A song the module plays could be taken as one of the game's songs (step 10).
2. Build (BUILDING.md) and copy `bin/subsdk8` to `user\load\0400486024DEC000\ocarinaMIDI\exefs\subsdk8`.
   Check it's ticked in the game's Properties > Add-ons.
3. Put the test songs on the emulator's SD card:

   ```
   python tools\live_test_songs.py --sd "<user folder>\sdmc"
   ```

   That's t1 to t8 in the playlist. Converter options after `--sd` (`--invert-stick`, `--stick-half 20000`,
   `--fps 25` ...) apply to all eight. The module reads the playlist and the song again at each play, so a
   new conversion needs no restart.
4. Keep the emulator's log open: the module's lines start `ocarinaMIDI:`.

## 1. Loading, with and without sloperinaGZ

Three boots: ocarinaMIDI alone; with sloperinaGZ 0.0.4.1 as released; with sloperinaGZ built from its
`feature/chain-hooks` branch. Each should log:

```
ocarinaMIDI: loaded 0.1.0 (...); controller hooks go in at the game's first controller setup
ocarinaMIDI: GetNpadStates style 0 hooked from InitializeNpad: calls the sdk at 0x...      (x5, styles 0-4)
ocarinaMIDI: counting frames from reads of controller style S, NpadIdType 0x...
```

- Alone: "calls the sdk". With sloperinaGZ: "calls another module" for all five, and sloperinaGZ still logs
  "input hook installed".
- sloperinaGZ still works: its menu opens (R + right stick down) and Link doesn't move while it's open.
- "not started": main has neither `InitializeNpad` nor `GetNpadStyleSet` in its imports (1.1.1 has both).
- "loaded" but no "hooked from" lines: the game never called either, so the hooks need another trigger.

## 2. The controls, no song playing

With the ocarina out, and once in normal play:

- R3 alone: note what the game does with it. It mustn't close the ocarina. If it does something in the
  field that gets in the way, the modifier is `CONTROL_MODIFIER` in `src/controls.c`.
- R3 + D-pad Up/Down: the ocarina's pitch mustn't change (the D-pad is hidden while R3 is held).
- R3 + D-pad Right / Left: "song 1 of 8: t1-naturals.oca", then the next and previous.

## 3. t1, the five buttons (frame counting)

D4 F4 A4 B4 D5, one second each. Link should play each with the staff showing it. When it ends:

```
stopped (end of the song) after 213 frames in T s: F frames per second (song made for 30); E controller states edited per frame
```

- **F** is the frame rate as the module counts it. Compare it with the emulator's fps counter. Double or
  half means the frame counting is off (`MIN_FRAME_MS` or the anchor in `src/poll.c`). If the game holds a
  steady rate other than 30, convert with `--fps F` for songs at their real tempo.
- **E** is how many connected controller states the game reads per frame: expected 1, maybe a few. If it
  wobbles between runs, the game may read from more than one thread.
- Wrong or missing notes: check the game's ocarina controls (Options); "Performance" needs `--layout performance`.
  Notes on the wrong buttons throughout would mean the Switch 2 controller state isn't the Switch 1 layout
  the module assumes.

## 4. t2, button + D-pad

C#4 D#4 E4 F#4 G#4 A#4 C5 C#5 D#5. Each should match playing it by hand (button + D-pad Up or Down).

## 5. t3, the stick bends

B3 C4 C#4 D4, then F#4 G4 G#4, then D#5 E5 F5: each group rises by semitones.

- B3, C4, G4, E5, F5 sound like their neighbours without the bend (C#4, F#4, D#5): the game bends with the
  other stick, so use `--bend-stick right`.
- Bent the wrong way (B3 above C#4): `--invert-stick`.
- A step too small or too large (C4 the same as B3 or C#4): `--stick-half` (default 16384, which should be
  the game's byte 192, its half-tilt step, if it maps the stick without a dead zone). Try 12000 and 20000.
- Bent notes that start unbent and then slide: the game reads the stick a frame after the press; the
  converter would then have to tilt a frame early.

## 6. t4, B3 to F5 and back

Every semitone, 0.5 s each, no gaps. Two notes in a row on the same button get one released frame
between them: check no note is missing or merged with the one before.

## 7. t5, sustain

D4 held 2, 5 and 10 s. Does it sound the whole time? If the game cuts or fades long notes, songs will too.

## 8. t6, rests

A4, then rests of 2, 5 and 10 s, each followed by A4. Does the ocarina stay out through every rest?

## 9. t7, repeated notes

A4 eight times at 0.25 s, eight at 0.125 s, eight at 1/16 s (one frame pressed, one released, at 30
fps). Count them: 24 if every press reaches the game. If the fastest merge, the game needs more than one
released frame (a converter change: the gap in `segments`).

## 10. t8, one of the game's songs

Saria's Song (F4 A4 B4 twice). Play it on a save that knows it, somewhere nothing reacts to it.

- Recognised (the song's jingle, Saria talks): the module's input sets off songs, so a melody that holds a
  warp song would warp. The converter warns when a melody holds one of the game's songs note for note.
- If F#4 in place of an F4 still counts, the game matches buttons, not notes, and that check needs widening.

## 11. Stopping and edge cases

- R3 + D-pad Down stops ("stopped (R3 + D-pad down)"); R3 + D-pad Up while playing restarts.
- After a song, the controller works as normal.
- "can't mount the SD card": nn::fs can't be used from the controller hook; mount at module init instead.
- With sloperinaGZ: its menu doesn't stop a playing song, and while its levitate is floating it hides R3,
  so the controls don't respond then.
