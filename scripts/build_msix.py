"""
Package the Windows build as an MSIX for the Microsoft Store.

    python scripts/build_desktop.py      # first: dist/NoScam/ (PyInstaller, onedir)
    python scripts/build_msix.py         # then:  dist/NoScam-<version>-x64.msix

Why MSIX rather than the Inno Setup installer: the Store signs MSIX packages
itself after certification, so a Store install needs no code-signing
certificate and meets no SmartScreen warning. The .exe installer stays for
people who download from GitHub.

Package identity must match what Partner Center reserved for the app, exactly,
or the upload is rejected. Copy the three values from Partner Center →
the app → Product identity, and pass them in the environment:

    MSIX_IDENTITY_NAME            e.g. 12345AdityaKumar.NoScam
    MSIX_PUBLISHER                e.g. CN=1A2B3C4D-....
    MSIX_PUBLISHER_DISPLAY_NAME   e.g. Aditya Kumar

Without them the package uses placeholder identity: fine for a local test
install, rejected by the Store.

To install a test build on your own PC before uploading, sign it with a
self-signed certificate whose subject equals MSIX_PUBLISHER and set
MSIX_PFX / MSIX_PFX_PASSWORD (see docs/MICROSOFT_STORE_SUBMISSION.md). Store
uploads should be left unsigned; the Store signs them.

    --no-pack   write the staging folder and manifest only (works on any OS)
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
STAGE = ROOT / "build" / "msix"
ICON = ROOT / "web" / "icon-512.png"

sys.path.insert(0, str(ROOT))
from service import __version__  # noqa: E402

PLACEHOLDER_NAME = "NoScam.Local"
PLACEHOLDER_PUBLISHER = "CN=NoScamLocalTest"

DESCRIPTION = ("Stops scam messages from authorising payments, one-time codes and "
               "remote-control installs. Runs on this PC; nothing about your money "
               "leaves it.")

# What the manifest refers to, and the size each must be.
ASSETS = {
    "StoreLogo.png": (50, 50),
    "Square44x44Logo.png": (44, 44),
    "Square71x71Logo.png": (71, 71),
    "Square150x150Logo.png": (150, 150),
    "Square310x310Logo.png": (310, 310),
    "Wide310x150Logo.png": (310, 150),
}


def store_version(version: str) -> str:
    """'1.2.1' -> '1.2.1.0'. The fourth part is reserved by the Store and must be 0."""
    parts = [int(p) for p in version.split(".")[:3]]
    parts += [0] * (3 - len(parts))
    return ".".join(str(p) for p in parts) + ".0"


def make_assets(out: Path) -> None:
    from PIL import Image

    out.mkdir(parents=True, exist_ok=True)
    source = Image.open(ICON).convert("RGBA")
    for name, (w, h) in ASSETS.items():
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        side = min(w, h)
        # Square icons fill ~80% of the tile, as Windows' own icons do;
        # the wide tile centres the same icon.
        size = int(side * 0.8) if name != "StoreLogo.png" else side
        icon = source.resize((size, size), Image.LANCZOS)
        canvas.paste(icon, ((w - size) // 2, (h - size) // 2), icon)
        canvas.save(out / name)


def manifest(name: str, publisher: str, publisher_display: str, version: str) -> str:
    e = lambda s: escape(s, {'"': "&quot;"})  # noqa: E731
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Package
  xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
  xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
  xmlns:uap3="http://schemas.microsoft.com/appx/manifest/uap/windows10/3"
  xmlns:desktop="http://schemas.microsoft.com/appx/manifest/desktop/windows10"
  xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
  IgnorableNamespaces="uap uap3 desktop rescap">

  <Identity Name="{e(name)}" Publisher="{e(publisher)}" Version="{version}" ProcessorArchitecture="x64" />

  <Properties>
    <DisplayName>NoScam</DisplayName>
    <PublisherDisplayName>{e(publisher_display)}</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
    <Description>{e(DESCRIPTION)}</Description>
  </Properties>

  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.26100.0" />
  </Dependencies>

  <Resources>
    <Resource Language="en-us" />
  </Resources>

  <Applications>
    <Application Id="NoScam" Executable="NoScam.exe" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements
        DisplayName="NoScam"
        Description="{e(DESCRIPTION)}"
        BackgroundColor="transparent"
        Square150x150Logo="Assets\\Square150x150Logo.png"
        Square44x44Logo="Assets\\Square44x44Logo.png">
        <uap:DefaultTile Wide310x150Logo="Assets\\Wide310x150Logo.png"
                         Square71x71Logo="Assets\\Square71x71Logo.png"
                         Square310x310Logo="Assets\\Square310x310Logo.png" />
      </uap:VisualElements>
      <Extensions>
        <!-- Start at login. A packaged app's Run-key entry is written to a
             private hive Windows never reads, so this is the only way. The
             person can switch it off in Settings > Apps > Startup. -->
        <desktop:Extension Category="windows.startupTask" Executable="NoScam.exe"
                           EntryPoint="Windows.FullTrustApplication">
          <desktop:StartupTask TaskId="NoScamAtLogin" Enabled="true" DisplayName="NoScam" />
        </desktop:Extension>
        <!-- Lets "noscam" run from a terminal (with the demo option), for testers and anyone who wants
             to see it stop a scam before trusting it with their own bank. -->
        <uap3:Extension Category="windows.appExecutionAlias" Executable="NoScam.exe"
                        EntryPoint="Windows.FullTrustApplication">
          <uap3:AppExecutionAlias>
            <desktop:ExecutionAlias Alias="noscam.exe" />
          </uap3:AppExecutionAlias>
        </uap3:Extension>
      </Extensions>
    </Application>
  </Applications>

  <Capabilities>
    <Capability Name="internetClient" />
    <!-- Only used when the person turns on approval from a phone on the same Wi-Fi. -->
    <Capability Name="privateNetworkClientServer" />
    <!-- A desktop (Win32) app: the local gate service, tray icon and browser launch. -->
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
</Package>
"""


