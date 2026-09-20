"""
Turn the narration script into a voice track.

    python3 video/narrate.py            # writes video/out/narration.wav + a cue sheet
    python3 video/narrate.py --voice Charon

Why a synthesised voice at all: the judges need to hear what is happening while
they watch it happen, and a script read badly under time pressure is worse than
one read evenly. The recording itself is the real product on a real screen —
that is the part that must not be faked, and is not.

Each line becomes its own audio file, with the pause that follows it baked in,
so the cue sheet can tell you exactly when to click. Requires a GEMINI_API_KEY
and ffmpeg.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
MODEL = os.environ.get("NOSCAM_TTS_MODEL", "gemini-2.5-flash-preview-tts")
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Gemini returns raw 16-bit mono PCM at 24 kHz.
SAMPLE_RATE = 24_000
CHANNELS = 1
SAMPLE_WIDTH = 2


def speak(text: str, voice: str, key: str, attempts: int = 6) -> bytes:
    """One line of speech. The preview voice models are rate-limited hard on the
    free tier, so a 429 is the normal case rather than an error: wait and ask
    again. The URL is never printed, because the key rides in it."""
    import time

    import httpx

    for attempt in range(attempts):
        try:
            return _speak_once(text, voice, key)
        except httpx.HTTPStatusError as exc:
            retryable = exc.response.status_code in (429, 500, 502, 503, 504)
            if not retryable or attempt == attempts - 1:
                raise RuntimeError(f"the voice model said {exc.response.status_code}") from None
            wait = min(60, 8 * (attempt + 1))
            print(f"      rate-limited; waiting {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def _speak_once(text: str, voice: str, key: str) -> bytes:
    import httpx

    response = httpx.post(
        ENDPOINT.format(model=MODEL),
        params={"key": key},
        json={
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}
                },
            },
        },
        timeout=120,
    )
    response.raise_for_status()
    parts = response.json()["candidates"][0]["content"]["parts"]
    audio = next(p["inlineData"]["data"] for p in parts if "inlineData" in p)
    return base64.b64decode(audio)


def speak_locally(text: str, voice: str) -> bytes:
    """macOS's own voice, as raw PCM.

    The hosted preview voices allow ten requests a day on the free tier, which
    is fewer than this script has lines — and a narration that changes voice
    halfway through because the quota ran out is worse than one that is merely
    less polished. This one has no quota, works offline, and sounds the same
    from the first line to the last.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as workspace:
        aiff = Path(workspace) / "line.aiff"
        raw = Path(workspace) / "line.raw"
        subprocess.run(["say", "-v", voice, "-o", str(aiff), text], check=True)
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(aiff), "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS),
             "-f", "s16le", str(raw)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return raw.read_bytes()


def write_wav(path: Path, pcm: bytes, trailing_silence: float = 0.0) -> float:
    silence = b"\x00" * int(SAMPLE_RATE * SAMPLE_WIDTH * trailing_silence)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(CHANNELS)
        fh.setsampwidth(SAMPLE_WIDTH)
        fh.setframerate(SAMPLE_RATE)
        fh.writeframes(pcm + silence)
    return len(pcm + silence) / (SAMPLE_RATE * SAMPLE_WIDTH)


def duration_of(path: Path) -> float:
    with wave.open(str(path), "rb") as fh:
        return fh.getnframes() / fh.getframerate()


def timestamp(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Narrate the demo script.")
    parser.add_argument("--voice", default=None,
                        help="Kore, Charon, Puck, Aoede… (default: from script.json)")
    parser.add_argument("--only", help="render a single segment by id, to redo one line")
    parser.add_argument("--force", action="store_true",
                        help="re-render lines that already exist")
    parser.add_argument("--engine", choices=("gemini", "say"), default="gemini",
                        help="'say' uses the machine's own voice: no quota, no network, "
                             "and the same voice for every line")
    args = parser.parse_args()

    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if args.engine == "gemini" and not key:
        print("Set GEMINI_API_KEY, or use --engine say for the machine's own voice.")
        return 1
    if not shutil.which("ffmpeg"):
        print("ffmpeg is needed to join the lines into one track: brew install ffmpeg")
        return 1

    script = json.loads((HERE / "script.json").read_text(encoding="utf-8"))
    voice = args.voice or (script.get("voice", "Kore") if args.engine == "gemini"
                           else "Samantha")
    segments = [s for s in script["segments"] if not args.only or s["id"] == args.only]
    OUT.mkdir(exist_ok=True)

    cues, elapsed = [], 0.0
    for index, segment in enumerate(segments, start=1):
        path = OUT / f"{index:02d}-{segment['id']}.wav"
        if path.exists() and not args.force:
            # Resume: a rate limit halfway through should cost the remaining
            # lines, not the ones already spoken.
            print(f"  [{index}/{len(segments)}] {segment['id']} — already done", flush=True)
            cues.append((timestamp(elapsed), segment["id"], segment["do"]))
            elapsed += duration_of(path)
            continue
        print(f"  [{index}/{len(segments)}] {segment['id']}…", flush=True)
        pcm = (speak(segment["say"], voice, key) if args.engine == "gemini"
               else speak_locally(segment["say"], voice))
        length = write_wav(path, pcm, segment.get("pause_after", 0.0))
        cues.append((timestamp(elapsed), segment["id"], segment["do"]))
        elapsed += length


    if args.only:
        print(f"\nRedid one line: {OUT / f'01-{args.only}.wav'}")
        return 0

    listing = OUT / "segments.txt"
    listing.write_text("".join(
        f"file '{(OUT / f'{i:02d}-{s['id']}.wav').name}'\n"
        for i, s in enumerate(segments, start=1)), encoding="utf-8")
    narration = OUT / "narration.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-c", "copy", str(narration)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    cue_sheet = ["# Cue sheet — what to do, and when\n",
                 f"\nTotal narration: {timestamp(elapsed)}. Play `out/narration.wav` in one ear,",
                 "\nfollow the cues, and record the screen in silence. Then:\n",
                 "\n    python3 video/assemble.py screen.mov\n\n"]
    for at, name, action in cues:
        cue_sheet.append(f"- **{at}** — {action}\n")
    (OUT / "cues.md").write_text("".join(cue_sheet), encoding="utf-8")

    print(f"\n  narration  {narration}  ({timestamp(elapsed)})")
    print(f"  cue sheet  {OUT / 'cues.md'}")
    print("\n  Record the screen with no sound, then:  python3 video/assemble.py screen.mov")
    return 0


if __name__ == "__main__":
    sys.exit(main())
