#!/usr/bin/env bash
# Install NoScam as a macOS LaunchAgent so it starts automatically at login.
#
# Usage:
#   ./scripts/install_launchagent.sh             # Install and load
#   ./scripts/install_launchagent.sh --uninstall # Unload and remove

set -euo pipefail

LABEL="com.noscam.desktop"
PLIST_PATH="$HOME/Library/LaunchAgents/${LABEL}.plist"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${1:-}" == "--uninstall" ]]; then
    if [[ -f "$PLIST_PATH" ]]; then
        echo "Unloading LaunchAgent..."
        launchctl unload "$PLIST_PATH" 2>/dev/null || true
        rm -f "$PLIST_PATH"
        echo "NoScam LaunchAgent removed."
    else
        echo "LaunchAgent not found at $PLIST_PATH."
    fi
    exit 0
fi

mkdir -p "$HOME/Library/LaunchAgents"

PYTHON_BIN="$(which python3)"
ENTRY_POINT="$ROOT_DIR/noscam.py"

cat <<EOF > "$PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_BIN}</string>
        <string>${ENTRY_POINT}</string>
        <string>--tray</string>
        <string>--no-open</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>${ROOT_DIR}</string>
    <key>StandardOutPath</key>
    <string>/tmp/noscam.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/noscam.stderr.log</string>
</dict>
</plist>
EOF

echo "Created LaunchAgent at $PLIST_PATH"
launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"
echo "NoScam is now registered to start automatically at user login."