def find_sdk_tool(tool: str) -> str:
    on_path = shutil.which(tool)
    if on_path:
        return on_path
    candidates = glob.glob(rf"C:\Program Files (x86)\Windows Kits\10\bin\*\x64\{tool}")
    if not candidates:
        sys.exit(f"{tool} not found. Install the Windows 10/11 SDK, or run this on a "
                 "GitHub windows runner, which has it.")
    # bin\10.0.22621.0\x64\makeappx.exe — newest SDK last when sorted by version.
    return sorted(candidates, key=lambda p: [int(x) for x in Path(p).parts[-3].split(".")])[-1]


def main() -> int:
    pack = "--no-pack" not in sys.argv
    app_dir = DIST / "NoScam"
    if pack and not (app_dir / "NoScam.exe").exists():
        sys.exit("No dist/NoScam/NoScam.exe — run scripts/build_desktop.py on Windows first.")

    name = os.environ.get("MSIX_IDENTITY_NAME") or PLACEHOLDER_NAME
    publisher = os.environ.get("MSIX_PUBLISHER") or PLACEHOLDER_PUBLISHER
    publisher_display = os.environ.get("MSIX_PUBLISHER_DISPLAY_NAME") or "NoScam"
    version = store_version(__version__)
    if name == PLACEHOLDER_NAME:
        print("MSIX_IDENTITY_NAME / MSIX_PUBLISHER not set: placeholder identity. "
              "Good for a local test, rejected by the Store.")

    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    if app_dir.exists():
        shutil.copytree(app_dir, STAGE, dirs_exist_ok=True)
    make_assets(STAGE / "Assets")
    (STAGE / "AppxManifest.xml").write_text(manifest(name, publisher, publisher_display, version),
                                            encoding="utf-8")
    print(f"Staged {STAGE} (identity {name}, version {version})")
    if not pack:
        return 0

    out = DIST / f"NoScam-{__version__}-x64.msix"
    out.unlink(missing_ok=True)
    subprocess.run([find_sdk_tool("makeappx.exe"), "pack", "/d", str(STAGE), "/p", str(out), "/o"],
                   check=True)

    pfx, password = os.environ.get("MSIX_PFX"), os.environ.get("MSIX_PFX_PASSWORD", "")
    if pfx:
        subprocess.run([find_sdk_tool("signtool.exe"), "sign", "/fd", "SHA256", "/a",
                        "/f", pfx, "/p", password, str(out)], check=True)
        print("Signed with a test certificate — for sideloading only; upload an unsigned build.")
    print(f"Built {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
