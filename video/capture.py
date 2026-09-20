"""
Photograph the product, one state at a time.

    python3 video/capture.py

Every frame is the real extension logic, the real gate and the real phone app,
rendered by a real browser — headless, so the capture is identical every run and
nobody's desktop, notifications or other tabs end up in the film.

The household is reset first, then each scene is set up through the same API the
phone uses, so what is photographed is the product's actual state rather than a
mock-up of it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
FRAMES = HERE / "frames"
SERVICE = "http://127.0.0.1:8787"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

DESKTOP = (1440, 900)
PHONE = (430, 880)

SCAM_PAYMENT = {
    "action": {"type": "payment", "host": "hdfc-secure.example",
               "amount": 18000, "payee": "RBI Safe Custody A/C"},
}


def call(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f"{SERVICE}{path}", data=data, method=method,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read() or "{}")


def shoot(name: str, url: str, size: tuple[int, int], wait_ms: int = 4000) -> Path:
    """One frame. `wait_ms` is virtual time, which lets the page's own timers and
    the gate's round trip finish before the shutter."""
    out = FRAMES / f"{name}.png"
    subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
         f"--window-size={size[0]},{size[1]}",
         f"--virtual-time-budget={wait_ms}",
         f"--screenshot={out}", url],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
    print(f"  {name:22} {out.stat().st_size // 1000:>4} KB")
    return out


def scorecard_page() -> str:
    """The real scorecard, in a page that looks like the terminal it came from."""
    result = subprocess.run([sys.executable, str(HERE.parent / "eval" / "score.py")],
                            capture_output=True, text=True, cwd=HERE.parent)
    body = (result.stdout or "").replace("&", "&amp;").replace("<", "&lt;")
    page = HERE / "frames" / "scorecard.html"
    page.write_text(f"""<!doctype html><meta charset="utf-8"><title>scorecard</title>
<style>
  body {{ margin: 0; background: #0b0b0d; color: #e7e7ea; display: grid;
         place-items: center; height: 100vh;
         font: 13px/1.45 ui-monospace, "SF Mono", Menlo, monospace; }}
  pre {{ margin: 0; padding: 26px 30px; }}
  b {{ color: #fff; }}
</style>
<pre>{body}</pre>""", encoding="utf-8")
    return page.as_uri()


def main() -> int:
    if not Path(CHROME).exists():
        print("Google Chrome is needed to photograph the pages.")
        return 1
    try:
        call("GET", "/health")
    except Exception:
        print("Start it first:  python3 noscam.py")
        return 1

    if FRAMES.exists():
        shutil.rmtree(FRAMES)
    FRAMES.mkdir(parents=True)

    print("\n  Resetting the household so every run photographs the same product.\n")
    call("PUT", "/limits", {"currency": "INR", "per_transaction_cap": 25000,
                            "daily_cap": 50000, "new_payee_cooling_minutes": 10,
                            "block_remote_access": True, "guardian_name": "Priya"})
    call("POST", "/household/payees", {"payees": ["Landlord", "Electricity Board", "Aarav"]})
    call("POST", "/household/reset")

    # 1–2. The message, and the page it opens.
    shoot("01-message", "http://localhost:8790/", DESKTOP, 3000)
    shoot("02-fake-bank", "http://localhost:8791/transfer.html", DESKTOP, 3000)

    # 3–4. The payment held, then the same card once the advice arrives.
    #
    # These start in the message and follow the link, rather than loading the
    # payment page directly: the referrer is what tells the gate a message sent
    # this person here, and without it the product correctly makes a *different*
    # and much less interesting decision.
    scam_journey = "http://localhost:8790/?auto=open&target=transfer"
    shoot("03-held", scam_journey, DESKTOP, 9000)
    shoot("04-held-advice", scam_journey, DESKTOP, 20000)

    # 5. The phone, with that request waiting on it.
    hold = call("POST", "/gate/check", {
        **SCAM_PAYMENT,
        "provenance": {"origin": "link", "source_host": "web.whatsapp.com",
                       "at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())},
    })
    shoot("05-phone-approval", f"{SERVICE}/app/", PHONE, 4000)

    # 6. Approved on the other device — and the desktop can continue.
    if hold.get("hold_id"):
        call("POST", f"/holds/{hold['hold_id']}/decision", {"verdict": "approve", "by": "Priya"})
    shoot("06-phone-empty", f"{SERVICE}/app/", PHONE, 4000)

    # 7. The honest half: an ordinary payment, untouched.
    shoot("07-ordinary", "http://localhost:8791/index.html?auto=pay", DESKTOP, 6000)

    # 8. Gift cards, refused outright.
    shoot("08-giftcards", "http://localhost:8790/?auto=open&target=gift", DESKTOP, 9000)

    # 9. A UPI collect request, decoded on the phone.
    upi = "upi%3A%2F%2Fpay%3Fpa%3Drefund.dept%40okaxis%26pn%3DHDFC%2520Bank%2520Refund%26am%3D"
    shoot("09-phone-upi", f"{SERVICE}/app/?url={upi}", PHONE, 8000)

    # 10. What it has done this week.
    shoot("10-phone-history", f"{SERVICE}/app/?tab=history", PHONE, 5000)

    # 11. The number, and the column nobody else prints.
    shoot("11-scorecard", scorecard_page(), DESKTOP, 2500)

    print(f"\n  {len(list(FRAMES.glob('*.png')))} frames in {FRAMES}")
    print("  Next:  python3 video/build.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
