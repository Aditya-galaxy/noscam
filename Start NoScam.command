#!/bin/bash
# Double-click this on macOS. It installs what is missing the first time,
# then starts NoScam and opens it. Closing the window stops it.
cd "$(dirname "$0")" || exit 1
command -v python3 >/dev/null || { echo "Python 3 is not installed."; read -r; exit 1; }
python3 -c "import fastapi, uvicorn, httpx, pydantic" 2>/dev/null \
  || python3 -m pip install --quiet -r requirements.txt
exec python3 noscam.py
