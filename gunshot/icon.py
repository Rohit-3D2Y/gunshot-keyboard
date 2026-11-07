"""The crosshair icon, drawn in code (used for the tray and the app icons)."""

from __future__ import annotations

from PIL import Image, ImageDraw

RED = (220, 40, 40, 255)
GREY = (130, 130, 130, 255)


def crosshair(size: int = 64, color: tuple = RED) -> Image.Image:
    # Draw at 4x then downscale for smooth edges at any size.
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = max(1, s // 11)
    pad = s // 8
    mid = s // 2
    d.ellipse((pad, pad, s - pad, s - pad), outline=color, width=w)
    d.line((mid, 0, mid, s * 11 // 32), fill=color, width=w)
    d.line((mid, s * 21 // 32, mid, s), fill=color, width=w)
    d.line((0, mid, s * 11 // 32, mid), fill=color, width=w)
    d.line((s * 21 // 32, mid, s, mid), fill=color, width=w)
    r = s // 13
    d.ellipse((mid - r, mid - r, mid + r, mid + r), fill=color)
    return img.resize((size, size), Image.LANCZOS)
