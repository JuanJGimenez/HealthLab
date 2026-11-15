"""Draw the app icon and save it as ``misalud.ico``.

The icon is kept in the repository; run this script only to change it:
``python release/make_icon.py``. It needs the Pillow library.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 256
BACKGROUND = (20, 92, 122)
LINE = (255, 255, 255)
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

# A pulse line across the icon, as fractions of its size.
PULSE = [
    (0.14, 0.52),
    (0.34, 0.52),
    (0.42, 0.30),
    (0.52, 0.74),
    (0.60, 0.44),
    (0.66, 0.52),
    (0.86, 0.52),
]


def draw_icon() -> Image.Image:
    """Return the icon: a rounded square with a pulse line."""
    scale = 4  # draw large and shrink, for smooth edges
    side = SIZE * scale
    image = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, side - 1, side - 1), radius=side // 5, fill=BACKGROUND)
    points = [(x * side, y * side) for x, y in PULSE]
    draw.line(points, fill=LINE, width=side // 14, joint="curve")
    return image.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


if __name__ == "__main__":
    target = Path(__file__).resolve().parent / "misalud.ico"
    draw_icon().save(target, sizes=SIZES)
    print(target)
