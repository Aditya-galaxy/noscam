"""
Is there a newer NoScam?

The extension updates itself through the store; this service does not, which is
the wrong way round for a security tool. So once a day it asks GitHub which
release is newest and, if it is not this one, says so — in the phone app and on
the console. It never downloads or installs anything by itself: nothing that can
change what the gate does should change without the household noticing.

The request carries nothing about the household. Set NOSCAM_NO_UPDATE_CHECK=1
to turn it off.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Any, Optional

import httpx

from . import __version__

logger = logging.getLogger("noscam.updates")

RELEASES_API = "https://api.github.com/repos/Aditya-galaxy/noscam/releases/latest"
RELEASES_PAGE = "https://github.com/Aditya-galaxy/noscam/releases/latest"
CHECK_EVERY = 24 * 60 * 60

_latest: Optional[str] = None
_checked_at: Optional[float] = None


def parse_version(text: str) -> tuple[int, ...]:
    """'v1.10.2' -> (1, 10, 2). Anything unparseable sorts as oldest."""
    numbers = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in numbers[:3]) or (0,)


def is_newer(candidate: str, current: str = __version__) -> bool:
    return parse_version(candidate) > parse_version(current)


def enabled() -> bool:
    return os.environ.get("NOSCAM_NO_UPDATE_CHECK") != "1"


def check_now() -> Optional[str]:
    global _latest, _checked_at
    try:
        response = httpx.get(RELEASES_API, timeout=8.0,
                             headers={"Accept": "application/vnd.github+json",
                                      "User-Agent": f"NoScam/{__version__}"})
        if response.status_code == 200:
            _latest = str(response.json().get("tag_name") or "").lstrip("v") or None
    except Exception as exc:                          # offline is normal, not an error
        logger.debug(f"update check failed: {exc}")
    _checked_at = time.time()
    return _latest


def status() -> dict[str, Any]:
    return {
        "current": __version__,
        "latest": _latest,
        "update_available": bool(_latest and is_newer(_latest)),
        "url": RELEASES_PAGE,
        "checking": enabled(),
    }


def start_background_checks(on_newer=None) -> None:
    """Check now and then once a day, on a daemon thread."""
    if not enabled():
        return

    def loop() -> None:
        announced = None
        while True:
            latest = check_now()
            if latest and is_newer(latest) and latest != announced and on_newer:
                announced = latest
                on_newer(latest)
            time.sleep(CHECK_EVERY)

    threading.Thread(target=loop, daemon=True, name="noscam-updates").start()
