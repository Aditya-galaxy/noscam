"""
Put the narration onto the screen recording.

    python3 video/assemble.py screen.mov            # -> video/out/noscam-demo.mp4
    python3 video/assemble.py screen.mov --keep-audio   # keep your own voice too

The recording is the real product on a real screen. This only adds sound, pads
or trims to match, and encodes something Devpost and YouTube both accept.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"


def duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description="Mux the narration onto a screen recording.")
    parser.add_argument("recording", help="the screen capture (.mov, .mp4)")
    parser.add_argument("--narration", default=str(OUT / "narration.wav"))
    parser.add_argument("--out", default=str(OUT / "noscam-demo.mp4"))
    parser.add_argument("--keep-audio", action="store_true",
                        help="mix the recording's own sound under the narration")
    args = parser.parse_args()

    if not shutil.which("ffmpeg"):
        print("ffmpeg is missing: brew install ffmpeg")
        return 1
    recording, narration = Path(args.recording), Path(args.narration)
    for path in (recording, narration):
        if not path.exists():
            print(f"missing: {path}")
            return 1

    video_len, audio_len = duration(recording), duration(narration)
    print(f"  video {video_len:.0f}s · narration {audio_len:.0f}s")
    if audio_len > video_len + 2:
        print("  The narration is longer than the recording. Either record the last")
        print("  scene again, or trim the script — a voice talking over a frozen")
        print("  screen is the thing judges notice.")

    if args.keep_audio:
        mapping = ["-filter_complex",
                   "[0:a]volume=0.25[under];[under][1:a]amix=inputs=2:duration=longest[a]",
                   "-map", "0:v", "-map", "[a]"]
    else:
        mapping = ["-map", "0:v", "-map", "1:a"]

    command = [
        "ffmpeg", "-y", "-i", str(recording), "-i", str(narration),
        *mapping,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        "-shortest", args.out,
    ]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    size = Path(args.out).stat().st_size / 1_000_000
    print(f"  {args.out}  ({size:.1f} MB, {duration(Path(args.out)):.0f}s)")
    print("\n  Watch it once before uploading. If a cue lands late, re-record that")
    print("  scene rather than stretching the audio: mismatched narration reads as")
    print("  carelessness, and this is a video about carefulness.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
