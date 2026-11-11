"""Convert a MIDI file into an ocarinaMIDI song (.oca) for Ocarina of Time's ocarina (Switch 2).

    python midi2oca.py song.mid --sd <emulator user folder>/sdmc      write it and add it to the playlist
    python midi2oca.py song.mid --out song.oca                         just write the file
    python midi2oca.py song.mid --list                                 show the tracks and channels

One note at a time: the highest of notes that start together, and a lower note only takes over when the
one sounding is about to end (legato). Channel 10 (drums) is dropped. The song is moved into the ocarina's
range (B3-F5) by one transposition for the whole song, then any notes still outside are moved by octaves.
Each note becomes the ocarina's buttons (docs/FORMAT.md), timed in ticks (30 a second by default).
Where the melody holds one of the game's own songs note for note, one of its notes is played with an alternate
fingering (same pitch), so the game doesn't take it as that song; --allow-songs keeps them as the game's songs.
"""
import argparse
import re
import struct
import sys
from dataclasses import dataclass, replace
from pathlib import Path

# --- the ocarina --------------------------------------------------------------------------------------
LOWEST, HIGHEST = 59, 77  # MIDI notes B3 and F5: the ocarina's 19 semitones
NATURAL_NOTES = (62, 65, 69, 71, 74)  # D4 F4 A4 B4 D5: what its five buttons play unmodified

# nn::hid::NpadButton bits
BTN = {name: 1 << bit for bit, name in enumerate(
    ("A", "B", "X", "Y", "LSTICK", "RSTICK", "L", "R", "ZL", "ZR", "PLUS", "MINUS",
     "DLEFT", "DUP", "DRIGHT", "DDOWN"))}

# The game's two button layouts (Options > Swap Ocarina-Playing Controls): the button for each natural note,
# and the buttons that raise or lower it a semitone.
LAYOUTS = {
    "game": {"notes": {62: "L", 65: "R", 69: "A", 71: "Y", 74: "X"}, "up": "DUP", "down": "DDOWN"},
    "performance": {"notes": {62: "R", 65: "B", 69: "A", 71: "Y", 74: "X"}, "up": "L", "down": "ZL"},
}

# Each semitone: (natural note, modifier step, stick step). The stick bends by whole semitones at half (1)
# and full (2) tilt; it's only used for the five notes a modifier can't reach.
NOTE_PLAN = {
    59: (62, -1, -2), 60: (62, -1, -1), 61: (62, -1, 0), 62: (62, 0, 0), 63: (62, 1, 0),
    64: (65, -1, 0), 65: (65, 0, 0), 66: (65, 1, 0), 67: (65, 1, 1),
    68: (69, -1, 0), 69: (69, 0, 0), 70: (69, 1, 0),
    71: (71, 0, 0), 72: (71, 1, 0),
    73: (74, -1, 0), 74: (74, 0, 0), 75: (74, 1, 0), 76: (74, 1, 1), 77: (74, 1, 2),
}

# The game's songs (the N64 melodies). Played with the ocarina out, one may set off its effect: warp songs move Link.
GAME_SONGS = {
    "Zelda's Lullaby": (71, 74, 69, 71, 74, 69),
    "Epona's Song": (74, 71, 69, 74, 71, 69),
    "Saria's Song": (65, 69, 71, 65, 69, 71),
    "Sun's Song": (69, 65, 74, 69, 65, 74),
    "Song of Time": (69, 62, 65, 69, 62, 65),
    "Song of Storms": (62, 65, 74, 62, 65, 74),
    "Minuet of Forest": (62, 74, 71, 69, 71, 69),
    "Bolero of Fire": (65, 62, 65, 62, 69, 65, 69, 65),
    "Serenade of Water": (62, 65, 69, 69, 71),
    "Requiem of Spirit": (62, 65, 62, 69, 65, 62),
    "Nocturne of Shadow": (71, 69, 69, 62, 71, 69, 65),
    "Prelude of Light": (74, 69, 74, 69, 71, 74),
}
# The game only takes a song from plain presses of the five buttons (docs/DESIGN.md), so a natural note played as
# its button + the lowering modifier + a one-semitone bend up sounds the same but breaks the match.
ALTERNATE_FINGERING = (-1, 1)  # (modifier step, stick step)

# --- the song file (src/song.h) --------------------------------------------------------------------------
SONG_MAGIC = b"OCA1"
SONG_VERSION = 1
TITLE_BYTES = 48
HEADER = struct.Struct("<4sHHII48s")
EVENT = struct.Struct("<IIhhhh")
SONGS_SUBDIR = Path("ocarinaMIDI") / "songs"
PLAYLIST = "playlist.txt"
MAX_FILE_NAME = 63  # the module's limit for a playlist entry
MAX_TICK_RATE = 0xFFFF  # a u16 in the header

