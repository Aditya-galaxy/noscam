"""
Render every NoScam icon from one geometry — the same shapes as noscam-mark.svg.

    python3 brand/make_icons.py

Drawn at 8x and scaled down (Lanczos), so edges are anti-aliased at every size,
from the 16 px tray icon to 1024 px store art. Re-run after any change to the mark;
nothing else in the repository should hold its own copy of the logo.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
INK = (11, 11, 11, 255)        # #0b0b0b
PAPER = (251, 251, 250, 255)   # #fbfbfa
SS = 8                         # supersampling factor

# The mark, in a 64-unit box (see noscam-mark.svg).
BODY = (6, 10, 58, 48, 10)                       # x0, y0, x1, y1, corner radius
TAIL = [(27, 48), (16, 57), (16, 48)]
BARS = [(24.5, 19, 30, 39), (34, 19, 39.5, 39)]
# Small sizes (32 px and under): thicker bars and a narrower gap, or the pause sign
# blurs into the bubble and it reads as a plain chat icon.
BARS_SMALL = [(22, 17, 30, 41), (34, 17, 42, 41)]
MARK_CENTRE = (32, 33.5)


def _draw_mark(d: ImageDraw.ImageDraw, scale: float, ox: float, oy: float, fg, cut, small: bool = False) -> None:
    p = lambda x, y: (ox + x * scale, oy + y * scale)  # noqa: E731
    x0, y0, x1, y1, r = BODY
    d.rounded_rectangle([p(x0, y0), p(x1, y1)], radius=r * scale, fill=fg)
    d.polygon([p(*pt) for pt in TAIL], fill=fg)
    for bx0, by0, bx1, by1 in (BARS_SMALL if small else BARS):
        d.rectangle([p(bx0, by0), p(bx1, by1)], fill=cut)


def mark(size: int, fg=INK, bg=(0, 0, 0, 0), padding: float = 0.0, small: bool = False) -> Image.Image:
    """The bare mark, centred, transparent background by default."""
    big = size * SS
    im = Image.new("RGBA", (big, big), bg)
    usable = big * (1 - 2 * padding)
    scale = usable / 64
    ox = (big - 64 * scale) / 2 + (32 - MARK_CENTRE[0]) * scale
    oy = (big - 64 * scale) / 2 + (32 - MARK_CENTRE[1]) * scale
    _draw_mark(ImageDraw.Draw(im), scale, ox, oy, fg, bg, small)
    return im.resize((size, size), Image.LANCZOS)


def app_icon(size: int, radius: float = 14 / 64) -> Image.Image:
    """The mark in off-white on a near-black rounded square."""
    big = size * SS
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, big - 1, big - 1], radius=big * radius, fill=INK)
    small = size <= 32
    scale = big / 64 * (0.84 if small else 0.74)   # fill more of a tiny tile
    ox = big / 2 - MARK_CENTRE[0] * scale
    oy = big / 2 - MARK_CENTRE[1] * scale
    _draw_mark(d, scale, ox, oy, PAPER, INK, small)
    return im.resize((size, size), Image.LANCZOS)


def save(img: Image.Image, rel: str) -> None:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True)
    print(f"  {rel}  {img.size[0]}x{img.size[1]}")


def main() -> None:
    # Phone app / PWA, and the source the desktop builds and the MSIX use.
    save(app_icon(192), "web/icon-192.png")
    save(app_icon(512), "web/icon-512.png")
    # Tray: the bare mark, white for dark taskbars/menu bars, black for light ones.
    # Shown at 16-24 px, so drawn with the small-size bars.
    save(mark(64, fg=PAPER, padding=0.04, small=True), "web/tray-white.png")
    save(mark(64, fg=INK, padding=0.04, small=True), "web/tray-black.png")
    # Browser extension.
    for s in (16, 32, 48, 128, 192, 512):
        save(app_icon(s), f"extension/icons/icon-{s}.png")
    # Android launcher.
    for dens, s in (("mdpi", 48), ("hdpi", 72), ("xhdpi", 96), ("xxhdpi", 144), ("xxxhdpi", 192)):
        save(app_icon(s), f"android/app/src/main/res/mipmap-{dens}/ic_launcher.png")
    # Website.
    save(app_icon(64), "site/public/favicon.png")
    save(app_icon(192), "site/public/icon.png")
    # Brand exports for stores, press and social.
    save(app_icon(1024), "brand/noscam-app-icon-1024.png")
    save(mark(1024, fg=INK, padding=0.06), "brand/noscam-mark-black-1024.png")
    save(mark(1024, fg=PAPER, padding=0.06), "brand/noscam-mark-white-1024.png")
    save(social_card(), "site/public/og.png")
    save(promo_tile(), "docs/store/promo-small-440x280.png")


def _font(size: int, bold: bool = False):
    name = "Arial Bold.ttf" if bold else "Arial.ttf"
    for path in (f"/System/Library/Fonts/Supplemental/{name}", f"C:/Windows/Fonts/{'arialbd' if bold else 'arial'}.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans" + ("-Bold" if bold else "") + ".ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def social_card() -> Image.Image:
    """1200x630 link preview: the mark and the line."""
    im = Image.new("RGBA", (1200, 630), INK)
    m = mark(120, fg=PAPER)
    im.alpha_composite(m, (80, 74))
    d = ImageDraw.Draw(im)
    d.text((214, 104), "NoScam", fill=PAPER, font=_font(52, True))
    d.text((80, 270), "An antivirus for scams.", fill=PAPER, font=_font(76, True))
    d.multiline_text((80, 388), "Stops what a scam message tells you to do —\nthe payment, the OTP, the remote-control app.",
                     fill=(160, 160, 156, 255), font=_font(34), spacing=12)
    d.text((80, 546), "noscam.kronagent.dev", fill=(110, 110, 106, 255), font=_font(26))
    return im.convert("RGB")


def promo_tile() -> Image.Image:
    """440x280 Chrome Web Store small promo tile."""
    im = Image.new("RGBA", (440, 280), INK)
    im.alpha_composite(mark(76, fg=PAPER), (30, 36))
    d = ImageDraw.Draw(im)
    d.text((118, 54), "NoScam", fill=PAPER, font=_font(40, True))
    d.multiline_text((32, 150), "An antivirus for scams.", fill=PAPER, font=_font(24, True))
    d.text((32, 196), "Stops what a scam message tells you to do.", fill=(160, 160, 156, 255), font=_font(15))
    return im.convert("RGB")


if __name__ == "__main__":
    main()
