"""Packs a release zip: the module for emulators and for Atmosphere, the converter, README and LICENSE.

Run `make release` (it builds first), or: python tools/make_release.py <subsdk8> <out dir>
"""
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROGRAM_ID = "0400486024DEC000"

INSTALL = """ocarinaMIDI {version}: plays MIDI songs on the ocarina in The Legend of Zelda: Ocarina of Time (Switch 2).

Emulator (Lichii, Eden)
  Copy the "emulator user folder" folder's contents into the emulator's user folder:
  the "user" folder next to the emulator's exe (portable) or its folder in %APPDATA%.
  That puts the module at user\\load\\{program_id}\\ocarinaMIDI\\exefs\\subsdk8.

Console (Atmosphere)
  Copy the "console SD card" folder's contents to the root of the SD card. That puts the module at
  atmosphere\\contents\\{program_id}\\exefs\\subsdk8. Untested on a real console so far.

Songs
  Install Python 3. Drag .mid files onto converter\\drop-midi-here.bat: the first time, it asks for the
  emulator's SD card folder (usually user\\sdmc next to its exe). Or run converter\\midi2oca.py (--help for options).

Playing
  Take out the ocarina, then hold R3 (right stick in) and press:
    D-pad Up: play    D-pad Down: stop    D-pad Right / Left: next / previous song
  The song list shows at the top of the screen when you switch songs.

Works next to sloperinaGZ (they use different module slots). README.md has the details.

Source code (GPL-3): https://github.com/waze3174/ocarinaMIDI, tag v{version}.
"""


def main():
    subsdk, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    top = f"ocarinaMIDI-{version}"
    files = {
        f"{top}/emulator user folder/load/{PROGRAM_ID}/ocarinaMIDI/exefs/subsdk8": subsdk.read_bytes(),
        f"{top}/console SD card/atmosphere/contents/{PROGRAM_ID}/exefs/subsdk8": subsdk.read_bytes(),
        f"{top}/converter/midi2oca.py": (ROOT / "tools" / "midi2oca.py").read_bytes(),
        f"{top}/converter/drop-midi-here.bat": (ROOT / "tools" / "drop-midi-here.bat").read_bytes(),
        f"{top}/README.md": (ROOT / "README.md").read_bytes(),
        f"{top}/LICENSE": (ROOT / "LICENSE").read_bytes(),
        f"{top}/INSTALL.txt": INSTALL.format(version=version, program_id=PROGRAM_ID)
        .replace("\n", "\r\n").encode("utf-8"),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{top}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    print(out)


if __name__ == "__main__":
    main()
