import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import midi2oca as m  # noqa: E402
from smf_write import TICKS_PER_QUARTER as TPQ, midi, notes_track, track  # noqa: E402

HALF = m.Stick.half
FULL = m.Stick.full


def convert(data, fps=30, **options):
    tracks = m.read_midi(data)
    picked = m.melody(m.select_notes(tracks, options.get("track"), options.get("channel")))
    fitted, shift, folded = m.fit_range(picked, options.get("transpose"))
    spans = m.segments(fitted, fps, "game", m.Stick(), options.get("min_hold", 1))
    return fitted, shift, folded, spans


class NotePlan(unittest.TestCase):
    def test_every_semitone_is_its_natural_note_plus_modifier_plus_stick(self):
        self.assertEqual(sorted(m.NOTE_PLAN), list(range(m.LOWEST, m.HIGHEST + 1)))
        for pitch, (natural, modifier, bend) in m.NOTE_PLAN.items():
            self.assertIn(natural, m.NATURAL_NOTES)
            self.assertIn(modifier, (-1, 0, 1))
            self.assertEqual(natural + modifier + bend, pitch)

    def test_only_the_five_unreachable_notes_use_the_stick(self):
        bent = sorted(p for p, (_, _, bend) in m.NOTE_PLAN.items() if bend)
        self.assertEqual(bent, [59, 60, 67, 76, 77])  # B3 C4 G4 E5 F5

    def test_game_layout_buttons(self):
        cases = {62: ("L", 0), 63: ("L", m.BTN["DUP"]), 64: ("R", m.BTN["DDOWN"]), 69: ("A", 0),
                 71: ("Y", 0), 74: ("X", 0)}
        for pitch, (button, modifier) in cases.items():
            played, natural_button = m.note_input(pitch, "game", m.Stick())
            self.assertEqual(played, m.Input(m.BTN[button] | modifier))
            self.assertEqual(natural_button, m.BTN[button])

    def test_bends_are_exact_tilts(self):
        self.assertEqual(m.note_input(67, "game", m.Stick())[0].ly, HALF)  # G4 = F#4 + 1
        self.assertEqual(m.note_input(77, "game", m.Stick())[0].ly, FULL)  # F5 = D#5 + 2
        self.assertEqual(m.note_input(59, "game", m.Stick())[0].ly, -FULL)  # B3 = C#4 - 2
        self.assertEqual(m.note_input(60, "game", m.Stick(sign=-1))[0].ly, HALF)
        self.assertEqual(m.note_input(60, "game", m.Stick(side="right"))[0], m.Input(m.BTN["L"] | m.BTN["DDOWN"], ry=-HALF))


class ReadingMidi(unittest.TestCase):
    def test_tempo_change_and_running_status(self):
        # running status: the second note-on and both offs reuse the first status byte
        events = [(0, b"\xFF\x51\x03" + (1000000).to_bytes(3, "big")),  # 60 bpm: a beat is 1 s
                  (0, b"\x90\x3E\x64"), (TPQ, b"\x3E\x00"), (TPQ, b"\x41\x64"), (2 * TPQ, b"\x41\x00")]
        notes = m.read_midi(midi(track(events)))[0].notes
        self.assertEqual([(n.start, n.end, n.pitch) for n in notes], [(0.0, 1.0, 62), (1.0, 2.0, 65)])

    def test_tempo_from_another_track_applies(self):
        conductor = track([(TPQ, b"\xFF\x51\x03" + (250000).to_bytes(3, "big"))])  # 240 bpm after beat 1
        notes = m.read_midi(midi(conductor, notes_track([(2, 1, 62)])))[1].notes
        self.assertAlmostEqual(notes[0].start, 0.5 + 0.25)
        self.assertAlmostEqual(notes[0].end, 0.5 + 0.5)

    def test_rejects_non_midi(self):
        with self.assertRaises(m.MidiError):
            m.read_midi(b"RIFF....")


class PickingTheMelody(unittest.TestCase):
    def test_top_note_of_a_chord(self):
        fitted, *_ = convert(midi(notes_track([(0, 1, 62), (0, 1, 66), (0, 1, 69)])))
        self.assertEqual([n.pitch for n in fitted], [69])

    def test_held_melody_note_ignores_lower_accompaniment(self):
        data = midi(notes_track([(0, 4, 72), (1, 0.5, 60), (2, 0.5, 64)]))
        fitted, *_ = convert(data, transpose=0)
        self.assertEqual([(n.pitch, n.end) for n in fitted], [(72, 2.0)])

    def test_legato_lower_note_takes_over(self):
        data = midi(notes_track([(0, 1.05, 69), (1, 1, 65)]))  # overlaps by 0.025 s
        fitted, *_ = convert(data, transpose=0)
        self.assertEqual([(n.pitch, n.start, n.end) for n in fitted], [(69, 0.0, 0.5), (65, 0.5, 1.0)])

    def test_drums_dropped_unless_asked_for(self):
        data = midi(notes_track([(0, 1, 62)]), notes_track([(0, 1, 70)], channel=10))
        self.assertEqual([n.pitch for n in convert(data, transpose=0)[0]], [62])
        self.assertEqual([n.pitch for n in convert(data, transpose=0, channel=10)[0]], [70])


