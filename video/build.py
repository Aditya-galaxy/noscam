"""
Assemble the demo video: real frames, timed to the narration.

    python3 video/capture.py && python3 video/narrate.py --engine say
    python3 video/build.py            # -> video/out/noscam-demo.mp4

Each narration line owns a scene, and each scene's length is the exact length of
the audio that plays over it — so the picture cannot drift away from the words.
A slow push on each still keeps it from looking like a slide deck.

Nothing here is generated imagery: every frame came out of a browser rendering
the product. Only the voice is synthetic, and the submission says so.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
FRAMES = HERE / "frames"
OUT = HERE / "out"
WIDTH, HEIGHT, FPS = 1920, 1080, 30

# Which picture belongs to which line. Two lines can share a frame — that is
# what makes a long explanation sit still while the eye reads the card.
SCENES = {
    "hook": "01-message",
    "problem": "01-message",
    "thesis": "01-message",
    "the-page": "02-fake-bank",
    "why-lists-fail": "02-fake-bank",
    "the-block": "03-held",
    "the-reason": "03-held",
    "the-model": "04-held-advice",
    "second-device": "05-phone-approval",
    "the-approval": "06-phone-empty",
    "ordinary-life": "07-ordinary",
    "other-vectors": "08-giftcards",
    "history": "10-phone-history",
    "the-numbers": "11-scorecard",
    "limits-and-close": "04-held-advice",
}
# A second picture inside one line, for the ones that cover two things.
SPLITS = {
    "other-vectors": ("08-giftcards", "09-phone-upi"),
    # The last line is the honest one about limits, then where to get it. The
    # address belongs on screen while it is said, not in a separate tour of a
    # web page that would spend demo time on something other than the product.
    "limits-and-close": ("04-held-advice", "12-endcard"),
}


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as fh:
        return fh.getnframes() / fh.getframerate()


def clip(frame: Path, seconds: float, index: int) -> Path:
    """One still, held for as long as its line is spoken, with a slow push in.

    Phone screenshots are portrait and the film is landscape, so everything is
    fitted rather than cropped: losing the top of a payment card to a crop would
    defeat the point of showing it.
    """
    out = OUT / f"clip-{index:02d}.mp4"
    # A still, fitted and held. An earlier version pushed slowly in with
    # zoompan, which re-renders every frame at full resolution and turned a
    # three-minute film into an hour of encoding for motion nobody would have
    # named. Fades at the cuts do the same work for free.
    chain = (f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
             f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=0x0b0b0d,"
             f"fade=t=in:st=0:d=0.3,"
             f"fade=t=out:st={max(0.0, seconds - 0.3):.2f}:d=0.3,format=yuv420p")
    subprocess.run(
        ["ffmpeg", "-y", "-loop", "1", "-t", f"{seconds:.3f}", "-i", str(frame),
         "-vf", chain, "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast",
         "-tune", "stillimage", "-crf", "22", "-g", str(FPS * 2), str(out)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    return out


def main() -> int:
    if not shutil.which("ffmpeg"):
        print("ffmpeg is missing: brew install ffmpeg")
        return 1
    narration = OUT / "narration.wav"
    if not narration.exists():
        print("No narration yet:  python3 video/narrate.py --engine say")
        return 1
    if not FRAMES.exists():
        print("No frames yet:  python3 video/capture.py")
        return 1

    script = json.loads((HERE / "script.json").read_text(encoding="utf-8"))
    clips, shots, index = [], [], 0

    # When the narration was spoken a paragraph at a time, there is no file per
    # line to measure — the narrator wrote down how long each line ran instead.
    timings_file = OUT / "timings.json"
    timings = (json.loads(timings_file.read_text(encoding="utf-8"))
               if timings_file.exists() else {})

    for order, segment in enumerate(script["segments"], start=1):
        name = segment["id"]
        if name in timings:
            seconds = timings[name]
        else:
            line = OUT / f"{order:02d}-{name}.wav"
            if not line.exists():
                print(f"  missing audio for {name} — rerun narrate.py")
                return 1
            seconds = wav_seconds(line)

        parts = SPLITS.get(name, (SCENES.get(name),))
        share = seconds / len(parts)
        for part in parts:
            frame = FRAMES / f"{part}.png"
            if not frame.exists():
                print(f"  missing frame {frame.name}")
                return 1
            # Several lines in a row can be spoken over one picture. Cutting
            # between two copies of the same image would fade it out and back
            # in — a blink the viewer notices and cannot explain. Hold it
            # instead: one shot, as long as all the lines that share it.
            if shots and shots[-1][0] == part:
                shots[-1][1] += share
                shots[-1][2].append(name)
            else:
                shots.append([part, share, [name]])

    for part, seconds, names in shots:
        index += 1
        print(f"  {index:>2}. {part:<18} {seconds:5.1f}s   ({', '.join(names)})")
        clips.append(clip(FRAMES / f"{part}.png", seconds, index))

    listing = OUT / "clips.txt"
    listing.write_text("".join(f"file '{c.name}'\n" for c in clips), encoding="utf-8")
    silent = OUT / "silent.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-c", "copy", str(silent)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    final = OUT / "noscam-demo.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(silent), "-i", str(narration),
         "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", str(final)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
         str(final)], capture_output=True, text=True, check=True)
    length = float(probe.stdout.strip())
    print(f"\n  {final}")
    print(f"  {length // 60:.0f}:{length % 60:04.1f} · "
          f"{final.stat().st_size / 1_000_000:.1f} MB · {WIDTH}x{HEIGHT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
