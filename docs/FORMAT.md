# Song files (.oca)

Written by `tools/midi2oca.py`, read by `src/songs.c` (`src/song.h`). Little endian.

## Header (64 bytes)

| Offset | Type | |
|---|---|---|
| 0 | char[4] | `OCA1` |
| 4 | u16 | version: 1 |
| 6 | u16 | the frame rate the converter assumed (shown in the log) |
| 8 | u32 | event count |
| 12 | u32 | total frames: playback stops when this many frames have passed |
| 16 | char[48] | title, UTF-8, NUL padded |

## Events (16 bytes each, sorted by frame)

| Offset | Type | |
|---|---|---|
| 0 | u32 | frame of playback this input starts at (0 = the frame playback starts) |
| 4 | u32 | buttons, `nn::hid::NpadButton` bits (A = bit 0 ... D-pad Down = bit 15) |
| 8 | s16 | left stick X |
| 10 | s16 | left stick Y |
| 12 | s16 | right stick X |
| 14 | s16 | right stick Y |

Each event's input holds until the next event. The converter starts with two idle frames and ends with
a release, one frame before the total.

## Playlist

`ocarinaMIDI/songs/playlist.txt` on the SD card: one file name per line (in the same folder), up to 64
songs and 63 characters each. Blank lines and lines starting with `#` are skipped. The converter adds
each song it writes with `--sd`.
