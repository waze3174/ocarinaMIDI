"""Convert a MIDI file into an ocarinaMIDI song (.oca) for Ocarina of Time's ocarina (Switch 2).

    python midi2oca.py song.mid --sd <emulator user folder>/sdmc      write it and add it to the playlist
    python midi2oca.py song.mid --out song.oca                         just write the file
    python midi2oca.py song.mid --list                                 show its parts (tracks and channels)
    python midi2oca.py song.mid --sd <sdmc> --pick                     ask which part is the melody

One note at a time: the highest of notes that start together, and a lower note only takes over when the
one sounding is about to end (legato). Channel 10 (drums) is dropped. All the other parts are used unless one
is picked (--track, --channel, or --pick to choose from a list with the likely melody marked). The song is moved
into the ocarina's range (B3-F5) by one transposition for the whole song, then any notes still outside are moved
by octaves. Each note becomes the ocarina's buttons (docs/FORMAT.md), timed in ticks (30 a second by default):
each starts on its own tick, and where notes come too fast for the ticks some are left out, so none comes late.
Where the melody holds one of the game's own songs note for note, one of its notes is played with an alternate
fingering (same pitch), so the game doesn't take it as that song; --allow-songs keeps them as the game's songs.
"""
import argparse
import math
import re
import struct
import sys
from dataclasses import dataclass, field, replace
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
    programs: dict = field(default_factory=dict)  # channel: its first program change (instrument) in this track


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
    """The track's events as (tick, kind, values): ("on"/"off", channel, pitch), ("program", channel, number),
    ("tempo", us), ("name", text)."""
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
        elif kind == 0xC0:
            events.append((tick, "program", channel, values[0]))
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
        sounding, notes, name, programs = {}, [], "", {}
        for tick, kind, *values in events:
            if kind == "name" and not name:
                name = values[0].strip()
            elif kind == "program":
                programs.setdefault(*values)
            elif kind == "on":
                sounding.setdefault(tuple(values), []).append(tick)
            elif kind == "off" and sounding.get(tuple(values)):
                start = sounding[tuple(values)].pop(0)
                notes.append(Note(to_seconds(start), to_seconds(tick), values[1], values[0], index))
        for (channel, pitch), starts in sounding.items():
            notes += [Note(to_seconds(start), to_seconds(end_tick), pitch, channel, index) for start in starts]
        tracks.append(Track(name, sorted(notes, key=lambda n: (n.start, -n.pitch)), programs))
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


# --- choosing the melody's part ----------------------------------------------------------------------------------
# General MIDI's instrument families, eight programs each
INSTRUMENT_FAMILIES = ("piano", "chromatic percussion", "organ", "guitar", "bass", "strings", "ensemble", "brass",
                       "reed", "pipe", "synth lead", "synth pad", "synth effects", "ethnic", "percussive",
                       "sound effects")
# The likely melody: a part that plays one note at a time through much of the song, above middle C and inside the
# ocarina's range scores highest; its name and instrument then weigh the score up or down.
MELODY_NAMES = re.compile(r"melod|vocal|voice|vox|lead|solo|sing|tune", re.IGNORECASE)
ACCOMPANIMENT_NAMES = re.compile(r"bass|drum|perc|chord|pad|string|accomp|rhythm|harmon|backing|arp", re.IGNORECASE)
MELODY_INSTRUMENTS = {"synth lead", "reed", "pipe", "brass"}
MELODY_NAME_WEIGHT, MELODY_INSTRUMENT_WEIGHT, ACCOMPANIMENT_WEIGHT = 2.0, 1.3, 0.3
MIDDLE_C = 60
PITCH_WEIGHTS = ((MIDDLE_C, 1.0), (MIDDLE_C - 12, 0.5))  # (median pitch at least, weight)
LOW_PITCH_WEIGHT = 0.15
CHORDS_BELOW = 0.75  # shown as playing chords when the melody keeps fewer of its notes than this


@dataclass(frozen=True)
class Part:
    """One track's notes on one channel: what the melody is chosen from."""
    track: int
    channel: int
    name: str
    instrument: str  # the General MIDI family of its first program change, or ""
    notes: tuple