DRUM_CHANNEL = 10
CHORD_WINDOW_S = 0.03  # notes starting this close together are one chord
LEGATO_S = 0.1  # a lower note may take over when the current one ends within this
LEAD_IN_TICKS = 2  # idle ticks before the first note, so the game sees every button released first
DEFAULT_TEMPO = 500000  # microseconds per quarter note, until a tempo event says otherwise
TRANSPOSE_SEARCH = range(-48, 49)


@dataclass(frozen=True)
class Note:
    start: float  # seconds
    end: float
    pitch: int
    channel: int  # 1-16
    track: int


@dataclass
class Track:
    name: str
    notes: list


# --- reading MIDI -----------------------------------------------------------------------------------------
class MidiError(ValueError):
    pass


def read_vlq(data, pos):
    value = 0
    for _ in range(4):
        if pos >= len(data):
            raise MidiError("file cut short")
        byte = data[pos]
        pos += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, pos
    raise MidiError("bad variable-length number")


def chunks(data):
    pos = 0
    while pos + 8 <= len(data):
        kind, length = data[pos:pos + 4], struct.unpack_from(">I", data, pos + 4)[0]
        yield kind, data[pos + 8:pos + 8 + length]
        pos += 8 + length


def parse_track(data):
    """The track's events as (tick, kind, values): ("on"/"off", channel, pitch), ("tempo", us), ("name", text)."""
    events, pos, tick, status = [], 0, 0, None
    while pos < len(data):
        delta, pos = read_vlq(data, pos)
        tick += delta
        if pos >= len(data):
            raise MidiError("file cut short")
        if data[pos] & 0x80:
            status = data[pos]
            pos += 1
        elif status is None or status >= 0xF0:
            raise MidiError("data byte without a status byte")
        if status == 0xFF:
            meta = data[pos]
            length, pos = read_vlq(data, pos + 1)
            body = data[pos:pos + length]
            pos += length
            if meta == 0x51 and length == 3:
                events.append((tick, "tempo", int.from_bytes(body, "big")))
            elif meta == 0x03:
                events.append((tick, "name", body.decode("utf-8", "replace")))
            elif meta == 0x2F:
                break
            status = None
            continue
        if status in (0xF0, 0xF7):
            length, pos = read_vlq(data, pos)
            pos += length
            status = None
            continue
        if status >= 0xF0:
            raise MidiError(f"unexpected system message 0x{status:02X}")
        kind, channel = status & 0xF0, (status & 0x0F) + 1
        size = 1 if kind in (0xC0, 0xD0) else 2
        values = data[pos:pos + size]
        if len(values) < size:
            raise MidiError("file cut short")
        pos += size
        if kind == 0x90 and values[1] > 0:
            events.append((tick, "on", channel, values[0]))
        elif kind in (0x80, 0x90):
            events.append((tick, "off", channel, values[0]))
    return events, tick


def tick_clock(tempos, ticks_per_quarter):
    """A function from tick to seconds, through the tempo changes [(tick, us per quarter)]."""
    points, seconds, last_tick, tempo = [], 0.0, 0, DEFAULT_TEMPO
    for tick, new_tempo in sorted(tempos):
        seconds += (tick - last_tick) * tempo / 1e6 / ticks_per_quarter
        points.append((tick, seconds, new_tempo))
        last_tick, tempo = tick, new_tempo

    def to_seconds(tick):
        base_tick, base_seconds, current = 0, 0.0, DEFAULT_TEMPO
        for point_tick, point_seconds, point_tempo in points:
            if point_tick > tick:
                break
            base_tick, base_seconds, current = point_tick, point_seconds, point_tempo
        return base_seconds + (tick - base_tick) * current / 1e6 / ticks_per_quarter

    return to_seconds


