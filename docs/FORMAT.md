# Song files (.oca)

Written by `tools/midi2oca.py`, read by `src/songs.c` (`src/song.h`). Little endian.

## Header (64 bytes)

| Offset | Type | |
|---|---|---|
| 0 | char[4] | `OCA1` |
| 4 | u16 | version: 1 |
| 6 | u16 | ticks per second: the events' time unit (the converter's `--tick-rate`, 30 by default) |
| 8 | u32 | event count |
| 12 | u32 | length, in ticks |
| 16 | char[48] | title, UTF-8, NUL padded |

## Events (16 bytes each, sorted by tick)

| Offset | Type | |
|---|---|---|
| 0 | u32 | tick this input starts at (0 = when playback starts) |
| 4 | u32 | buttons, `nn::hid::NpadButton` bits (A = bit 0 ... D-pad Down = bit 15) |
| 8 | s16 | left stick X |
| 10 | s16 | left stick Y |
| 12 | s16 | right stick X |
| 14 | s16 | right stick Y |

Each event's input holds until the next event. The converter starts with two idle ticks and ends with
a release, one tick before the length.

## Playback

The module plays by the clock (`src/player.c`). At each game frame it gives the game the next event
once that event's time has come, and never more than one event per frame, so every press and every
release reaches the game for at least one frame. Events that come due faster than the game's frames
(a dense passage at a low frame rate) are given late, in order, and the song catches up at the next
gap. The song ends a frame after its last event, once its length has passed. A wait of more than
250 ms between two frames (loading, a hitch) pauses the song for that long instead of rushing through
what it missed.

The converter keeps each note at least one tick long and puts one released tick between two notes on
the same button; the one-event-per-frame rule makes each of those at least one game frame.

## History

0.1 counted game frames: the field at offset 6 was the frame rate the converter assumed, and offsets 0
and 12 counted frames, so the tempo followed the game's frame rate. 0.2 reads the same fields as ticks,
with the same layout and version, so files from 0.1 load and play at the tempo they were made for
(30 a second, unless they were converted with `--fps`).

## Playlist

`ocarinaMIDI/songs/playlist.txt` on the SD card: one file name per line (in the same folder), up to 64
songs and 63 characters each. Blank lines, lines starting with `#` and files that aren't there are
skipped. The converter adds each song it writes with `--sd`, and drops the lines whose file is gone.
