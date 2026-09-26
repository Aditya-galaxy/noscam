#!/usr/bin/env bash
# Sign, notarise and wrap dist/NoScam.app in a DMG.
#
#   scripts/package_macos.sh            # -> dist/NoScam-macOS-<arch>.dmg
#
# Signing happens only when these are set (CI secrets, or your own shell):
#   MACOS_SIGN_IDENTITY   "Developer ID Application: Your Name (TEAMID)"
#   APPLE_ID, APPLE_TEAM_ID, APPLE_APP_PASSWORD   for notarytool
# Without them the DMG is unsigned: fine for testing, but every user who
# downloads it meets Gatekeeper's "cannot be opened" wall.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$ROOT/dist/NoScam.app"
ARCH="$(uname -m)"
DMG="$ROOT/dist/NoScam-macOS-${ARCH}.dmg"

[[ -d "$APP" ]] || { echo "No $APP — run scripts/build_desktop.py first."; exit 1; }

if [[ -n "${MACOS_SIGN_IDENTITY:-}" ]]; then
    echo "Signing $APP with hardened runtime..."
    codesign --force --deep --timestamp --options runtime \
        --entitlements "$ROOT/scripts/entitlements.plist" \
        --sign "$MACOS_SIGN_IDENTITY" "$APP"
    codesign --verify --strict --verbose=2 "$APP"
else
    echo "MACOS_SIGN_IDENTITY not set: building an UNSIGNED dmg."
fi

STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"
hdiutil create -volname "NoScam" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
rm -rf "$STAGE"

if [[ -n "${MACOS_SIGN_IDENTITY:-}" ]]; then
    codesign --force --timestamp --sign "$MACOS_SIGN_IDENTITY" "$DMG"
    if [[ -n "${APPLE_ID:-}" && -n "${APPLE_TEAM_ID:-}" && -n "${APPLE_APP_PASSWORD:-}" ]]; then
        echo "Submitting to Apple for notarisation (this can take minutes)..."
        xcrun notarytool submit "$DMG" --apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" \
            --password "$APPLE_APP_PASSWORD" --wait
        xcrun stapler staple "$DMG"
        spctl --assess --type open --context context:primary-signature -v "$DMG"
    else
        echo "Notarisation credentials not set: signed but NOT notarised."
    fi
fi

echo "Built $DMG"