def read_midi(data):
    """The file's tracks, with their notes in seconds."""
    if data[:4] != b"MThd":
        raise MidiError("not a MIDI file")
    header = next(body for kind, body in chunks(data) if kind == b"MThd")
    _, _, division = struct.unpack_from(">HHH", header)
    if division & 0x8000:
        raise MidiError("SMPTE timing isn't supported")
    parsed = [parse_track(body) for kind, body in chunks(data) if kind == b"MTrk"]
    tempos = [(tick, values[0]) for events, _ in parsed for tick, kind, *values in events if kind == "tempo"]
    to_seconds = tick_clock(tempos, division)
    tracks = []
    for index, (events, end_tick) in enumerate(parsed):
        sounding, notes, name = {}, [], ""
        for tick, kind, *values in events:
            if kind == "name" and not name:
                name = values[0].strip()
            elif kind == "on":
                sounding.setdefault(tuple(values), []).append(tick)
            elif kind == "off" and sounding.get(tuple(values)):
                start = sounding[tuple(values)].pop(0)
                notes.append(Note(to_seconds(start), to_seconds(tick), values[1], values[0], index))
        for (channel, pitch), starts in sounding.items():
            notes += [Note(to_seconds(start), to_seconds(end_tick), pitch, channel, index) for start in starts]
        tracks.append(Track(name, sorted(notes, key=lambda n: (n.start, -n.pitch))))
    return tracks


# --- picking the melody ------------------------------------------------------------------------------------
def select_notes(tracks, track=None, channel=None):
    notes = []
    for index, t in enumerate(tracks):
        if track is not None and index != track:
            continue
        notes += [n for n in t.notes if (n.channel == channel if channel else n.channel != DRUM_CHANNEL)]
    return sorted((n for n in notes if n.end > n.start), key=lambda n: (n.start, -n.pitch))


def chord_tops(notes):
    """The highest note of each group of notes that start within CHORD_WINDOW_S of the group's first."""
    tops, group_start = [], None
    for note in notes:
        if group_start is not None and note.start - group_start <= CHORD_WINDOW_S:
            if note.pitch > tops[-1].pitch:
                tops[-1] = note
            continue
        tops.append(note)
        group_start = note.start
    return tops


def melody(notes):
    """One note at a time: see the module docstring."""
    picked = []
    for note in chord_tops(notes):
        if picked and note.start < picked[-1].end:
            current = picked[-1]
            if note.pitch < current.pitch and current.end - note.start > LEGATO_S:
                continue
            picked[-1] = replace(current, end=note.start)
        picked.append(note)
    return picked


def out_of_range(pitches, shift):
    return sum(1 for p in pitches if not LOWEST <= p + shift <= HIGHEST)


def best_transpose(pitches):
    """Fewest notes left outside the range; then an octave shift (keeps the key); then the smallest."""
    return min(TRANSPOSE_SEARCH, key=lambda s: (out_of_range(pitches, s), s % 12 != 0, abs(s)))


def fold_into_range(pitch):
    while pitch < LOWEST:
        pitch += 12
    while pitch > HIGHEST:
        pitch -= 12
    return pitch


def fit_range(notes, transpose=None):
    """The notes moved into the ocarina's range, the transposition used and how many had to be folded."""
    shift = best_transpose([n.pitch for n in notes]) if transpose is None else transpose
    folded = out_of_range([n.pitch for n in notes], shift)
    return [replace(n, pitch=fold_into_range(n.pitch + shift)) for n in notes], shift, folded


@dataclass(frozen=True)
class SongWindow:
    song: str
    first: int  # note indices, inclusive
    last: int


def game_song_windows(pitches):
    """Each place where these pitches play one of the game's songs, note for note."""
    pitches = tuple(pitches)
    return [SongWindow(name, i, i + len(song) - 1) for name, song in GAME_SONGS.items()
            for i in range(len(pitches) - len(song) + 1) if pitches[i:i + len(song)] == song]


def notes_to_alter(windows):
    """The fewest notes that put one in every window: going by where the windows end, the last note of each
    window that doesn't hold one yet."""
    altered = []
    for window in sorted(windows, key=lambda w: w.last):
        if not altered or altered[-1] < window.first:
            altered.append(window.last)
    return altered


# --- from notes to controller input -------------------------------------------------------------------------
@dataclass(frozen=True)
class Stick:
    half: int = 16384  # tilt for one semitone
    full: int = 32767  # tilt for two
    sign: int = 1  # -1 if tilting down raises the pitch
    side: str = "left"


@dataclass(frozen=True)
class Input:
    buttons: int
    lx: int = 0
    ly: int = 0
    rx: int = 0
    ry: int = 0


RELEASED = Input(0)


def stick_tilt(bend, stick):
    magnitude = {0: 0, 1: stick.half, 2: stick.full}[abs(bend)]
    return stick.sign * magnitude * (-1 if bend < 0 else 1)