def parts(tracks):
    """Each track's notes on each channel but the drums', in file order."""
    found = []
    for index, track in enumerate(tracks):
        for channel in sorted({n.channel for n in track.notes} - {DRUM_CHANNEL}):
            program = track.programs.get(channel)
            instrument = INSTRUMENT_FAMILIES[program // 8] if program is not None else ""
            notes = tuple(select_notes(tracks, index, channel))
            if notes:
                found.append(Part(index, channel, track.name, instrument, notes))
    return found


def melody_score(part, song_seconds):
    """How much a part looks like the melody (see MELODY_NAMES)."""
    line = melody(part.notes)
    playing = min(1.0, sum(n.end - n.start for n in line) / song_seconds)
    in_range = 1 - fit_range(line)[2] / len(line)
    median = sorted(n.pitch for n in line)[len(line) // 2]
    height = next((weight for lowest, weight in PITCH_WEIGHTS if median >= lowest), LOW_PITCH_WEIGHT)
    score = math.sqrt(len(line) / len(part.notes)) * playing * in_range * height
    if MELODY_NAMES.search(part.name):
        score *= MELODY_NAME_WEIGHT
    if part.instrument in MELODY_INSTRUMENTS:
        score *= MELODY_INSTRUMENT_WEIGHT
    if ACCOMPANIMENT_NAMES.search(part.name) or part.instrument == "bass":
        score *= ACCOMPANIMENT_WEIGHT
    return score


def likely_melody(found):
    """The part that looks most like the melody."""
    song_seconds = max(n.end for part in found for n in part.notes)
    return max(found, key=lambda part: melody_score(part, song_seconds))


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


RELEASED_TICKS = 1  # between two notes on the same button, so the game sees it pressed again


def same_button(a, b):
    """True if two notes are played on the same button (the same natural note, in either layout)."""
    return NOTE_PLAN[a.pitch][0] == NOTE_PLAN[b.pitch][0]


def ticks_between(previous, note, min_hold):
    """The fewest ticks from one note's start to the next one's."""
    return min_hold + (RELEASED_TICKS if same_button(previous, note) else 0)


def in_time(notes, tick_rate, min_hold):
    """The notes that can each start on their own tick: a note needs min_hold ticks before the next starts, and one
    released tick more if they share a button (so the game sees it pressed again). Of two notes too close for that,
    the shorter is left out, so a passage too fast for the ticks thins out instead of making the rest of the song
    late."""
    kept = []
    for note in notes:
        start = round(note.start * tick_rate)
        while kept and start < round(kept[-1].start * tick_rate) + ticks_between(kept[-1], note, min_hold):
            if kept[-1].end - kept[-1].start >= note.end - note.start:
                break
            kept.pop()
        else:
            kept.append(note)
    return kept


@dataclass
class Segment:
    start: int  # ticks
    end: int
    input: Input
    button: int  # the natural note's button


def segments(notes, fingered, tick_rate, min_hold):
    """Tick spans for notes from in_time, played as `fingered` (from fingerings): each from its own rounded tick,
    at least min_hold long, and ending before the next, with one released tick between two notes on the same button
    (so the game sees it pressed again)."""
    offset = round(notes[0].start * tick_rate) - LEAD_IN_TICKS if notes else 0
    spans = []
    for note, (played, button) in zip(notes, fingered):
        start = round(note.start * tick_rate) - offset
        spans.append(Segment(start, max(round(note.end * tick_rate) - offset, start + min_hold), played, button))
    for span, following in zip(spans, spans[1:]):
        span.end = min(span.end, following.start - (RELEASED_TICKS if following.button == span.button else 0))
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


LIKELY = "   <- likely the melody"


def describe_part(part):
    pitches = [n.pitch for n in part.notes]
    chords = len(melody(part.notes)) < CHORDS_BELOW * len(part.notes)
    words = [f"track {part.track}, channel {part.channel}", part.name or "(no name)", part.instrument,
             f"{len(part.notes)} note{'' if len(part.notes) == 1 else 's'}",
             f"{pitch_name(min(pitches))} to {pitch_name(max(pitches))}",
             "chords" if chords else ""]
    return ", ".join(word for word in words if word)


def list_parts(found):
    guess = likely_melody(found) if found else None
    for part in found:
        print(describe_part(part) + (LIKELY if part is guess else ""))


def ask_for_part(found, title, ask=input):
    """Lists the parts and asks which one is the melody (Enter, or no answer at all, takes the likely one). Returns
    the part, or None for all of them together."""
    guess = likely_melody(found)
    default = found.index(guess) + 1
    print(f"{title}: which part is the melody?")
    print("   0  all parts together (the highest note at each moment)")
    for number, part in enumerate(found, 1):
        print(f"  {number:2}  {describe_part(part)}" + (LIKELY if part is guess else ""))
    while True:
        try:
            answer = ask(f"Number, or Enter for {default}: ").strip()
        except EOFError:
            print()
            answer = ""
        if not answer:
            return guess
        if answer.isdigit() and int(answer) <= len(found):
            return found[int(answer) - 1] if int(answer) else None
        print(f"Type a number from 0 to {len(found)}.")


def parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("midi", type=Path)
    where = p.add_mutually_exclusive_group()
    where.add_argument("--sd", type=Path, help="the emulator's SD card folder (user/sdmc); adds the song to the playlist")
    where.add_argument("--out", type=Path, help="write the .oca file here instead")
    where.add_argument("--list", action="store_true", help="show the parts (tracks and channels), then stop")
    p.add_argument("--track", type=int, help="only this track (numbers from --list)")
    p.add_argument("--channel", type=int, choices=range(1, 17), metavar="1-16", help="only this channel")
    p.add_argument("--pick", action="store_true",
                   help="list the parts and ask which is the melody, unless --track or --channel is given (Enter, "
                        "or no answer, takes the likely melody)")
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
        list_parts(parts(tracks))
        return
    track, channel = args.track, args.channel
    if args.pick and track is None and channel is None:
        found = parts(tracks)
        part = ask_for_part(found, args.midi.name) if len(found) > 1 else None
        if part:
            track, channel = part.track, part.channel
            print(f"melody: {describe_part(part)} (--track {track} --channel {channel})")
        elif len(found) > 1:
            print("melody: all parts together")
    picked = melody(select_notes(tracks, track, channel))
    if not picked:
        sys.exit("no notes left: check --track and --channel (see --list)")
    fitted, shift, folded = fit_range(picked, args.transpose)
    played = in_time(fitted, args.tick_rate, args.min_hold)
    stick = Stick(args.stick_half, args.stick_full, -1 if args.invert_stick else 1, args.bend_stick)
    windows = game_song_windows(n.pitch for n in played)
    altered = [] if args.allow_songs else notes_to_alter(windows)
    fingered = fingerings(played, args.layout, stick, altered)
    changes, total = events(segments(played, fingered, args.tick_rate, args.min_hold))
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
    too_close = len(fitted) - len(played)
    print(f"{title}: {len(played)} notes" + (f" ({too_close} left out, too close together)" if too_close else "")
          + f", transposed {shift:+d}, {folded} folded by octaves, {total / args.tick_rate:.1f} s, "
          f"{len(changes)} events -> {path}")
    report_game_songs(windows, altered, played, args.layout, stick)


if __name__ == "__main__":
    main()
