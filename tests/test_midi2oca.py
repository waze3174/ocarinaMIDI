import io
import itertools
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import midi2oca as m  # noqa: E402
from smf_write import TICKS_PER_QUARTER as TPQ, midi, notes_track, track  # noqa: E402

HALF = m.Stick.half
FULL = m.Stick.full


def convert(data, tick_rate=30, **options):
    tracks = m.read_midi(data)
    picked = m.melody(m.select_notes(tracks, options.get("track"), options.get("channel")))
    fitted, shift, folded = m.fit_range(picked, options.get("transpose"))
    played = m.in_time(fitted, tick_rate, options.get("min_hold", 1))
    fingered = m.fingerings(played, "game", m.Stick(), options.get("altered", ()))
    spans = m.segments(played, fingered, tick_rate, options.get("min_hold", 1))
    return played, shift, folded, spans


def plain_natural_pitches(notes, fingered):
    """What the game's song matcher can see: each note played as a plain press of its button, stick centred,
    as its pitch; any other note as None (it breaks a match)."""
    return [note.pitch if played == m.Input(button) else None for note, (played, button) in zip(notes, fingered)]


def pitch_notes(pitches, length=0.5):
    return [m.Note(i * length, (i + 1) * length, pitch, 1, 0) for i, pitch in enumerate(pitches)]


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


class Ticks(unittest.TestCase):
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

    def spans_in_time(self, notes):
        """in_time and segments on these notes: the notes kept and their spans, once checked that each starts on its
        own tick, lasts a tick at least and has a released tick before a repeat on the same button."""
        kept = m.in_time(notes, 30, 1)
        spans = m.segments(kept, m.fingerings(kept, "game", m.Stick()), 30, 1)
        offset = round(kept[0].start * 30) - m.LEAD_IN_TICKS
        self.assertEqual([s.start for s in spans], [round(n.start * 30) - offset for n in kept])
        for a, b in zip(spans, spans[1:]):
            self.assertGreaterEqual(a.end - a.start, 1)
            self.assertLessEqual(a.end, b.start - (1 if a.button == b.button else 0))
        return kept, spans

    def test_notes_faster_than_the_ticks_thin_out_and_keep_their_time(self):
        run = [m.Note(i / 60, (i + 1) / 60, (62, 69)[i % 2], 1, 0) for i in range(60)]  # 60 a second for 1 s
        kept, _ = self.spans_in_time(run + [m.Note(1.5, 2.0, 65, 1, 0)])
        self.assertEqual(kept[-1].pitch, 65)  # the note after the run is on its own tick: nothing was pushed late
        self.assertEqual(len(kept) - 1, 30)  # one a tick

    def test_fast_repeats_keep_a_released_tick_and_their_time(self):
        repeats = [m.Note(i * 0.04, (i + 1) * 0.04, 62, 1, 0) for i in range(25)]  # 1.2 ticks apart for 1 s
        kept, spans = self.spans_in_time(repeats + [m.Note(1.5, 2.0, 69, 1, 0)])
        self.assertEqual(kept[-1].pitch, 69)
        self.assertGreater(len(kept) - 1, 10)
        changes, _ = m.events(spans)
        self.assertEqual([bool(i.buttons) for _, i in changes[:-2]], [True, False] * (len(kept) - 1))

    def test_of_two_notes_too_close_the_shorter_goes(self):
        grace, main = m.Note(0.0, 0.04, 62, 1, 0), m.Note(0.04, 1.0, 63, 1, 0)  # D4 then D#4: both on L
        self.assertEqual(m.in_time([grace, main], 30, 1), [main])
        held, short = m.Note(0.0, 0.04, 62, 1, 0), m.Note(0.04, 0.06, 63, 1, 0)
        self.assertEqual(m.in_time([held, short], 30, 1), [held])


