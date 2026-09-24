"""Generate the WinFix application icon assets.

Produces ``app/gui/assets/winfix.png`` (512px) and ``app/gui/assets/winfix.ico``
(multi-resolution, used by PyInstaller for the Windows executable).

Run this only when the icon design changes; the generated assets are committed
so neither the app nor the build pipeline needs Pillow at runtime.

    python scripts/generate_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "app" / "gui" / "assets"

SIZE = 512
BG_TOP = (59, 130, 246)       # primary blue
BG_BOTTOM = (37, 99, 235)
GLYPH = (255, 255, 255)
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def _rounded_gradient(size: int, radius: int) -> Image.Image:
    """A vertical blue gradient clipped to a rounded square."""
    gradient = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / max(1, size - 1)
        gradient.putpixel((0, y), tuple(
            int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3)
        ))
    gradient = gradient.resize((size, size))

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [(0, 0), (size - 1, size - 1)], radius=radius, fill=255
    )

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(gradient, (0, 0), mask)
    return canvas


def _draw_glyph(image: Image.Image) -> None:
    """Draw a stylised 'W' check-mark: two descending strokes forming a W."""
    draw = ImageDraw.Draw(image)
    w = SIZE
    stroke = int(w * 0.085)

    # A 'W' built from four line segments, weighted like a checkmark.
    points = [
        (w * 0.22, w * 0.34),
        (w * 0.36, w * 0.70),
        (w * 0.50, w * 0.46),
        (w * 0.64, w * 0.70),
        (w * 0.78, w * 0.34),
    ]
    draw.line(points, fill=GLYPH, width=stroke, joint="curve")

    # Round the stroke ends so the glyph reads cleanly at small sizes.
    for point in (points[0], points[-1]):
        r = stroke / 2
        draw.ellipse(
            [point[0] - r, point[1] - r, point[0] + r, point[1] + r], fill=GLYPH
        )


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)

    icon = _rounded_gradient(SIZE, radius=int(SIZE * 0.22))
    _draw_glyph(icon)

    png_path = ASSETS / "winfix.png"
    icon.save(png_path)

    ico_path = ASSETS / "winfix.ico"
    icon.save(ico_path, format="ICO", sizes=ICO_SIZES)

    print(f"Wrote {png_path}")
    print(f"Wrote {ico_path} ({len(ICO_SIZES)} resolutions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