def note_input(pitch, layout, stick, alternate=False):
    """The buttons and stick for one semitone (alternate: a natural note's alternate fingering); also its natural
    note's button, to spot re-presses."""
    natural, modifier, bend = NOTE_PLAN[pitch]
    if alternate:
        if (modifier, bend) != (0, 0):
            raise ValueError(f"note {pitch} isn't a natural note: it has no alternate fingering")
        modifier, bend = ALTERNATE_FINGERING
    names = LAYOUTS[layout]
    button = BTN[names["notes"][natural]]
    buttons = button | (BTN[names["up" if modifier > 0 else "down"]] if modifier else 0)
    tilt = stick_tilt(bend, stick)
    sticks = {"ly": tilt} if stick.side == "left" else {"ry": tilt}
    return Input(buttons, **sticks), button


def fingerings(notes, layout, stick, altered=()):
    """Each note's (Input, natural button); the notes at the indices in `altered` with the alternate fingering."""
    altered = set(altered)
    return [note_input(note.pitch, layout, stick, i in altered) for i, note in enumerate(notes)]


@dataclass
class Segment:
    start: int  # ticks
    end: int
    input: Input
    button: int  # the natural note's button


def segments(notes, fingered, tick_rate, min_hold):
    """Tick spans for the notes, played as `fingered` (from fingerings): rounded, never overlapping, at least
    min_hold long, and with one released tick between two notes on the same button (so the game sees it
    pressed again)."""
    spans = []
    offset = None
    for note, (played, button) in zip(notes, fingered):
        start, end = round(note.start * tick_rate), round(note.end * tick_rate)
        if offset is None:
            offset = start - LEAD_IN_TICKS
        spans.append(Segment(start - offset, end - offset, played, button))
    for i, span in enumerate(spans):
        if i:
            previous = spans[i - 1]
            span.start = max(span.start, previous.end)
            if span.button == previous.button and span.start == previous.end:
                if previous.end - previous.start > min_hold:
                    previous.end -= 1
                else:
                    span.start += 1
        span.end = max(span.end, span.start + min_hold)
        if i + 1 < len(spans) and spans[i + 1].start < span.end:
            span.end = max(spans[i + 1].start, span.start + min_hold)
    return spans


def events(spans):
    """(tick, Input) changes, ending released; and the song's length in ticks."""
    changes = []
    for i, span in enumerate(spans):
        changes.append((span.start, span.input))
        next_start = spans[i + 1].start if i + 1 < len(spans) else None
        if next_start != span.end:
            changes.append((span.end, RELEASED))
    total = changes[-1][0] + 1 if changes else 1
    return changes, total


# --- writing ----------------------------------------------------------------------------------------------------
def encode_title(title):
    raw = title.encode("utf-8")[:TITLE_BYTES - 1]
    return raw.decode("utf-8", "ignore").encode("utf-8")


def song_bytes(title, tick_rate, changes, total_ticks):
    out = [HEADER.pack(SONG_MAGIC, SONG_VERSION, tick_rate, len(changes), total_ticks, encode_title(title))]
    out += [EVENT.pack(tick, i.buttons, i.lx, i.ly, i.rx, i.ry) for tick, i in changes]
    return b"".join(out)


def file_name(stem):
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_") or "song"
    return name[:MAX_FILE_NAME - len(".oca")] + ".oca"


def is_song_line(line):
    return bool(line.strip()) and not line.strip().startswith("#")


def add_to_playlist(songs_dir, name):
    """Adds the song once, and drops the songs whose file is gone. Returns the names dropped."""
    playlist = songs_dir / PLAYLIST
    lines = playlist.read_text(encoding="utf-8").splitlines() if playlist.exists() else []
    gone = [line.strip() for line in lines if is_song_line(line) and not (songs_dir / line.strip()).is_file()]
    lines = [line for line in lines if not is_song_line(line) or line.strip() not in gone]
    if name not in (line.strip() for line in lines):
        lines.append(name)
    playlist.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    return gone


# --- the command line --------------------------------------------------------------------------------------------
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def pitch_name(pitch):
    return f"{NOTE_NAMES[pitch % 12]}{pitch // 12 - 1}"


def song_time(seconds):
    minutes, rest = divmod(seconds, 60)
    return f"{int(minutes)}:{rest:04.1f}"


def alternate_fingering_text(pitch, layout, stick):
    names = LAYOUTS[layout]
    modifier, bend = ALTERNATE_FINGERING
    tilt = "up" if stick_tilt(bend, stick) > 0 else "down"
    return f"{names['notes'][pitch]} + {names['up' if modifier > 0 else 'down']} + {stick.side} stick half {tilt}"