def band(names=("Piano", "Melody", "Bass")):
    """A format 1 file: piano chords (channel 1), a melody line high up (channel 2), a bass line (channel 3) and
    drums (channel 10), each with its name and a program change."""
    melody_line = [(i, 1, pitch) for i, pitch in enumerate((72, 74, 76, 77, 79, 77, 76, 74))]
    chords = [(2 * i, 2, pitch) for i in range(4) for pitch in (48, 52, 55)]
    bass = [(i, 1, 36 + (i % 2) * 7) for i in range(8)]
    drums = [(i, 0.5, 38) for i in range(8)]
    piano, lead, bass_name = names
    return midi(notes_track(chords, 1, piano, program=0), notes_track(melody_line, 2, lead, program=73),
                notes_track(bass, 3, bass_name, program=33), notes_track(drums, 10, "Drums"))


class ChoosingThePart(unittest.TestCase):
    def test_each_track_and_channel_is_a_part_but_the_drums(self):
        found = m.parts(m.read_midi(band()))
        self.assertEqual([(p.track, p.channel, p.name, p.instrument) for p in found],
                         [(0, 1, "Piano", "piano"), (1, 2, "Melody", "pipe"), (2, 3, "Bass", "bass")])
        self.assertEqual(m.describe_part(found[0]), "track 0, channel 1, Piano, piano, 12 notes, C3 to G3, chords")
        self.assertEqual(m.describe_part(found[1]), "track 1, channel 2, Melody, pipe, 8 notes, C5 to G5")

    def test_one_track_with_several_channels_gives_a_part_each(self):
        events = [(0, b"\x90\x48\x64"), (480, b"\x80\x48\x00"), (0, b"\x91\x30\x64"), (480, b"\x81\x30\x00")]
        found = m.parts(m.read_midi(midi(track(events))))
        self.assertEqual([(p.track, p.channel, len(p.notes)) for p in found], [(0, 1, 1), (0, 2, 1)])

    def test_likely_melody_is_the_high_single_line(self):
        for names in (("Piano", "Melody", "Bass"), ("", "", "")):
            with self.subTest(names=names):
                self.assertEqual(m.likely_melody(m.parts(m.read_midi(band(names)))).channel, 2)

    def test_a_name_can_tell_two_alike_lines_apart(self):
        line = [(i, 1, pitch) for i, pitch in enumerate((72, 74, 76, 77))]
        found = m.parts(m.read_midi(midi(notes_track(line, 1, "Synth"), notes_track(line, 2, "Vocals"))))
        self.assertEqual(m.likely_melody(found).name, "Vocals")

    def ask(self, *answers):
        found = m.parts(m.read_midi(band()))
        replies = iter(answers)

        def reply(_prompt):
            answer = next(replies)
            if answer is EOFError:
                raise EOFError
            return answer

        with redirect_stdout(io.StringIO()) as shown:
            picked = m.ask_for_part(found, "band.mid", reply)
        return found, picked, shown.getvalue()

    def test_enter_takes_the_likely_melody_marked_in_the_list(self):
        found, picked, shown = self.ask("")
        self.assertIs(picked, found[1])
        self.assertIn("   2  track 1, channel 2, Melody, pipe, 8 notes, C5 to G5   <- likely the melody", shown)
        self.assertIn("   0  all parts together", shown)

    def test_a_number_picks_a_part_and_0_all_of_them(self):
        found, picked, _ = self.ask("3")
        self.assertIs(picked, found[2])
        self.assertIsNone(self.ask("0")[1])

    def test_anything_else_asks_again(self):
        found, picked, shown = self.ask("9", "bass", "1")
        self.assertIs(picked, found[0])
        self.assertEqual(shown.count("Type a number from 0 to 3."), 2)

    def test_no_answer_at_all_takes_the_likely_melody(self):
        found, picked, _ = self.ask(EOFError)
        self.assertIs(picked, found[1])


