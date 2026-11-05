"""
System tray companion for NoScam.

Runs in the macOS menu bar or Windows system tray, displaying live status,
quick links to the guardian dashboard, phone pairing, and a clean exit.

When pystray or Pillow is not installed, `is_available()` returns False,
allowing NoScam to fall back seamlessly to console/headless mode.
"""

from __future__ import annotations

import logging
import os
import webbrowser
from typing import Callable

logger = logging.getLogger("noscam.tray")


def is_available() -> bool:
    """Returns True if system tray libraries (pystray, PIL) are installed."""
    try:
        import PIL.Image  # noqa: F401
        import pystray  # noqa: F401
        return True
    except ImportError:
        return False


def _load_icon_image():
    from PIL import Image, ImageDraw

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    icon_paths = [
        os.path.join(here, "web", "icon-192.png"),
        os.path.join(here, "extension", "icons", "icon-192.png"),
    ]
    for path in icon_paths:
        if os.path.exists(path):
            try:
                return Image.open(path)
            except Exception:
                pass

    # Fallback: Draw a crisp shield/circle icon programmatically
    img = Image.new("RGBA", (64, 64), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 60, 60), fill=(20, 20, 20), outline=(50, 205, 50), width=4)
    draw.ellipse((22, 22, 42, 42), fill=(50, 205, 50))
    return img


def run_tray(port: int, on_quit: Callable[[], None], lan: bool = False) -> None:
    """Run the system tray icon loop. Must be called on the main thread on macOS."""
    if not is_available():
        logger.warning("pystray or PIL not installed. Running in headless mode.")
        return

    import pystray

    app_url = f"http://127.0.0.1:{port}/app/"
    image = _load_icon_image()

    def open_dashboard(icon, item):
        webbrowser.open(app_url)

    def open_audit(icon, item):
        webbrowser.open(f"{app_url}#history")

    def quit_app(icon, item):
        icon.stop()
        on_quit()

    from . import autostart, updates
    from .paths import is_store_package

    def toggle_autostart(icon, item):
        if autostart.is_enabled():
            autostart.disable()
        else:
            autostart.enable()

    def open_release(icon, item):
        webbrowser.open(updates.RELEASES_PAGE)

    from . import guard

    def open_install(icon, item):
        webbrowser.open("https://aditya-galaxy.github.io/noscam/#install")

    def headline(item=None) -> str:
        st = guard.status()
        mark = {"protected": "✓", "unprotected": "⚠", "warning": "⚠"}[st["state"]]
        return f"{mark} {st['headline']}"

    menu = pystray.Menu(
        # Live, not a constant: a green "Active" over an unconnected browser
        # is the one lie a security tool must not tell.
        pystray.MenuItem(headline, open_dashboard, enabled=True),
        pystray.MenuItem("Install the browser extension…", open_install,
                         visible=lambda item: not guard.extension_connected()),
        pystray.MenuItem(lambda item: f"Update available: {updates.status()['latest']}",
                         open_release,
                         visible=lambda item: updates.status()["update_available"]),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open Guardian Dashboard", open_dashboard, default=True),
        pystray.MenuItem("View Audit Log", open_audit),
        # A Store install starts at login through the startup task in its
        # manifest, switched off in Settings → Apps → Startup, not from here.
        pystray.MenuItem("Start at login", toggle_autostart,
                         checked=lambda item: autostart.is_enabled(),
                         visible=lambda item: not is_store_package()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit NoScam", quit_app),
    )

    icon = pystray.Icon("NoScam", image, "NoScam", menu=menu)

    def refresh() -> None:
        icon.title = f"NoScam — {guard.status()['headline']}"
        try:
            icon.update_menu()
        except Exception:                      # noqa: BLE001 — some backends redraw on open anyway
            pass

    def show(title: str, message: str) -> None:
        try:
            icon.notify(message, title)
        except Exception:                      # noqa: BLE001 — no notification support here
            logger.info("%s: %s", title, message)

    guard.on_status_change(refresh)
    guard.on_alert(show)

    def setup(icon) -> None:
        icon.visible = True
        refresh()

    icon.run(setup=setup)
