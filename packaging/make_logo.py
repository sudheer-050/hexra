"""Draws the Hexra logo: a wave, thick blue outlines, no fill, on white. Writes assets/logo.svg, assets/logo.png and packaging/app.ico.

    python packaging/make_logo.py
"""
import math
import os

from PIL import Image, ImageDraw

BLUE = (31, 91, 255)            # #1F5BFF
STROKE = 36                     # thick outline, in a 512 x 512 design space
SIZE = 512
AMP, WAVELENGTH, XREF = 40, 250.0, 62.0

# three waves in step with each other (one shared sine, so they never touch); the middle one is longest
WAVES = [
    dict(x0=137, x1=387, y=148),
    dict(x0=62, x1=450, y=256),
    dict(x0=137, x1=387, y=364),
]


def points(w, n=240):
    out = []
    for i in range(n + 1):
        x = w["x0"] + (w["x1"] - w["x0"]) * i / n
        y = w["y"] - AMP * math.sin(2 * math.pi * (x - XREF) / WAVELENGTH)
        out.append((x, y))
    return out


def svg():
    paths = []
    for w in WAVES:
        d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in points(w))
        paths.append(f'  <path d="{d}" fill="none" stroke="#1F5BFF" stroke-width="{STROKE}" stroke-linecap="round" stroke-linejoin="round"/>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512" role="img" aria-label="Hexra wave logo">\n'
            '  <rect width="512" height="512" fill="#FFFFFF"/>\n' + "\n".join(paths) + "\n</svg>\n")


def render(px, margin=0.0):
    """Anti-aliased PNG. Each stroke is a round brush stamped densely along the curve (smooth edges and round caps),
    drawn at 4x and shrunk. `margin` shrinks the artwork inside the canvas (for icons)."""
    k = 4
    big = px * k
    scale = big / SIZE * (1 - 2 * margin)
    off = big * margin
    im = Image.new("RGB", (big, big), "white")
    d = ImageDraw.Draw(im)
    r = STROKE * scale / 2
    for w in WAVES:
        for x, y in points(w, n=900):
            X, Y = x * scale + off, y * scale + off
            d.ellipse((X - r, Y - r, X + r, Y + r), fill=BLUE)
    return im.resize((px, px), Image.LANCZOS)


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(os.path.join(root, "assets"), exist_ok=True)
    open(os.path.join(root, "assets", "logo.svg"), "w", encoding="utf-8").write(svg())
    render(1024).save(os.path.join(root, "assets", "logo.png"))
    icon = render(256, margin=0.04)
    icon.save(os.path.join(root, "packaging", "app.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote assets/logo.svg, assets/logo.png, packaging/app.ico")


if __name__ == "__main__":
    main()