def report_game_songs(windows, altered, notes, layout, stick):
    """Each place the melody plays one of the game's songs: the note played differently, or a warning."""
    for window in windows:
        where = (f"{window.song} at notes {window.first + 1}-{window.last + 1} "
                 f"(from {song_time(notes[window.first].start - notes[0].start)})")
        changed = next((i for i in altered if window.first <= i <= window.last), None)
        if changed is None:
            print(f"warning: it plays {where}; the game may take it as that song (warp songs move Link)",
                  file=sys.stderr)
            continue
        pitch = notes[changed].pitch
        print(f"{where}: note {changed + 1} ({pitch_name(pitch)}) is played as "
              f"{alternate_fingering_text(pitch, layout, stick)}, the same pitch, so the game won't take it as the song")


def list_tracks(tracks):
    for index, track in enumerate(tracks):
        channels = sorted({n.channel for n in track.notes})
        span = f"{min(n.pitch for n in track.notes)}-{max(n.pitch for n in track.notes)}" if track.notes else "-"
        print(f"track {index}: {track.name or '(no name)'}: {len(track.notes)} notes, channels {channels}, pitches {span}")


def parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("midi", type=Path)
    where = p.add_mutually_exclusive_group()
    where.add_argument("--sd", type=Path, help="the emulator's SD card folder (user/sdmc); adds the song to the playlist")
    where.add_argument("--out", type=Path, help="write the .oca file here instead")
    where.add_argument("--list", action="store_true", help="show the tracks and channels, then stop")
    p.add_argument("--track", type=int, help="only this track (numbers from --list)")
    p.add_argument("--channel", type=int, choices=range(1, 17), metavar="1-16", help="only this channel")
    p.add_argument("--transpose", type=int, help="semitones for the whole song (default: the best fit)")
    p.add_argument("--tick-rate", type=int, default=30, help="the timing's resolution, ticks a second (default 30)")
    p.add_argument("--min-hold", type=int, default=1, help="shortest note, in ticks (default 1)")
    p.add_argument("--layout", choices=sorted(LAYOUTS), default="game", help="the game's ocarina button layout")
    p.add_argument("--title", help="shown in the log (default: the first track name, or the file name)")
    p.add_argument("--stick-half", type=int, default=Stick.half, help="stick tilt for a one-semitone bend")
    p.add_argument("--stick-full", type=int, default=Stick.full, help="stick tilt for a two-semitone bend")
    p.add_argument("--invert-stick", action="store_true", help="tilt down to raise the pitch")
    p.add_argument("--bend-stick", choices=("left", "right"), default="left", help="the stick that bends the pitch")
    p.add_argument("--allow-songs", action="store_true",
                   help="play the game's songs plainly, so the game may take them as its songs (by default one "
                        "note of each is played with an alternate fingering)")
    args = p.parse_args(argv)
    if not (args.sd or args.out or args.list):
        p.error("give --sd, --out or --list")
    if not 1 <= args.tick_rate <= MAX_TICK_RATE or args.min_hold < 1:
        p.error(f"--tick-rate must be 1 to {MAX_TICK_RATE}, and --min-hold at least 1")
    return args


def main(argv=None):
    args = parse_args(argv)
    try:
        tracks = read_midi(args.midi.read_bytes())
    except (OSError, MidiError) as error:
        sys.exit(f"{args.midi}: {error}")
    if args.list:
        list_tracks(tracks)
        return
    picked = melody(select_notes(tracks, args.track, args.channel))
    if not picked:
        sys.exit("no notes left: check --track and --channel (see --list)")
    fitted, shift, folded = fit_range(picked, args.transpose)
    stick = Stick(args.stick_half, args.stick_full, -1 if args.invert_stick else 1, args.bend_stick)
    windows = game_song_windows(n.pitch for n in fitted)
    altered = [] if args.allow_songs else notes_to_alter(windows)
    fingered = fingerings(fitted, args.layout, stick, altered)
    changes, total = events(segments(fitted, fingered, args.tick_rate, args.min_hold))
    title = args.title or next((t.name for t in tracks if t.name), "") or args.midi.stem
    data = song_bytes(title, args.tick_rate, changes, total)
    if args.sd:
        songs_dir = args.sd / SONGS_SUBDIR
        songs_dir.mkdir(parents=True, exist_ok=True)
        path = songs_dir / file_name(args.midi.stem)
        path.write_bytes(data)
        for gone in add_to_playlist(songs_dir, path.name):
            print(f"playlist: dropped {gone}, its file is gone")
    else:
        path = args.out
        path.write_bytes(data)
    print(f"{title}: {len(picked)} notes, transposed {shift:+d}, {folded} folded by octaves, "
          f"{total / args.tick_rate:.1f} s, {len(changes)} events -> {path}")
    report_game_songs(windows, altered, fitted, args.layout, stick)


if __name__ == "__main__":
    main()