class GameSongs(unittest.TestCase):
    SARIA = m.GAME_SONGS["Saria's Song"]

    def test_every_game_song_uses_the_five_natural_notes(self):
        for song in m.GAME_SONGS.values():
            self.assertTrue(set(song) <= set(m.NATURAL_NOTES))

    def test_a_game_song_inside_a_melody_is_found(self):
        self.assertEqual(m.game_song_windows((62,) + self.SARIA + (74,)), [m.SongWindow("Saria's Song", 1, 6)])

    def test_a_note_in_between_breaks_it(self):
        self.assertEqual(m.game_song_windows(self.SARIA[:3] + (66,) + self.SARIA[3:]), [])

    def test_overlapping_songs_share_an_altered_note(self):
        windows = m.game_song_windows(self.SARIA * 2)  # F A B four times: Saria's Song starts at notes 0, 3 and 6
        self.assertEqual([(w.first, w.last) for w in windows], [(0, 5), (3, 8), (6, 11)])
        self.assertEqual(m.notes_to_alter(windows), [5, 11])

    def test_fewest_notes_that_break_every_song(self):
        melodies = [self.SARIA * 2, m.GAME_SONGS["Song of Time"] + m.GAME_SONGS["Song of Storms"],
                    m.GAME_SONGS["Bolero of Fire"] * 2 + m.GAME_SONGS["Zelda's Lullaby"]]
        for pitches in melodies:
            windows = m.game_song_windows(pitches)
            altered = m.notes_to_alter(windows)
            self.assertTrue(all(any(w.first <= i <= w.last for i in altered) for w in windows))
            fewest = next(k for k in range(len(pitches) + 1) for picked in itertools.combinations(range(len(pitches)), k)
                          if all(any(w.first <= i <= w.last for i in picked) for w in windows))
            self.assertEqual(len(altered), fewest)

    def test_altered_melody_holds_no_game_song_for_the_matcher(self):
        notes = pitch_notes((62,) + self.SARIA * 2 + m.GAME_SONGS["Song of Time"])
        windows = m.game_song_windows(n.pitch for n in notes)
        self.assertTrue(windows)
        fingered = m.fingerings(notes, "game", m.Stick(), m.notes_to_alter(windows))
        self.assertEqual(m.game_song_windows(plain_natural_pitches(notes, fingered)), [])
        unaltered = m.fingerings(notes, "game", m.Stick())
        self.assertEqual(m.game_song_windows(plain_natural_pitches(notes, unaltered)), windows)


class AlternateFingering(unittest.TestCase):
    def test_same_pitch_from_button_modifier_and_bend(self):
        modifier, bend = m.ALTERNATE_FINGERING
        self.assertEqual(modifier + bend, 0)
        self.assertNotEqual(modifier, 0)

    def test_game_layout(self):
        for pitch, button in m.LAYOUTS["game"]["notes"].items():
            played, natural_button = m.note_input(pitch, "game", m.Stick(), alternate=True)
            self.assertEqual(played, m.Input(m.BTN[button] | m.BTN["DDOWN"], ly=HALF))
            self.assertEqual(natural_button, m.BTN[button])

    def test_performance_layout_and_inverted_right_stick(self):
        played, _ = m.note_input(69, "performance", m.Stick(sign=-1, side="right"), alternate=True)
        self.assertEqual(played, m.Input(m.BTN["A"] | m.BTN["ZL"], ry=-HALF))

    def test_only_natural_notes_have_one(self):
        with self.assertRaises(ValueError):
            m.note_input(63, "game", m.Stick(), alternate=True)

    def test_altered_note_keeps_its_timing(self):
        data = midi(notes_track([(0, 1, 65), (1, 1, 69), (2, 1, 71)]))
        plain = convert(data, transpose=0)[3]
        altered = convert(data, transpose=0, altered=[1])[3]
        self.assertEqual([(s.start, s.end) for s in plain], [(s.start, s.end) for s in altered])
        self.assertEqual(altered[1].input, m.Input(m.BTN["A"] | m.BTN["DDOWN"], ly=HALF))


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
            for name in ("a.oca", "b.oca", "a.oca"):
                (songs / name).write_bytes(b"")
                m.add_to_playlist(songs, name)
            self.assertEqual((songs / m.PLAYLIST).read_text(), "a.oca\nb.oca\n")

    def test_playlist_drops_songs_whose_file_is_gone(self):
        with tempfile.TemporaryDirectory() as folder:
            songs = Path(folder)
            (songs / m.PLAYLIST).write_text("a.oca\n# my songs\n gone.oca \n\nb.oca\n")
            for name in ("a.oca", "b.oca", "c.oca"):
                (songs / name).write_bytes(b"")
            self.assertEqual(m.add_to_playlist(songs, "c.oca"), ["gone.oca"])
            self.assertEqual((songs / m.PLAYLIST).read_text(), "a.oca\n# my songs\n\nb.oca\nc.oca\n")

    def test_file_names_are_plain(self):
        self.assertEqual(m.file_name("Song of Storms (v2)"), "Song_of_Storms_v2.oca")
        self.assertLessEqual(len(m.file_name("x" * 200)), m.MAX_FILE_NAME)


