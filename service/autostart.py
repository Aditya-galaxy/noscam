"""
Start NoScam when the person logs in.

A gate that is only running when somebody remembered to start it is not a gate.
The installed desktop app turns this on the first time it runs, and the tray
menu has a "Start at login" switch to turn it off again. Nothing here needs
administrator rights: each platform has a per-user place for login items.

  macOS    ~/Library/LaunchAgents/org.noscam.desktop.plist
  Windows  HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run  (value "NoScam")
  Linux    ~/.config/autostart/noscam.desktop
"""

from __future__ import annotations

import os
import plistlib
import sys

LABEL = "org.noscam.desktop"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _command() -> list[str]:
    """How to start this copy of NoScam, quietly, without opening a browser."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--no-open"]
    entry = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "noscam.py")
    return [sys.executable, entry, "--tray", "--no-open"]


def _mac_plist_path() -> str:
    return os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")


def _linux_desktop_path() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "autostart", "noscam.desktop")


def is_enabled() -> bool:
    if sys.platform == "darwin":
        return os.path.exists(_mac_plist_path())
    if os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.QueryValueEx(key, "NoScam")
                return True
        except OSError:
            return False
    return os.path.exists(_linux_desktop_path())


def enable() -> None:
    command = _command()
    if sys.platform == "darwin":
        path = _mac_plist_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            # RunAtLoad without KeepAlive: "Quit NoScam" in the menu bar must
            # actually quit, not be undone by launchd a second later.
            plistlib.dump({"Label": LABEL, "ProgramArguments": command,
                           "RunAtLoad": True, "ProcessType": "Interactive"}, fh)
        return
    if os.name == "nt":
        import subprocess
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, "NoScam", 0, winreg.REG_SZ, subprocess.list2cmdline(command))
        return
    path = _linux_desktop_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    exec_line = " ".join(f'"{part}"' if " " in part else part for part in command)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("[Desktop Entry]\nType=Application\nName=NoScam\n"
                 f"Exec={exec_line}\nX-GNOME-Autostart-enabled=true\n")


def disable() -> None:
    if sys.platform == "darwin":
        try:
            os.remove(_mac_plist_path())
        except FileNotFoundError:
            pass
        return
    if os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, "NoScam")
        except OSError:
            pass
        return
    try:
        os.remove(_linux_desktop_path())
    except FileNotFoundError:
        pass


def enable_on_first_run(data_dir: str) -> None:
    """Turn on start-at-login once, the first time the installed app runs. If
    the person later turns it off, that choice sticks."""
    marker = os.path.join(data_dir, ".autostart-offered")
    if os.path.exists(marker):
        return
    try:
        enable()
    except Exception:                                  # noqa: BLE001 — never block startup on this
        pass
    os.makedirs(data_dir, exist_ok=True)
    with open(marker, "w", encoding="utf-8") as fh:
        fh.write("1")
