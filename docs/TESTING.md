# Live test plan

0.1.1 passed t1 to t8 in an emulator next to the bundled sloperinaGZ 0.0.4.1 (2026-11-10), and t8 set off
Saria's Song. The stop lines measured 24.6 to 39 frames a second against songs made for 30, which is
why 0.2.0 times songs by the clock. In 0.2.0 the clock timing and the plain song list are confirmed in
game; avoiding the game's songs hasn't been tried yet. 0.3.0 draws the song list in the game's own style,
keeps fast songs in time (it skips what it can't give in time instead of falling behind), and its drop bat
asks which part of a song is the melody and works next to the emulator's exe; none of that is tested in
game yet. Steps marked **new** cover what changed; the others check nothing regressed.

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
ocarinaMIDI: loaded 0.3.0 (...); controller hooks go in at the game's first controller setup
ocarinaMIDI: GetNpadStates style 0 hooked from InitializeNpad: calls the sdk at 0x...      (x5, styles 0-4)
ocarinaMIDI: counting frames from reads of controller style S, NpadIdType 0x...
```

- Alone: "calls the sdk". With sloperinaGZ: "calls another module" for all five, and sloperinaGZ still logs
  "input hook installed".
- sloperinaGZ still works: its menu opens (R + right stick down) and Link doesn't move while it's open.
- No `[rtld] Unresolved symbol` line anywhere: that's a hook calling main's PLT (0.1.0's crash, DESIGN.md).
- No "no song list on screen:" line after "loaded" (main's `nvnBootstrapLoader` import wasn't found).

## 2. The song list (new in 0.3.0: the game's style)

With the ocarina out, hold R3. Nothing shows yet: the list only appears when the selection changes. Run this
once with sloperinaGZ not loaded, once with it loaded and its menu closed, and once with its menu open.

- First R3 + D-pad Right: the game may pause for a moment (it's reading its font and shader), then a box
  at the top centre in the game's menu look: near-black, the title `song 1 of 8` in gold bold with
  `stopped` dimmed at the right and a hairline under them, the songs in the game's type, the selected one
  in bold white on a light band that fades out at both ends, the ones before and after it in the normal
  colour. The log shows, once, `ui shader: programs ...`, `game fonts: Clarimo UD PE loaded (N KiB, N ms)` and
  `gpu drawing ready (... KiB, shader code ... KiB)`.
- R3 + D-pad Right / Left steps through the list (and logs "song 2 of 8: ..."). It wraps at both ends. The
  list stays 3 s after the last switch, then goes, whether R3 is held or not. Later switches don't pause.
- R3 + D-pad Up right after switching: the list goes at once and the song plays without it. Play
  and stop alone never show it.
- The game's picture is unchanged around the box, there's no flicker, the colours aren't washed out
  (a box much brighter than the game's own menus would mean the swapchain is sRGB), and the frame rate is
  the same with the list shown and hidden (the emulator's fps counter).
- A long file name ends in `...`; `_` shows as a space; a playlist of 1 or 2 songs shows only those rows.
- Delete one `.oca` from `sdmc\ocarinaMIDI\songs` (leave its playlist line) and press R3 again: the count
  drops by one, the log says "playlist: ... is missing, skipped", and stepping never lands on it.
- With sloperinaGZ (0.0.4.1 and chain-hooks, built or bundled): open its menu, then switch songs. Both
  draw, the game doesn't freeze or flicker, neither's text or box changes (sloperinaGZ's menu keeps its
  look, and the list isn't tinted by it), and the log has no "song list off:" or "gpu drawing:" error line.
  Leave the game running a few minutes, showing the list now and then: the game's own textures must not go
  wrong after it was shown (both modules put the game's texture and sampler pools back).
  Check the log for the order of the two modules' "loaded" lines (DESIGN.md, Next to sloperinaGZ).
- Memory: with sloperinaGZ loaded too, check that its pictures still load (its log) and that the game hits no
  allocation error after the first switch. This module takes about 1.5 MiB of the game's heap for the
  GPU side once it has drawn the list, and the two font files (the log gives their size).
- The plain fallback can't be forced from outside. If `game fonts:`, `ui shader:` or `gpu drawing:` reports
  a problem in the log, check that the plain panel (`song list on screen (plain)`) shows instead.
- "song list off: unsupported swapchain format": the line before it gives the format; `format_bpp` in
  `src/overlay_cpu.c` needs it (only the plain panel needs this).

## 3. t1, the five buttons, and the stop lines

D4 F4 A4 B4 D5, one second each. When it ends:

```
stopped (end of the song) at 7.1xx s of 7.1xx s, after 7.1xx s: N frames, F per second
timing: events up to L ms late; 0 notes skipped to keep time; 0 stalls paused it for 0 ms; E controller states edited per frame
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

## 6. Fast songs keep their time (new)

What was reported: fast songs "buffer weirdly". Cause (DESIGN.md, Keeping up): when notes came faster
than the game's frames, the module gave every one of them late, a frame each, so a fast run dragged and
the song then jumped back to time at the next rest; the converter also pushed notes too close together
later. Now the module skips what it can't give within 50 ms, and the converter leaves such notes out.

Songs: `dragonforce_-_Through_the_Fire_and_Flames` (the densest), `Metallica_-_Fuel`, `metallica_-_one`,
`CANTINA`. Play each twice: the file you have now (converted by 0.2, all parts), then the same song
converted again (`dist\songs-0.3.0`, or drop the MIDI on the new bat and press 0 for all parts). Note
the emulator's fps counter while it plays.

- By ear: fast runs stay on the beat and the song never stalls then rushes. Some notes of a very fast
  run are missing at low frame rates; that's expected (about one note per frame).
- The stop lines: "after" within about 0.1 s of "of"; **L** about 100 ms or less (more only right after
  a hitch shorter than 250 ms); "N notes skipped to keep time" above 0 in these songs below 30 fps.
  Write down F (per second), L and N for each: they show how much the module had to skip.
- No note sticks, and repeated notes stay separate (listen in the fastest runs).
- A load or a hitch during the song shows as "N stalls paused it for M ms"; the song carries on from
  where it was.
- `rick_astley_-_never_gonna_give_you_up` (a light song): sounds as before, and few or no notes skipped.
- If a song still sounds wrong, note the song, the time in it, the fps and the stop lines.

## 6b. Choosing the melody, and the bat next to the emulator (new)

On the PC, no game needed.

1. Copy `drop-midi-here.bat` and `midi2oca.py` from `dist\emulator-converter` next to the emulator's exe
   (the folder holding its `user` folder).
2. Drop two MIDI files on it at once, e.g. `CANTINA.mid` and `ABBA - Gimme Gimme Gimme.mid`.
   - It doesn't ask for a folder, and says `Songs go to "...\user\sdmc\ocarinaMIDI\songs"`.
   - For each file it lists the parts (`track N, channel C, name, instrument, notes, range, chords`)
     with `0  all parts together` first and one marked `<- likely the melody` ("Cantina Band" and
     "Melody" for these two).
   - Enter takes the marked part and prints `melody: ... (--track N --channel C)`; a number takes that
     part; 0 takes all parts; anything else asks again. A MIDI with one part isn't asked about.
   - Both songs land in the emulator's playlist.
3. Play a song converted as its melody part next to the same song converted with all parts: the melody
   should be clearer and lighter (fewer notes).
4. The same bat in another folder (no `user\sdmc` next to it): it asks for the SD card folder the first
   time and remembers it in `sd-path.txt` beside it.
5. Without Python 3, the bat says "Python 3 was not found" (the Microsoft Store's `python` stub, which
   only offers to install Python, doesn't count).

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
