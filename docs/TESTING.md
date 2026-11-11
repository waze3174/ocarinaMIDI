# Live test plan

0.1.1 passed t1 to t8 in an emulator next to the bundled sloperinaGZ 0.0.4.1 (2026-11-10), and t8 set off
Saria's Song. The stop lines measured 24.6 to 39 frames a second against songs made for 30, which is
why 0.2.0 times songs by the clock. In 0.2.0 the clock timing and the song list are confirmed in game;
avoiding the game's songs hasn't been tried yet. Steps marked **new** cover what changed (the song list,
clock timing, avoiding the game's songs, missing playlist files); the others check nothing regressed.

## Setup

1. **Back up the save.** A song the module plays could still be taken as one of the game's songs.
2. Build (BUILDING.md) and copy `bin/subsdk8` to `user\load\0400486024DEC000\ocarinaMIDI\exefs\subsdk8`.
   Check it's ticked in the game's Properties > Add-ons.
3. Put the test songs on the emulator's SD card:

   ```
   python tools\live_test_songs.py --sd "<user folder>\sdmc"
   ```

   That's t1 to t8 in the playlist. Converter options after `--sd` (`--allow-songs`, `--stick-half 20000`,
   ...) apply to all eight. The module reads the playlist each time R3 goes down and a song each time it
   starts, so a new conversion needs no restart.
4. Keep the emulator's log open: the module's lines start `ocarinaMIDI:`.

## 1. Loading, with and without sloperinaGZ

Three boots: ocarinaMIDI alone; with sloperinaGZ 0.0.4.1 as released; with sloperinaGZ built from its
`feature/chain-hooks` branch (aacbf17 or later). Each should log:

```
ocarinaMIDI: loaded 0.2.0 (...); controller hooks go in at the game's first controller setup
ocarinaMIDI: GetNpadStates style 0 hooked from InitializeNpad: calls the sdk at 0x...      (x5, styles 0-4)
ocarinaMIDI: counting frames from reads of controller style S, NpadIdType 0x...
```

- Alone: "calls the sdk". With sloperinaGZ: "calls another module" for all five, and sloperinaGZ still logs
  "input hook installed".
- sloperinaGZ still works: its menu opens (R + right stick down) and Link doesn't move while it's open.
- No `[rtld] Unresolved symbol` line anywhere: that's a hook calling main's PLT (0.1.0's crash, DESIGN.md).
- No "no song list on screen:" line after "loaded" (main's `nvnBootstrapLoader` import wasn't found).

## 2. The song list (new)

With the ocarina out, hold R3. Nothing shows yet: the list only appears when the selection changes.

- R3 + D-pad Right: a panel at the top centre: `song 1 of 8` and `stopped` on the first line, the selected song in white
  with `>`, the songs before and after it in grey. The log shows, once, `swapchain: WxH, format F`,
  `song list ready (...)` and `song list on screen: ...`.
- R3 + D-pad Right / Left steps through the list (and logs "song 2 of 8: ..."). It wraps at both ends.
  The list stays 3 s after the last switch, then goes, whether R3 is held or not.
- R3 + D-pad Up right after switching: the list goes at once and the song plays without it. Play
  and stop alone never show it.
- The game's picture is unchanged around the panel, there's no flicker, and the frame rate is the same
  with the list shown and hidden (the emulator's fps counter).
- A long file name ends in `...`; `_` shows as a space.
- Delete one `.oca` from `sdmc\ocarinaMIDI\songs` (leave its playlist line) and press R3 again: the count
  drops by one, the log says "playlist: ... is missing, skipped", and stepping never lands on it.
- With each sloperinaGZ (0.0.4.1 and chain-hooks): open its menu, then switch songs. Both panels draw, the
  game doesn't freeze or flicker, and the log has no "song list off:" line. If ours never shows next to
  0.0.4.1, check the log for the order of the two modules' "loaded" lines (DESIGN.md, Next to
  sloperinaGZ).
- "song list off: unsupported swapchain format": the line before it gives the format; `format_bpp` in
  `src/overlay.c` needs it.

## 3. t1, the five buttons, and the stop lines

D4 F4 A4 B4 D5, one second each. When it ends:

```
stopped (end of the song) at 7.1xx s of 7.1xx s, after 7.1xx s: N frames, F per second
timing: events up to L ms late; 0 stalls paused it for 0 ms; E controller states edited per frame
```

- "after" (wall time) matches "of" (the song's length): the tempo is right whatever **F** is.
- **L** is at most about one frame (33 ms at 30 fps).
- **E** is how many connected controller states the game reads per frame: expected 1, maybe a few.

## 4. Steady tempo at different frame rates (new)

Play t4 (B3 to F5 and back, 0.5 s a note) somewhere the game holds its full rate, then somewhere it runs
slower (a busy area, or a higher resolution scale in the emulator: anything that changes the fps
counter). Both stop lines should give "after" within 0.1 s of "of", with different "per second" values.
By ear, the notes are evenly spaced in both places.

## 5. t2 to t7 (passed in 0.1.1)

- t2: C#4 D#4 E4 F#4 G#4 A#4 C5 C#5 D#5, each as played by hand with button + D-pad.
- t3: B3 C4 C#4 D4, then F#4 G4 G#4, then D#5 E5 F5, each group rising by semitones.
- t4: every semitone, no note missing or merged with the one before.
- t5: D4 held 2, 5 and 10 s, sounding the whole time.
- t6: A4 after rests of 2, 5 and 10 s; the ocarina stays out.
- t7: A4 eight times at 0.25 s, 0.125 s and 1/16 s: 24 presses. Also count them at a lower frame rate:
  still 24, as each press and each release gets a frame of its own.

## 6. A dense song (new)

`dragonforce - Through the Fire and Flames.mid` (439 s, 5429 events, 30 of them in its busiest second:
one per tick) and `rick astley - never gonna give you up.mid` (a lighter one). This is the stress test
for the one-frame minimum and the released frame before a repeated note.

- No note sticks and no repeated note merges (listen in the fastest runs).
- The timing line's **L** stays small at 30 fps and grows at lower rates, and "after" exceeds "of" by
  at most about L: the song falls behind in fast runs and catches up after them.
- A load or a hitch during the song shows as "N stalls paused it for M ms"; the song carries on from
  where it was.

## 7. t8, one of the game's songs (new)

Saria's Song (F4 A4 B4 twice), on a save that knows it, somewhere nothing reacts to it.

- Converted by default (`live_test_songs.py --sd ...`), the converter prints "Saria's Song at notes 1-6
  (...): note 6 (B4) is played as Y + DDOWN + left stick half up, the same pitch, ...". In the game, all
  six notes play, the last B4 sounds like the first, and the game does **not** take it as Saria's Song.
- Converted again with `--allow-songs`: it prints a warning instead, and the game takes it as Saria's
  Song, as 0.1.1 did.
- If the default conversion is still recognised, the game matched in a mode where it ignores the
  modifier (DESIGN.md, the song matcher): note which situation it was in.
- If the altered B4 sounds a semitone off, the stick bend and the modifier don't add up the way the
  code reads (`ALTERNATE_FINGERING` in the converter).

## 8. Stopping and edge cases

- R3 + D-pad Down stops ("stopped (R3 + D-pad down)"); R3 + D-pad Up while playing restarts.
- R3 + D-pad Right while playing: "a song is playing: stop it first", and the list shows `playing m:ss`.
- After a song, the controller works as normal.
- With sloperinaGZ: its menu doesn't stop a playing song, and while its levitate is floating it hides R3,
  so the controls (and the list) don't respond then.
