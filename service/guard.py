"""
The part of NoScam that behaves like an antivirus: always on, quiet until it
matters, and honest about whether it is actually protecting anything.

Three jobs:

1. **Protection status.** The gate can only stand in front of a payment if the
   browser extension is asking it. The extension checks in about once a minute;
   if it has not been heard from, the tray says so plainly — "Not protected:
   browser extension not connected" — instead of a reassuring green dot over
   nothing.

2. **Alerts.** When the gate holds or refuses something, a desktop notification
   says what and why, so an action stopped in a background tab is not missed.

3. **Remote-control watch.** "Support" and "digital arrest" callers have the
   person install AnyDesk or TeamViewer first. The browser stops the download,
   but not a copy installed earlier or from elsewhere. Every few seconds this
   looks at the running programs and, when a remote-control tool starts, says
   so: someone may be able to see and control this computer right now.

It reads only process *names*, never their contents, and sends nothing anywhere.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("noscam.guard")

EXTENSION_FRESH_SECONDS = 180      # the extension pings every 60 s
WATCH_INTERVAL_SECONDS = 15

# Lower-case fragments of process names, and the name to show a person.
REMOTE_ACCESS_PROCESSES = {
    "anydesk": "AnyDesk",
    "teamviewer": "TeamViewer",
    "rustdesk": "RustDesk",
    "ultraviewer": "UltraViewer",
    "quicksupport": "QuickSupport",
    "ammyy": "Ammyy Admin",
    "supremo": "Supremo",
    "airdroid": "AirDroid",
    "remotepc": "RemotePC",
    "splashtop": "Splashtop",
    "logmein": "LogMeIn",
    "screenconnect": "ScreenConnect",
    "connectwisecontrol": "ConnectWise Control",
    "zohoassist": "Zoho Assist",
    "chromeremotedesktop": "Chrome Remote Desktop",
    "remoting_host": "Chrome Remote Desktop",
}

_lock = threading.Lock()
_extension_seen_at: Optional[float] = None
_remote_running: list[str] = []
_listeners: list[Callable[[str, str], None]] = []
_status_listeners: list[Callable[[], None]] = []
_last_alert: dict[str, float] = {}


# --- status ------------------------------------------------------------------

def saw_extension(now: Optional[float] = None) -> None:
    global _extension_seen_at
    first = _extension_seen_at is None
    _extension_seen_at = now if now is not None else time.time()
    if first:
        _status_changed()


def extension_connected(now: Optional[float] = None) -> bool:
    now = now if now is not None else time.time()
    return _extension_seen_at is not None and now - _extension_seen_at < EXTENSION_FRESH_SECONDS


def status(now: Optional[float] = None) -> dict:
    now = now if now is not None else time.time()
    connected = extension_connected(now)
    with _lock:
        remote = list(_remote_running)
    if remote:
        state, headline = "warning", f"Remote-control app running: {', '.join(remote)}"
    elif not connected:
        state, headline = "unprotected", "Not protected: browser extension not connected"
    else:
        state, headline = "protected", "Protected"
    return {
        "state": state,
        "headline": headline,
        "extension_connected": connected,
        "extension_last_seen_seconds": None if _extension_seen_at is None
        else int(now - _extension_seen_at),
        "remote_access_running": remote,
    }


# --- alerts ------------------------------------------------------------------

def on_alert(listener: Callable[[str, str], None]) -> None:
    """Called with (title, message) for every alert; the tray shows them."""
    _listeners.append(listener)


def on_status_change(listener: Callable[[], None]) -> None:
    _status_listeners.append(listener)


def alert(title: str, message: str, key: Optional[str] = None, quiet_for: float = 60.0) -> None:
    """Show a notification, at most once per `quiet_for` seconds per key, so a
    page that retries a payment ten times does not produce ten pop-ups."""
    now = time.time()
    if key:
        if now - _last_alert.get(key, 0) < quiet_for:
            return
        _last_alert[key] = now
    logger.info("alert: %s — %s", title, message)
    for listener in list(_listeners):
        try:
            listener(title, message)
        except Exception:                      # noqa: BLE001 — a broken tray must not break the gate
            logger.debug("alert listener failed", exc_info=True)


def _status_changed() -> None:
    for listener in list(_status_listeners):
        try:
            listener()
        except Exception:                      # noqa: BLE001
            logger.debug("status listener failed", exc_info=True)


def describe_decision(action: dict, disposition: str, headline: str) -> Optional[tuple[str, str]]:
    """The notification for a gate decision, or None if it needs none."""
    if disposition == "allow":
        return None
    where = action.get("host") or "a website"
    amount = action.get("amount")
    what = f"₹{amount:,.0f} payment" if isinstance(amount, (int, float)) and amount else \
        str(action.get("type", "action")).replace("_", " ")
    verb = {"blocked": "stopped", "needs_approval": "held", "cool_off": "paused"}.get(disposition, "held")
    return f"NoScam {verb} a {what}", f"{headline} ({where})"


# --- remote-control watch ----------------------------------------------------

def running_process_names() -> list[str]:
    """Names of running programs, lower-case. Never their arguments or data."""
    try:
        if os.name == "nt":
            # CREATE_NO_WINDOW: a windowed app spawning tasklist would otherwise
            # flash a console every few seconds.
            out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True,
                                 timeout=10, creationflags=0x08000000).stdout
            return [line.split('","')[0].strip('"').lower() for line in out.splitlines() if line]
        out = subprocess.run(["ps", "-axo", "comm"], capture_output=True, text=True, timeout=10).stdout
        return [os.path.basename(line.strip()).lower() for line in out.splitlines()[1:] if line.strip()]
    except Exception:                          # noqa: BLE001 — no process list is not an emergency
        return []


def remote_access_in(names: list[str]) -> list[str]:
    found = []
    for name in names:
        squashed = name.replace(" ", "").replace("-", "").replace(".", "")
        for fragment, label in REMOTE_ACCESS_PROCESSES.items():
            if fragment in squashed and label not in found:
                found.append(label)
    return sorted(found)


def check_remote_access(names: Optional[list[str]] = None) -> list[str]:
    """Update what is running; alert on anything that has just started."""
    global _remote_running
    current = remote_access_in(names if names is not None else running_process_names())
    with _lock:
        started = [r for r in current if r not in _remote_running]
        changed = current != _remote_running
        _remote_running = current
    for tool in started:
        alert(f"{tool} is running",
              f"Someone with its code can see and control this computer. If a caller asked you "
              f"to install or open {tool}, hang up and close it. No bank, police or support "
              f"team needs it.", key=f"remote:{tool}", quiet_for=600)
    if changed:
        _status_changed()
    return current


def start(interval: float = WATCH_INTERVAL_SECONDS) -> None:
    """Background watch: remote-control tools, and the extension going quiet."""
    def loop() -> None:
        was_connected = extension_connected()
        while True:
            check_remote_access()
            now_connected = extension_connected()
            if now_connected != was_connected:
                was_connected = now_connected
                _status_changed()
            time.sleep(interval)

    if os.environ.get("NOSCAM_NO_PROCESS_WATCH") == "1" or "pytest" in sys.modules:
        return
    threading.Thread(target=loop, daemon=True, name="noscam-guard").start()
