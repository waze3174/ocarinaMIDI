# ocarinaMIDI

Plays MIDI songs on the ocarina in **The Legend of Zelda: Ocarina of Time (Switch 2)**. A small game
module presses the ocarina's own buttons for you, so the game plays the notes with its own sound,
animation and pitch bend. Songs are converted on the PC first (`tools/midi2oca.py`).

It runs next to [sloperinaGZ](https://github.com/PracticeROM/sloperina) or on its own. Status: written, not yet tested in the
game. See [docs/TESTING.md](docs/TESTING.md).

## What you need

- The game, version 1.0.0 or 1.1.1 (the module uses no game offsets, so later versions should work too).
- An emulator with exefs mods (Ryuchii, Lichii, Eden), or a console with LayeredFS.
- Python 3 to convert songs.

## Install (Ryuchii)

The emulator's user folder is `user\` next to `ryuchii.exe` (portable) or `%APPDATA%\ryuchii`.

1. Copy `subsdk8` to `user\load\0400486024DEC000\ocarinaMIDI\exefs\subsdk8`.
   sloperinaGZ stays where it is (`...\sloperinaGZ\exefs\subsdk9` plus its `.ips`): the two use
   different slots and Ryuchii loads both.
2. Convert a song onto the emulator's SD card:

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

While a song plays, the game only sees the song's input; your controller is back when it ends or you stop
it. While R3 is held the game doesn't see the D-pad. The song names show in the emulator's log, on lines
starting `ocarinaMIDI:` (Ryuchii logs them under `Debug.Emulated`, at the default level).

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
- **Timing** is counted in game frames: `--fps` (default 30) is the frame rate the song assumes. If the
  game runs slower the song slows down with it; no note is skipped. The log shows the measured rate
  when a song stops.
- **Buttons.** `--layout game` (the default) is the game's standard ocarina controls; use
  `--layout performance` if you swapped them in the options. `--stick-half`, `--stick-full`,
  `--invert-stick` and `--bend-stick` tune the five notes played with a stick bend (B3, C4, G4, E5, F5).
- **The game's songs.** The converter warns when a melody holds one of them (Zelda's Lullaby, the warp
  songs, ...) note for note: played with the ocarina out, the game may take it as that song.

Run the converter's tests with `make test` (or `python -m unittest discover -s tests -t .`).

## Building

See [docs/BUILDING.md](docs/BUILDING.md). In short: devkitA64, then `make` (or `make dist`).

## Licence and credits

ocarinaMIDI is free software under the GNU General Public License, version 3 ([LICENSE](LICENSE)).

- The module's plumbing (`src/crt0.S`, `got.c`, `sys.c`, `sdfs.h`, the controller state layout,
  `lib/module.ld`, the Makefile) is adapted from **sloperinaGZ** (GPL-3; its contributors are listed in its CONTRIBUTORS.md),
  itself based on **gz**, glankk's practice ROM for Ocarina of Time (N64).
- No game files are included. You need your own copy of the game.
