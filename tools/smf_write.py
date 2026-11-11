"""Writes small Standard MIDI Files (the live-test songs and the converter's tests)."""
import struct

TICKS_PER_QUARTER = 480  # at the default tempo, 120 bpm, a quarter note is 0.5 s
VELOCITY = 100


def vlq(value):
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append(0x80 | (value & 0x7F))
        value >>= 7
    return bytes(reversed(out))


def track(events):
    """events: (tick, bytes) in any order; written with delta times and an end-of-track."""
    body, last = b"", 0
    for tick, data in sorted(events, key=lambda e: e[0]):
        body += vlq(tick - last) + data
        last = tick
    body += vlq(0) + b"\xFF\x2F\x00"
    return b"MTrk" + struct.pack(">I", len(body)) + body


def midi(*tracks):
    """A format 1 file holding these tracks."""
    return b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), TICKS_PER_QUARTER) + b"".join(tracks)


def notes_track(notes, channel=1, name=None):
    """notes: (start beat, length in beats, pitch)."""
    events = [(0, b"\xFF\x03" + vlq(len(name.encode())) + name.encode())] if name else []
    for start, length, pitch in notes:
        events.append((int(start * TICKS_PER_QUARTER), bytes([0x90 | (channel - 1), pitch, VELOCITY])))
        events.append((int((start + length) * TICKS_PER_QUARTER), bytes([0x80 | (channel - 1), pitch, 0])))
    return track(events)
