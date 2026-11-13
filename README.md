# ocarinaMIDI

Plays MIDI songs on the ocarina in **The Legend of Zelda: Ocarina of Time (Switch 2)**. A small game
module presses the ocarina's own buttons for you, so the game plays the notes with its own sound,
animation and pitch bend. Songs are converted on the PC first (`tools/midi2oca.py`).

It runs next to [sloperinaGZ](https://github.com/PracticeROM/sloperina) or on its own.

## What's new in 0.3.0

The song list is drawn in the game's own menu style, as sloperinaGZ's menu is in its "game" style: the
game's UI font (Clarimo UD PE), its near-black info box, a gold title over a hairline, and the selected
song in bold white on a light band. The module reads the font and the UI shader from your copy of the
game while it runs; nothing of them is in this repository or the release. If it can't (the files aren't
found, or there is no memory for them), the song list falls back to the plain panel of 0.2.0, so it still
shows. sloperinaGZ's selection frame (the game's cursor pictures) is not drawn: the plain band stands in.

Status: 0.2.0 was tested in an emulator on game version 1.1.1, next to sloperinaGZ: songs keep their tempo
(a 59 s stretch played in exactly 59 s) and the song list shows when switching songs. 0.3.0's game-style
song list has not been tried in game yet, nor has avoiding the game's own songs; 1.0.0 and real consoles are
untested. See [docs/TESTING.md](docs/TESTING.md).

## What you need

- The game, version 1.0.0 or 1.1.1 (the module uses no game offsets, so later versions should work too).
- An emulator with exefs mods (Lichii, Eden), or a console with LayeredFS.
- Python 3 to convert songs.

## Install (Lichii)

The emulator's user folder is `user\` next to `lichii.exe` (portable) or `%APPDATA%\lichii`.

1. Copy `subsdk8` to `user\load\0400486024DEC000\ocarinaMIDI\exefs\subsdk8`.
   sloperinaGZ stays where it is (`...\sloperinaGZ\exefs\subsdk9` plus its `.ips`): the two use
   different slots and Lichii loads both.
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
file is gone are left out. The first time you switch songs, the module reads the game's font and shader,
which can take a moment.

While a song plays, the game only sees the song's input; your controller is back when it ends or you stop
it. While R3 is held the game doesn't see the D-pad. The module also logs what it does in the emulator's
log, on lines starting `ocarinaMIDI:` (Lichii logs them under `Debug.Emulated`, at the default level).

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
  `lib/module.ld`, the Makefile) and its on-screen drawing (`src/nvn.c`, `slots.c`, `overlay_cpu.c`,
  `font.c`) are adapted from **sloperinaGZ** (GPL-3; its contributors are listed in its CONTRIBUTORS.md),
  itself based on **gz**, glankk's practice ROM for Ocarina of Time (N64).
- The game-style song list (0.3.0) is ported from sloperinaGZ master 8c3a940636 (release 0.0.5): reading
  the game's files and fonts (`gamefile.c`, `zstd.c`, `gamefont.c`, `uishader.c`), drawing with the game's
  UI shader (`gpuui.c`) and the layout of its menu in the game style (`gameui.c`, after its
  `nativeui.c`). `src/third_party` holds [stb_truetype](https://github.com/nothings/stb) (public domain)
  and zstd's educational decoder (BSD or GPLv2, Meta Platforms), both as sloperinaGZ ships them.
- The plain panel's font is gz's, Press Start 2P by codeman38 (SIL Open Font License 1.1).
- No game files are included. You need your own copy of the game; the module reads its font and shader
  from it at run time.