class CommandLine(unittest.TestCase):
    def pick(self, answer, *options):
        """What the converter prints for band() with --pick, when this answer is typed."""
        with tempfile.TemporaryDirectory() as folder:
            source, out = Path(folder) / "band.mid", Path(folder) / "band.oca"
            source.write_bytes(band())
            stdout = io.StringIO()
            stdin, sys.stdin = sys.stdin, io.StringIO(answer)
            try:
                with redirect_stdout(stdout):
                    m.main([str(source), "--out", str(out), "--pick", *options])
            finally:
                sys.stdin = stdin
        return stdout.getvalue()

    def test_pick_converts_the_part_chosen(self):
        stdout = self.pick("\n")
        self.assertIn("melody: track 1, channel 2, Melody", stdout)
        self.assertIn("(--track 1 --channel 2)", stdout)
        self.assertIn(": 8 notes,", stdout)  # the melody line
        self.assertIn(": 4 notes,", self.pick("1\n"))  # the piano's four chords, their top notes
        self.assertIn("melody: all parts together", self.pick("0\n"))

    def test_track_or_channel_given_means_no_question(self):
        self.assertNotIn("which part", self.pick("", "--channel", "1"))

    def run_converter(self, *options, extra=()):
        """Saria's Song, 0.5 s a note, with `extra` notes (start s, length s, pitch), converted with these options."""
        saria = [(i * 0.5, 0.5, pitch) for i, pitch in enumerate(m.GAME_SONGS["Saria's Song"])] + list(extra)
        with tempfile.TemporaryDirectory() as folder:
            source, out = Path(folder) / "saria.mid", Path(folder) / "saria.oca"
            source.write_bytes(midi(notes_track([(2 * start, 2 * length, pitch) for start, length, pitch in saria])))
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                m.main([str(source), "--out", str(out), "--transpose", "0", *options])
            data = out.read_bytes()
        count = m.HEADER.unpack_from(data)[3]
        buttons = [m.EVENT.unpack_from(data, m.HEADER.size + i * m.EVENT.size)[1] for i in range(count)]
        return buttons, stdout.getvalue(), stderr.getvalue()

    def test_game_song_gets_one_alternate_note_by_default(self):
        buttons, stdout, stderr = self.run_converter()
        self.assertEqual(sum(1 for b in buttons if b & m.BTN["DDOWN"]), 1)
        self.assertIn("Saria's Song at notes 1-6", stdout)
        self.assertIn("note 6 (B4) is played as Y + DDOWN + left stick half up", stdout)
        self.assertEqual(stderr, "")

    def test_allow_songs_plays_it_plainly_and_warns(self):
        buttons, _, stderr = self.run_converter("--allow-songs")
        self.assertFalse(any(b & m.BTN["DDOWN"] for b in buttons))
        self.assertIn("warning: it plays Saria's Song", stderr)

    def test_game_song_is_found_after_notes_too_close_are_left_out(self):
        # a 30 ms C5 (on Y) just before the first B4 (on Y) is left out, which leaves Saria's Song note for note
        buttons, stdout, _ = self.run_converter(extra=[(0.965, 0.03, 72)])
        self.assertIn("(1 left out, too close together)", stdout)
        self.assertIn("Saria's Song at notes 1-6", stdout)
        self.assertEqual(sum(1 for b in buttons if b & m.BTN["DDOWN"]), 1)


if __name__ == "__main__":
    unittest.main()
