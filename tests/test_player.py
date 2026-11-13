"""src/player.c, built for the PC with tests/player_host.c: what the game is given at each frame."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import midi2oca as m  # noqa: E402

TICK_RATE = 30
CATCH_UP_MS = 50  # src/player.c
A, Y, X = m.BTN["A"], m.BTN["Y"], m.BTN["X"]


def find_compiler():
    """A C compiler for the PC: $CC, else cc, gcc or clang on the PATH, else LLVM's default place on Windows."""
    candidates = [os.environ.get("CC"), shutil.which("cc"), shutil.which("gcc"), shutil.which("clang")]
    if os.name == "nt":
        candidates.append(str(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "LLVM" / "bin" / "clang.exe"))
    return next((c for c in candidates if c and shutil.which(c)), None)


def tick_ms(tick):
    return tick * 1000 // TICK_RATE


def frames(every_ms, until_ms, start_ms=0):
    return list(range(start_ms, until_ms, every_ms))


class Played:
    """What the game got at each frame: (ms, buttons, index of the song's event or None before the first)."""

    def __init__(self, frames, ended):
        self.frames, self.ended = frames, ended

    def given(self):
        """Each event as it was first given: (ms, index)."""
        out, last = [], None
        for ms, _, index in self.frames:
            if index != last:
                out.append((ms, index))
            last = index
        return out

    def presses(self):
        """The buttons of each frame where one goes down: the notes the game plays."""
        out, held = [], 0
        for _, buttons, _ in self.frames:
            if buttons & ~held:
                out.append(buttons)
            held = buttons
        return out


class Player(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = find_compiler()
        if not compiler:
            raise unittest.SkipTest("no C compiler for the PC (set CC)")
        cls.folder = tempfile.TemporaryDirectory()
        cls.exe = Path(cls.folder.name) / ("player_host.exe" if os.name == "nt" else "player_host")
        subprocess.run([compiler, "-std=gnu11", "-O1", "-Wall", "-Wextra", "-Wno-unused-parameter", "-o", str(cls.exe),
                        str(ROOT / "tests" / "player_host.c"), str(ROOT / "src" / "player.c")], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def play(self, changes, frame_times):
        """changes: (tick, buttons), each tagged with its index on the left stick's x (far below a direction)."""
        events = [(tick, m.Input(buttons, lx=index + 1)) for index, (tick, buttons) in enumerate(changes)]
        song = Path(self.folder.name) / "song.oca"
        song.write_bytes(m.song_bytes("test", TICK_RATE, events, changes[-1][0] + 1))
        run = subprocess.run([str(self.exe), str(song)], input="\n".join(map(str, frame_times)) + "\n",
                             capture_output=True, text=True, check=True)
        out, ended = [], None
        for line in run.stdout.splitlines():
            fields = line.split()
            if fields[0] == "end":
                ended = int(fields[1])
                continue
            ms, buttons, lx = map(int, fields)
            out.append((ms, buttons, lx - 1 if lx else None))
        return Played(out, ended)

    def lateness(self, changes, played):
        """How late each event given was, by its index."""
        return {index: ms - tick_ms(changes[index][0]) for ms, index in played.given()}

    def test_every_event_on_time_when_frames_keep_up(self):
        changes = [(2 + 2 * i, (A, Y)[i % 2]) for i in range(30)] + [(62, 0)]
        played = self.play(changes, frames(16, 3000))
        self.assertEqual([index for _, index in played.given()], list(range(len(changes))))
        self.assertLessEqual(max(self.lateness(changes, played).values()), 16)
        self.assertLessEqual(played.ended - tick_ms(changes[-1][0] + 1), 16)

    def test_stays_in_time_when_notes_come_faster_than_frames(self):
        # a trill of one-tick notes for 3 s (30 a second) at 20 frames a second, then a held note
        run = [(2 + i, (A, Y)[i % 2]) for i in range(90)]
        changes = run + [(105, X), (135, 0)]
        played = self.play(changes, frames(50, 6000))
        late = self.lateness(changes, played)
        one_tick = tick_ms(1)
        self.assertLessEqual(max(ms for index, ms in late.items() if index < len(run) - 1),
                             2 * one_tick + CATCH_UP_MS + 1)
        self.assertLessEqual(late[len(run)], 50)  # the held note, on time
        self.assertLessEqual(played.ended - tick_ms(136), 50)
        from_run = [index for index in late if index < len(run)]
        self.assertGreaterEqual(len(from_run), 55)  # about one a frame: still a trill, at the frame rate
        self.assertLess(len(from_run), len(run))
        self.assertTrue(all(a != b for a, b in zip(played.presses(), played.presses()[1:])))

    def test_note_repeated_after_a_skip_is_pressed_again(self):
        # a 200 ms frame passes both the release between two A notes and the second A's start: the release is
        # given late rather than skipped, or the two notes would sound as one
        changes = [(2, A), (10, 0), (11, A), (30, 0)]
        played = self.play(changes, frames(50, 300) + frames(50, 1500, start_ms=500))
        self.assertEqual(played.given()[:4], [(100, 0), (500, 1), (550, 2), (1000, 3)])
        self.assertEqual(played.presses(), [A, A])

    def test_long_wait_pauses_the_song_instead_of_skipping(self):
        # 400 ms without a frame (a load): the song carries on where it was
        changes = [(2, A), (10, Y), (12, X), (20, 0)]
        played = self.play(changes, frames(30, 300) + frames(30, 1500, start_ms=700))
        self.assertEqual([index for _, index in played.given()], [0, 1, 2, 3])


if __name__ == "__main__":
    unittest.main()
