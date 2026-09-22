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

    menu = pystray.Menu(
        pystray.MenuItem("● NoScam Active", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open Guardian Dashboard", open_dashboard, default=True),
        pystray.MenuItem("View Audit Log", open_audit),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit NoScam", quit_app),
    )

    icon = pystray.Icon("NoScam", image, "NoScam: Active", menu=menu)
    icon.run()
