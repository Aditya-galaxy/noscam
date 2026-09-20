"""
Build the thing a person downloads.

    python3 package.py            # -> dist/noscam.zip

The repository is not the product. It carries a fifty-megabyte film, the frames
it was cut from, the test suite, the scorecard and the write-ups — all of which
matter to a reviewer and none of which a person installing this needs to run it.
Downloading the repository to use NoScam means downloading the video twice: once
to watch on the page, once inside the zip.

So this ships the parts that actually run, and nothing else.

Every file comes from `git ls-files`, never from the working directory. That is
not a tidiness preference: the working directory holds `data/`, which is the
live household — the audit log, the payee list, and the token that authorises a
phone to approve payments. It is gitignored, so asking git what exists makes it
impossible to put someone's own household into a file that strangers download.
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIST = HERE / "dist"
VERSION = "1.0.0"

# What it takes to run: the gate, the phone app, the extension, the stand-in
# sites that let you watch it work, and the launcher that starts all of them.
SHIP = ["noscam.py", "requirements.txt", "Start NoScam.command",
        "service", "web", "extension", "demo",
        "LICENSE", "LIMITATIONS.md"]

INSTALL = """NoScam — a message cannot authorise your money.

WHAT THIS IS
  Software that runs on your own computer and refuses to let an instruction
  that arrived in a message authorise something you cannot undo: a payment to
  someone new, a remote-control app, a code read out loud to a caller.

  Nothing about your money leaves this machine. There is no account to make.

TO RUN IT
  1. Open Terminal in this folder.
  2. python3 -m pip install -r requirements.txt
  3. python3 noscam.py

  A browser opens. Follow the message, press Transfer, and watch it stop.

  On a Mac you can double-click "Start NoScam.command" instead of step 3.

THE BROWSER EXTENSION
  The gate can only stand in front of a payment if it can see the page. Open
  chrome://extensions, turn on Developer mode, choose "Load unpacked", and
  pick the "extension" folder in here.

WHAT IT CANNOT DO
  Read LIMITATIONS.md. It is short, and it is honest: this does not protect a
  phone at the OS level, does not clean an already-infected computer, and can
  always be overridden by the person at the keyboard. That last one is
  deliberate. A control you cannot override is a control you uninstall.

  Version {version} · MIT licensed · github.com/Aditya-galaxy/noscam
"""


def tracked(paths: list[str]) -> list[Path]:
    """Ask git what exists. The working directory also holds the live
    household, which must never end up in a download."""
    listing = subprocess.run(["git", "ls-files", "-z", *paths],
                             cwd=HERE, capture_output=True, text=True, check=True)
    return [Path(name) for name in listing.stdout.split("\0") if name]


def main() -> int:
    files = tracked(SHIP)
    if not files:
        print("git listed nothing — run this inside the repository.")
        return 1

    DIST.mkdir(exist_ok=True)
    archive = DIST / "noscam.zip"
    root = f"noscam-{VERSION}"

    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(f"{root}/INSTALL.txt", INSTALL.format(version=VERSION))
        for name in files:
            bundle.write(HERE / name, f"{root}/{name}")

    # Say what went in, so a mistake here is visible rather than shipped.
    size = archive.stat().st_size
    print(f"  {archive}  ({size / 1_000_000:.1f} MB, {len(files) + 1} files)\n")
    for name in sorted({str(f).split("/")[0] for f in files}):
        print(f"    {name}")
    print("\n  Excluded: the film, its frames, the tests, the scorecard, the")
    print("  write-ups, and data/ — which is somebody's actual household.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
