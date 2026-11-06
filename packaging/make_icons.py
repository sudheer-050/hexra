"""Builds the logo files from the master image assets/logo-original.png (the image is used exactly as drawn, only resized).

    python packaging/make_icons.py

Writes assets/logo.png (1024 x 1024, white background, for the README and the guide) and packaging/app.ico (7 sizes, the
white outside the wave made transparent so the icon has no white box on a dark taskbar).
"""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER = os.path.join(ROOT, "assets", "logo-original.png")
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def transparent_outside(im: Image.Image) -> Image.Image:
    """The wave on a transparent background: only the white connected to the picture's edge is removed, so the white
    foam inside the wave (closed off by its dark outline) stays."""
    rgb = im.convert("RGB")
    key = (255, 0, 255)
    marked = rgb.copy()
    w, h = marked.size
    for xy in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)):
        ImageDraw.floodfill(marked, xy, key, thresh=28)
    alpha = Image.new("L", (w, h), 255)
    px, ap = marked.load(), alpha.load()
    for y in range(h):
        for x in range(w):
            if px[x, y] == key:
                ap[x, y] = 0
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def main():
    master = Image.open(MASTER).convert("RGB")
    master.resize((1024, 1024), Image.LANCZOS).save(os.path.join(ROOT, "assets", "logo.png"), optimize=True)
    cut = transparent_outside(master.resize((512, 512), Image.LANCZOS))
    cut.resize((256, 256), Image.LANCZOS).save(os.path.join(ROOT, "packaging", "app.ico"), sizes=SIZES)
    cut.save(os.path.join(ROOT, "assets", "logo-transparent.png"), optimize=True)
    print("wrote assets/logo.png, assets/logo-transparent.png, packaging/app.ico")


if __name__ == "__main__":
    main()