class FittingTheRange(unittest.TestCase):
    def test_octave_shift_preferred(self):
        _, shift, folded, _ = convert(midi(notes_track([(0, 1, 84), (1, 1, 86), (2, 1, 88)])))  # C6 D6 E6
        self.assertEqual((shift % 12, folded), (0, 0))

    def test_wide_melody_folds_the_outliers(self):
        fitted, shift, folded, _ = convert(midi(notes_track([(0, 1, 60), (1, 1, 62), (2, 1, 90)])))
        self.assertEqual(folded, 1)
        self.assertTrue(all(m.LOWEST <= n.pitch <= m.HIGHEST for n in fitted))


class Frames(unittest.TestCase):
    def test_repeated_note_gets_a_released_frame(self):
        spans = convert(midi(notes_track([(0, 1, 62), (1, 1, 62)])), transpose=0)[3]
        changes, total = m.events(spans)
        self.assertEqual([(f, i.buttons) for f, i in changes],
                         [(2, m.BTN["L"]), (16, 0), (17, m.BTN["L"]), (32, 0)])
        self.assertEqual(total, 33)

    def test_different_buttons_change_without_a_gap(self):
        spans = convert(midi(notes_track([(0, 1, 62), (1, 1, 65)])), transpose=0)[3]
        changes, _ = m.events(spans)
        self.assertEqual([(f, i.buttons) for f, i in changes],
                         [(2, m.BTN["L"]), (17, m.BTN["R"]), (32, 0)])

    def test_very_short_notes_still_last_a_frame(self):
        spans = convert(midi(notes_track([(0, 0.01, 62), (0.1, 0.01, 69)])), transpose=0)[3]
        self.assertEqual(len(spans), 2)
        self.assertTrue(all(s.end - s.start >= 1 for s in spans))
        self.assertTrue(all(a.end <= b.start for a, b in zip(spans, spans[1:])))


class GameSongs(unittest.TestCase):
    def test_every_game_song_uses_the_five_natural_notes(self):
        for song in m.GAME_SONGS.values():
            self.assertTrue(set(song) <= set(m.NATURAL_NOTES))

    def test_a_game_song_inside_a_melody_is_found(self):
        saria = m.GAME_SONGS["Saria's Song"]
        self.assertEqual(m.game_songs_in((62,) + saria + (74,)), ["Saria's Song"])

    def test_a_note_in_between_breaks_it(self):
        saria = m.GAME_SONGS["Saria's Song"]
        self.assertEqual(m.game_songs_in(saria[:3] + (66,) + saria[3:]), [])


class SongFile(unittest.TestCase):
    def test_layout_matches_src_song_h(self):
        changes = [(2, m.Input(m.BTN["L"], ly=-HALF)), (5, m.RELEASED)]
        data = m.song_bytes("Zelda's Lullaby", 30, changes, 6)
        self.assertEqual(len(data), 64 + 2 * 16)
        magic, version, fps, count, total, title = m.HEADER.unpack_from(data)
        self.assertEqual((magic, version, fps, count, total), (b"OCA1", 1, 30, 2, 6))
        self.assertEqual(title.rstrip(b"\0"), b"Zelda's Lullaby")
        self.assertEqual(m.EVENT.unpack_from(data, 64), (2, m.BTN["L"], 0, -HALF, 0, 0))

    def test_long_title_is_cut_on_a_character_boundary(self):
        self.assertLessEqual(len(m.encode_title("é" * 40)), m.TITLE_BYTES - 1)
        m.encode_title("é" * 40).decode("utf-8")

    def test_playlist_lists_each_song_once(self):
        with tempfile.TemporaryDirectory() as folder:
            songs = Path(folder)
            m.add_to_playlist(songs, "a.oca")
            m.add_to_playlist(songs, "b.oca")
            m.add_to_playlist(songs, "a.oca")
            self.assertEqual((songs / m.PLAYLIST).read_text(), "a.oca\nb.oca\n")

    def test_file_names_are_plain(self):
        self.assertEqual(m.file_name("Song of Storms (v2)"), "Song_of_Storms_v2.oca")
        self.assertLessEqual(len(m.file_name("x" * 200)), m.MAX_FILE_NAME)


if __name__ == "__main__":
    unittest.main()
