# ocarinaMIDI

Plays MIDI songs on the ocarina in **The Legend of Zelda: Ocarina of Time (Switch 2)**. A small game
module presses the ocarina's own buttons for you, so the game plays the notes with its own sound,
animation and pitch bend. Songs are converted on the PC first (`tools/midi2oca.py`).

It runs next to [sloperinaGZ](https://github.com/PracticeROM/sloperina) or on its own. Status: 0.1.1 played
every live-test song in Ryuchii next to sloperinaGZ; 0.2.0 (clock timing, the on-screen song list, avoiding
the game's songs) is waiting for its live test. See [docs/TESTING.md](docs/TESTING.md).

## What you need

- The game, version 1.0.0 or 1.1.1 (the module uses no game offsets, so later versions should work too).
- An emulator with exefs mods (Ryuchii, Lichii, Eden), or a console with LayeredFS.
- Python 3 to convert songs.

## Install (Ryuchii)

The emulator's user folder is `user\` next to `ryuchii.exe` (portable) or `%APPDATA%\ryuchii`.

1. Copy `subsdk8` to `user\load\0400486024DEC000\ocarinaMIDI\exefs\subsdk8`.
   sloperinaGZ stays where it is (`...\sloperinaGZ\exefs\subsdk9` plus its `.ips`): the two use
   different slots and Ryuchii loads both.
2. Convert a song onto the emulator's SD card: drag `.mid` files onto `tools\drop-midi-here.bat`, or

   ```
   python tools\midi2oca.py song.mid --sd "<user folder>\sdmc"
   ```

   This writes `sdmc\ocarinaMIDI\songs\song.oca` and adds it to `songs\playlist.txt`.

## Playing

Take out the ocarina in the game, then:

| Hold R3 (right stick in) and press | |
|---|---|
| D-pad Up | play the selected song (from the start) |
| D-pad Down | stop |
| D-pad Right / Left | next / previous song |

When you switch songs (R3 + D-pad Right / Left), the song list shows at the top of the screen for 3 seconds:
the selected song, its place in the playlist, the songs before and after it, and whether a song is
playing, with its time. It goes as soon as a song starts, so it never covers a performance. Songs whose
file is gone are left out.

While a song plays, the game only sees the song's input; your controller is back when it ends or you stop
it. While R3 is held the game doesn't see the D-pad. The module also logs what it does in the emulator's
log, on lines starting `ocarinaMIDI:` (Ryuchii logs them under `Debug.Emulated`, at the default level).

## Converting songs

```
python tools\midi2oca.py song.mid --list                       the tracks and channels
python tools\midi2oca.py song.mid --sd <sdmc> --track 1        one track
python tools\midi2oca.py song.mid --sd <sdmc> --channel 4      one channel
python tools\midi2oca.py song.mid --sd <sdmc> --transpose -5   your own transposition
```

- **One note at a time.** The ocarina can't play chords: the highest note of a chord is kept, and a
  lower note only takes over when the one sounding is ending. Channel 10 (drums) is dropped. For a
  song with accompaniment, pick the melody's track or channel.
- **Range.** The ocarina plays B3 to F5. The whole song is transposed to fit best (an octave shift when
  that's as good), then notes still outside are moved by octaves. The converter says how many.
- **Timing** follows the clock, whatever the game's frame rate. Notes are rounded to ticks, 30 a second
  (`--tick-rate`). Each note and each gap before a repeated note reaches the game for at least a frame,
  so in a passage faster than the game's frames notes come a little late and the song catches up after.
- **Buttons.** `--layout game` (the default) is the game's standard ocarina controls; use
  `--layout performance` if you swapped them in the options. `--stick-half`, `--stick-full`,
  `--invert-stick` and `--bend-stick` tune the five notes played with a stick bend (B3, C4, G4, E5, F5).
- **The game's songs.** When a melody holds one of them note for note (Zelda's Lullaby, the warp songs,
  ...), the converter plays one of its notes with another fingering of the same pitch (its button, the
  D-pad down and the stick half up), so the game doesn't take it as that song, and says which note.
  `--allow-songs` plays them plainly, so the game may take them as its songs (warp songs move Link).
- **The playlist.** `--sd` also drops playlist lines whose `.oca` file is gone.

Run the converter's tests with `make test` (or `python -m unittest discover -s tests -t .`).

## Building

See [docs/BUILDING.md](docs/BUILDING.md). In short: devkitA64, then `make` (or `make dist`).

## Licence and credits

ocarinaMIDI is free software under the GNU General Public License, version 3 ([LICENSE](LICENSE)).

- The module's plumbing (`src/crt0.S`, `got.c`, `sys.c`, `sdfs.h`, the controller state layout,
  `lib/module.ld`, the Makefile) and its on-screen drawing (`src/nvn.c`, `overlay.c`, `font.c`) are adapted
  from **sloperinaGZ** (GPL-3; its contributors are listed in its CONTRIBUTORS.md), itself based on **gz**,
  glankk's practice ROM for Ocarina of Time (N64).
- The font is gz's, Press Start 2P by codeman38 (SIL Open Font License 1.1).
- No game files are included. You need your own copy of the game.
