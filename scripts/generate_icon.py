"""Generate the WinFix AI app icon: three panes and a verified check.

Follows the design specification: drawn on a 256 px grid (16 px padding,
104 px panes, 16 px gaps, r 54 badge) and hinted separately at 16, 24, 32 and
48 px so pane edges land on whole pixels. Outputs:

* app/gui/assets/winfix.svg  — vector master
* app/gui/assets/winfix.png  — 256 px
* app/gui/assets/winfix.ico  — 16, 20, 24, 32, 40, 48, 64, 128, 256 px

    python scripts/generate_icon.py      (needs Pillow; assets are committed)
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "app" / "gui" / "assets"

PANE = ((0x2E, 0x8D, 0xE0), (0x0B, 0x5C, 0xAD))
BADGE = ((0x25, 0xA5, 0x5E), (0x0E, 0x7A, 0x3E))
CHECK = (255, 255, 255)

# Per-size grid: (padding, pane, gap). Every pane edge is a whole pixel.
HINTS = {16: (1, 6, 2), 20: (1, 8, 2), 24: (2, 9, 2), 32: (2, 13, 2), 40: (3, 16, 2),
         48: (3, 19, 4)}
MASTER = (16, 104, 16)
SUPERSAMPLE = 8


def _gradient(size: int, colors) -> Image.Image:
    """Diagonal gradient (top-left light to bottom-right dark)."""
    (r1, g1, b1), (r2, g2, b2) = colors
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / max(1, 2 * size - 2)
            px[x, y] = (round(r1 + (r2 - r1) * t), round(g1 + (g2 - g1) * t),
                        round(b1 + (b2 - b1) * t))
    return img


def render(size: int) -> Image.Image:
    pad, pane, gap = HINTS.get(size) or tuple(round(v * size / 256) for v in MASTER)
    s = SUPERSAMPLE
    big = size * s
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    radius = max(1, round(pane * 0.2)) * s
    origins = [(pad, pad), (pad + pane + gap, pad), (pad, pad + pane + gap)]

    for ox, oy in origins:
        tile = _gradient(pane * s, PANE)
        mask = Image.new("L", tile.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, tile.size[0] - 1, tile.size[1] - 1],
                                               radius=radius, fill=255)
        canvas.paste(tile, (ox * s, oy * s), mask)

    # Badge: a circle centred on the fourth cell, slightly larger than the cell.
    cx = cy = (pad + pane + gap + pane / 2) * s
    r = pane * (54 / 104) * s
    badge_box = [round(cx - r), round(cy - r), round(cx + r), round(cy + r)]
    badge = _gradient(badge_box[2] - badge_box[0], BADGE)
    mask = Image.new("L", badge.size, 0)
    ImageDraw.Draw(mask).ellipse([0, 0, badge.size[0] - 1, badge.size[1] - 1], fill=255)
    canvas.paste(badge, (badge_box[0], badge_box[1]), mask)

    draw = ImageDraw.Draw(canvas)
    stroke = max(1.6 * s, r * 0.3)
    points = [(cx - r * 0.42, cy + r * 0.02), (cx - r * 0.12, cy + r * 0.32),
              (cx + r * 0.45, cy - r * 0.3)]
    draw.line(points, fill=CHECK, width=round(stroke), joint="curve")
    for x, y in (points[0], points[-1]):
        h = stroke / 2
        draw.ellipse([x - h, y - h, x + h, y + h], fill=CHECK)

    return canvas.resize((size, size), Image.LANCZOS)


def svg() -> str:
    pad, pane, gap = MASTER
    rects = "".join(
        f'<rect x="{x}" y="{y}" width="{pane}" height="{pane}" rx="21" fill="url(#pane)"/>'
        for x, y in ((pad, pad), (pad + pane + gap, pad), (pad, pad + pane + gap)))
    c = pad + pane + gap + pane / 2
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">'
        '<defs><linearGradient id="pane" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#2E8DE0"/><stop offset="1" stop-color="#0B5CAD"/>'
        '</linearGradient><linearGradient id="badge" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#25A55E"/><stop offset="1" stop-color="#0E7A3E"/>'
        f'</linearGradient></defs>{rects}<circle cx="{c}" cy="{c}" r="54" fill="url(#badge)"/>'
        f'<path d="M{c - 23} {c + 1} L{c - 6.5} {c + 17.5} L{c + 24} {c - 16}" fill="none" '
        'stroke="#FFFFFF" stroke-width="16" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>\n")


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / "winfix.svg").write_text(svg(), encoding="utf-8")
    master = render(256)
    master.save(ASSETS / "winfix.png")
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    frames = [render(s) for s in sizes]
    frames[-1].save(ASSETS / "winfix.ico", format="ICO", sizes=[(s, s) for s in sizes],
                    append_images=frames[:-1])
    print("Wrote winfix.svg, winfix.png and winfix.ico "
          f"({', '.join(str(s) for s in sizes)} px)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
