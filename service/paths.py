"""
Where NoScam's files are, whichever way it was installed.

Three ways it runs, and each puts things somewhere different:

  - a clone of the repository: everything sits next to `service/`, and the
    household lives in `data/` beside it, as it always has;
  - `pipx install noscam`: the code is in site-packages, the phone app and the
    extension are installed as data files under `<prefix>/share/noscam`;
  - the desktop app (PyInstaller): everything is unpacked under `sys._MEIPASS`,
    which is read-only, and the app is started from Finder or Explorer with a
    working directory of `/` or `C:\\Windows\\System32`.

So the household never goes in "the current directory" or next to the code
unless this is a checkout. For everyone else it goes where the platform keeps
per-user application data, where it survives upgrades and can be written.
"""

from __future__ import annotations

import os
import site
import sys

APP_NAME = "NoScam"
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_PACKAGE_DIR)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def is_checkout() -> bool:
    """Running from a clone of the repository, rather than an installed copy."""
    return not is_frozen() and os.path.isdir(os.path.join(_REPO_ROOT, ".git"))


def _candidate_roots() -> list[str]:
    roots = []
    if is_frozen():
        roots.append(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
    roots.append(_REPO_ROOT)
    roots.append(os.path.join(sys.prefix, "share", "noscam"))
    try:
        roots.append(os.path.join(site.getuserbase(), "share", "noscam"))
    except Exception:                                  # noqa: BLE001 — site can be stubbed out
        pass
    return roots


def resource_root() -> str:
    """The folder that holds `web/`, `extension/` and `demo/`."""
    for root in _candidate_roots():
        if os.path.isdir(os.path.join(root, "web")):
            return root
    return _REPO_ROOT


def resource(*parts: str) -> str:
    return os.path.join(resource_root(), *parts)


def user_data_dir() -> str:
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
        return os.path.join(base, APP_NAME)
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
        return os.path.join(base, APP_NAME)
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "noscam")


def data_dir() -> str:
    """Where the household lives: the audit log, payees, limits and the token
    that lets a phone approve payments."""
    override = os.environ.get("NOSCAM_DATA")
    if override:
        return override
    if is_checkout():
        return os.path.join(_REPO_ROOT, "data")
    return user_data_dir()
