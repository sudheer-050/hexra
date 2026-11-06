"""Draws the Hexra logo: three overlapping breaking waves, thick blue outlines, no fill, on white.
Writes assets/logo.svg, assets/logo.png and packaging/app.ico.

    python packaging/make_logo.py [preview.png]      (with a path: write only a one-wave preview there)

The wave is an original drawing: one flowing line (a long swell rising into a curling crest that spirals inward), smoothed
with a centripetal Catmull-Rom spline and copied three times, each lower and further right, so they overlap.
"""
import os
import sys

from PIL import Image, ImageDraw

BLUE = (31, 91, 255)            # #1F5BFF
SIZE = 512

# one wave, facing right, in a 0..512 box: the swell from the left, up to the crest, over the lip and into the curl
WAVE = [
    (18, 336), (90, 330), (158, 300), (204, 244), (236, 178), (284, 124), (350, 100), (416, 114), (456, 160),
    (464, 212), (440, 248), (404, 256), (376, 236),
]
# (scale, X0, Y0, stroke): where each copy's left end starts on the canvas
LAYERS = [
    (0.80, 42, 262, 24),
    (0.80, 76, 346, 24),
    (0.80, 110, 430, 24),
]


def catmull_rom(pts, per=40, alpha=0.5):
    """Open centripetal Catmull-Rom spline through `pts` (the end points are repeated so the curve reaches them)."""
    P = [pts[0]] + list(pts) + [pts[-1]]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]

        def tj(ti, a, b):
            return ti + (((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5) ** alpha + 1e-9

        t0 = 0.0
        t1 = tj(t0, p0, p1)
        t2 = tj(t1, p1, p2)
        t3 = tj(t2, p2, p3)
        for k in range(per):
            t = t1 + (t2 - t1) * k / per
            a1 = [(t1 - t) / (t1 - t0) * p0[d] + (t - t0) / (t1 - t0) * p1[d] for d in (0, 1)]
            a2 = [(t2 - t) / (t2 - t1) * p1[d] + (t - t1) / (t2 - t1) * p2[d] for d in (0, 1)]
            a3 = [(t3 - t) / (t3 - t2) * p2[d] + (t - t2) / (t3 - t2) * p3[d] for d in (0, 1)]
            b1 = [(t2 - t) / (t2 - t0) * a1[d] + (t - t0) / (t2 - t0) * a2[d] for d in (0, 1)]
            b2 = [(t3 - t) / (t3 - t1) * a2[d] + (t - t1) / (t3 - t1) * a3[d] for d in (0, 1)]
            out.append(tuple((t2 - t) / (t2 - t1) * b1[d] + (t - t1) / (t2 - t1) * b2[d] for d in (0, 1)))
    out.append(P[-2])
    return out


def layer_points(scale, x0, y0, per=40):
    return [(x0 + (x - 18) * scale, y0 + (y - 336) * scale) for x, y in catmull_rom(WAVE, per)]


def svg():
    paths = []
    for scale, x0, y0, stroke in LAYERS:
        d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in layer_points(scale, x0, y0))
        paths.append(f'  <path d="{d}" fill="none" stroke="#1F5BFF" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round"/>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512" role="img" aria-label="Hexra logo: three overlapping waves">\n'
            '  <rect width="512" height="512" fill="#FFFFFF"/>\n' + "\n".join(paths) + "\n</svg>\n")


def render(px, layers=LAYERS, margin=0.0):
    """Anti-aliased PNG: a round brush stamped densely along each line, drawn at 4x and shrunk."""
    k = 4
    big = px * k
    f = big / SIZE * (1 - 2 * margin)
    off = big * margin
    im = Image.new("RGB", (big, big), "white")
    d = ImageDraw.Draw(im)
    for scale, x0, y0, stroke in layers:
        r = stroke * f / 2
        pts = layer_points(scale, x0, y0, per=120)
        for (x, y), (nx, ny) in zip(pts, pts[1:]):
            for u in (0.0, 0.5):                                   # stamp between samples too, so the line has no gaps
                X, Y = (x + (nx - x) * u) * f + off, (y + (ny - y) * u) * f + off
                d.ellipse((X - r, Y - r, X + r, Y + r), fill=BLUE)
        X, Y = pts[-1][0] * f + off, pts[-1][1] * f + off
        d.ellipse((X - r, Y - r, X + r, Y + r), fill=BLUE)
    return im.resize((px, px), Image.LANCZOS)


def main():
    if len(sys.argv) > 1:
        render(512, layers=[(1.0, 30, 340, 28)]).save(sys.argv[1])
        print("preview written to", sys.argv[1])
        return
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(os.path.join(root, "assets"), exist_ok=True)
    open(os.path.join(root, "assets", "logo.svg"), "w", encoding="utf-8").write(svg())
    render(1024).save(os.path.join(root, "assets", "logo.png"))
    heavy = [(sc, x0, y0, 36) for sc, x0, y0, _ in LAYERS]           # a heavier line keeps the small icon sizes readable
    render(256, layers=heavy, margin=0.04).save(os.path.join(root, "packaging", "app.ico"),
                                  sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote assets/logo.svg, assets/logo.png, packaging/app.ico")


if __name__ == "__main__":
    main()
