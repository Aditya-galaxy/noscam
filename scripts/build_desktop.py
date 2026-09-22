"""
Automated PyInstaller build script for NoScam desktop application.

Usage:
    python3 scripts/build_desktop.py
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"


def check_prerequisites():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is required to build the standalone desktop app.")
        print("Install it with: pip install pyinstaller pillow pystray")
        sys.exit(1)


def build():
    check_prerequisites()
    os_name = platform.system().lower()
    sep = ";" if os_name == "windows" else ":"

    print(f"Building NoScam standalone desktop binary for {platform.system()}...")

    # Data folders to embed inside the standalone binary
    data_args = [
        f"--add-data=service{sep}service",
        f"--add-data=web{sep}web",
        f"--add-data=extension{sep}extension",
        f"--add-data=demo{sep}demo",
    ]

    hidden_imports = [
        "--hidden-import=uvicorn.logging",
        "--hidden-import=uvicorn.loops",
        "--hidden-import=uvicorn.loops.auto",
        "--hidden-import=uvicorn.protocols",
        "--hidden-import=uvicorn.protocols.http",
        "--hidden-import=uvicorn.protocols.http.auto",
        "--hidden-import=uvicorn.protocols.websockets",
        "--hidden-import=uvicorn.protocols.websockets.auto",
        "--hidden-import=uvicorn.lifespan",
        "--hidden-import=uvicorn.lifespan.on",
        "--hidden-import=pystray",
        "--hidden-import=PIL",
        "--hidden-import=fastapi",
        "--hidden-import=pydantic",
    ]

    icon_path = ROOT / "web" / "icon-512.png"
    icon_arg = [f"--icon={icon_path}"] if icon_path.exists() else []

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconsole",
        "--name=NoScam",
        "--clean",
        "-y",
        *data_args,
        *hidden_imports,
        *icon_arg,
        str(ROOT / "noscam.py"),
    ]

    print(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print("Build failed.")
        sys.exit(result.returncode)

    print("\nStandalone build succeeded!")
    if os_name == "darwin":
        app_path = DIST / "NoScam.app"
        print(f"macOS Application: {app_path}")
    elif os_name == "windows":
        exe_path = DIST / "NoScam" / "NoScam.exe"
        print(f"Windows Executable: {exe_path}")
    else:
        bin_path = DIST / "NoScam" / "NoScam"
        print(f"Linux Binary: {bin_path}")


if __name__ == "__main__":
    build()
