import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import live_test_songs as live  # noqa: E402
import midi2oca as m  # noqa: E402


def played_pitches(name):
    title, notes = live.SONGS[name]
    picked = m.melody(m.select_notes(m.read_midi(live.song_midi(title, notes))))
    fitted, shift, folded = m.fit_range(picked, 0)
    return [n.pitch for n in fitted], folded


class LiveTestSongs(unittest.TestCase):
    def test_every_note_is_played_as_written(self):
        for name, (title, notes) in live.SONGS.items():
            with self.subTest(name):
                pitches, folded = played_pitches(name)
                self.assertEqual(folded, 0)
                self.assertEqual(pitches, [pitch for _, _, pitch in sorted(notes)])
                self.assertLess(len(title.encode()), m.TITLE_BYTES)

    def test_only_t8_plays_a_game_song(self):
        for name in live.SONGS:
            with self.subTest(name):
                expected = ["Saria's Song"] if name == "t8-sarias-song" else []
                self.assertEqual([w.song for w in m.game_song_windows(played_pitches(name)[0])], expected)

    def test_sd_card_gets_every_song_in_the_playlist(self):
        with tempfile.TemporaryDirectory() as folder, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            live.main(["--sd", folder])
            songs = Path(folder) / m.SONGS_SUBDIR
            listed = (songs / m.PLAYLIST).read_text().split()
            self.assertEqual(listed, [f"{name}.oca" for name in live.SONGS])
            self.assertTrue(all((songs / entry).stat().st_size > 64 for entry in listed))


if __name__ == "__main__":
    unittest.main()
