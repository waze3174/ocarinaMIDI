"""The songs for the live test (docs/TESTING.md): writes them as MIDI files, or converts them straight onto the
emulator's SD card. Options it doesn't know (--stick-half, --invert-stick, --allow-songs, ...) go to midi2oca."""
import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import midi2oca  # noqa: E402
from smf_write import midi, notes_track  # noqa: E402

B3, C4, Cs4, D4, Ds4, E4, F4, Fs4, G4, Gs4, A4, As4, B4, C5, Cs5, D5, Ds5, E5, F5 = range(59, 78)
BEATS_PER_SECOND = 2  # at the files' tempo, 120 bpm


def sequence(pitches, length, gap=0.0, start=0.0):
    """Notes one after another, in seconds: (start, length, pitch)."""
    return [(start + i * (length + gap), length, pitch) for i, pitch in enumerate(pitches)]


# name: (title, notes in seconds). None of them holds one of the game's songs, except t8 on purpose (converted with
# an alternate fingering on one note unless --allow-songs is given).
SONGS = {
    "t1-naturals": ("t1 the five buttons", sequence([D4, F4, A4, B4, D5], 1, 0.5)),
    "t2-modifiers": ("t2 button + D-pad", sequence([Cs4, Ds4, E4, Fs4, Gs4, As4, C5, Cs5, Ds5], 1, 0.5)),
    "t3-stick": ("t3 stick bends, rising by semitones",
                 sequence([B3, C4, Cs4, D4], 1, 0.25)
                 + sequence([Fs4, G4, Gs4], 1, 0.25, start=6)
                 + sequence([Ds5, E5, F5], 1, 0.25, start=10.5)),
    "t4-chromatic": ("t4 B3 to F5 and back, legato",
                     sequence(list(range(B3, F5 + 1)) + list(range(E5, B3 - 1, -1)), 0.5)),
    "t5-sustain": ("t5 D4 held 2, 5, 10 s", [(0, 2, D4), (3, 5, D4), (9, 10, D4)]),
    "t6-rests": ("t6 A4 after rests of 2, 5, 10 s", [(0, 0.5, A4), (2.5, 0.5, A4), (8, 0.5, A4), (18.5, 0.5, A4)]),
    "t7-repeats": ("t7 A4 repeated, faster and faster",
                   sequence([A4] * 8, 0.25) + sequence([A4] * 8, 0.125, start=3) + sequence([A4] * 8, 1 / 16, start=5)),
    "t8-sarias-song": ("t8 Saria's Song (the game's own)", sequence([F4, A4, B4, F4, A4, B4], 0.5, 0.25)),
}


def song_midi(title, notes):
    beats = [(start * BEATS_PER_SECOND, length * BEATS_PER_SECOND, pitch) for start, length, pitch in notes]
    return midi(notes_track(beats, name=title))


def write_midi(folder):
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, (title, notes) in SONGS.items():
        path = folder / f"{name}.mid"
        path.write_bytes(song_midi(title, notes))
        paths.append(path)
    return paths


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    where = p.add_mutually_exclusive_group(required=True)
    where.add_argument("--sd", type=Path, help="the emulator's SD card folder (user/sdmc): convert and add to the playlist")
    where.add_argument("--midi", type=Path, help="only write the MIDI files to this folder")
    args, converter_options = p.parse_known_args(argv)
    if args.midi:
        if converter_options:
            p.error(f"converter options need --sd: {' '.join(converter_options)}")
        for path in write_midi(args.midi):
            print(path)
        return
    with tempfile.TemporaryDirectory() as folder:
        for path in write_midi(Path(folder)):
            midi2oca.main([str(path), "--sd", str(args.sd), "--transpose", "0", *converter_options])


if __name__ == "__main__":
    main()
