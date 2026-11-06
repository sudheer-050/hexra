"""Layout helpers and diagrams for the Hexra guide (ReportLab)."""
from __future__ import annotations

from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, PageBreak, PageTemplate, Paragraph, Preformatted,
                                Spacer, Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

NAVY = colors.HexColor("#182848")
BLUE = colors.HexColor("#2f6fdb")
GREEN = colors.HexColor("#2ea66b")
AMBER = colors.HexColor("#d98a1b")
RED = colors.HexColor("#c8453b")
GREY = colors.HexColor("#5b6572")
LIGHT = colors.HexColor("#eef2f8")
LINE = colors.HexColor("#c9d2df")

_ss = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=_ss["BodyText"], fontName="Helvetica", fontSize=10, leading=14.2, spaceAfter=5, alignment=TA_LEFT)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8.6, leading=11.5, textColor=GREY, spaceAfter=3)
H1 = ParagraphStyle("h1", parent=BODY, fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=NAVY, spaceBefore=4, spaceAfter=10)
H2 = ParagraphStyle("h2", parent=BODY, fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=BLUE, spaceBefore=12, spaceAfter=5)
H3 = ParagraphStyle("h3", parent=BODY, fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=NAVY, spaceBefore=8, spaceAfter=3)
BUL = ParagraphStyle("bul", parent=BODY, leftIndent=14, bulletIndent=3, spaceAfter=2.5)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=8.8, leading=11.4, spaceAfter=0)
CELLB = ParagraphStyle("cellb", parent=CELL, fontName="Helvetica-Bold", textColor=colors.white)
CODE = ParagraphStyle("code", parent=BODY, fontName="Courier", fontSize=8.4, leading=10.6, backColor=LIGHT, borderPadding=(5, 6, 5, 6),
                      spaceBefore=4, spaceAfter=9, leftIndent=6, rightIndent=6)


def P(text, style=BODY):
    return Paragraph(text, style)


def B(items, style=BUL):
    return [Paragraph(t, style, bulletText="•") for t in items]


def code(text):
    return Preformatted(text.strip("\n"), CODE)


def callout(title, text, colour=BLUE):
    t = Table([[Paragraph(f"<b>{title}</b><br/>{text}", CELL)]], colWidths=[165 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), LIGHT), ("LINEBEFORE", (0, 0), (0, -1), 3, colour),
                           ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return [t, Spacer(1, 7)]


def table(rows, widths, header=True, zebra=True):
    """rows: list of lists of strings (inline markup allowed)."""
    data = []
    for i, r in enumerate(rows):
        st = CELLB if (header and i == 0) else CELL
        data.append([Paragraph(str(c), st) for c in r])
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if header else 0)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.4, LINE),
             ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
             ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), NAVY))
    if zebra:
        for i in range(1 if header else 0, len(rows)):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), LIGHT))
    t.setStyle(TableStyle(style))
    return [t, Spacer(1, 8)]


# ------------------------------------------------------------------ document with a table of contents
class Doc(BaseDocTemplate):
    def __init__(self, path, title):
        super().__init__(path, pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm, topMargin=20 * mm, bottomMargin=20 * mm,
                         title=title, author="Hexra", subject="User guide and full project history")
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="f")
        self.addPageTemplates([PageTemplate(id="cover", frames=[frame], onPage=self._cover),
                               PageTemplate(id="main", frames=[frame], onPage=self._page)])

    def _cover(self, c, d):
        c.saveState()
        c.setFillColor(NAVY)
        c.rect(0, 0, A4[0], A4[1], stroke=0, fill=1)
        c.restoreState()

    def _page(self, c, d):
        c.saveState()
        c.setStrokeColor(LINE)
        c.line(22 * mm, 15 * mm, A4[0] - 22 * mm, 15 * mm)
        c.setFont("Helvetica", 8)
        c.setFillColor(GREY)
        c.drawString(22 * mm, 10.5 * mm, "Hexra - guide and project history")
        c.drawRightString(A4[0] - 22 * mm, 10.5 * mm, f"Page {d.page}")
        c.restoreState()

    def afterFlowable(self, f):
        if isinstance(f, Paragraph):
            name = f.style.name
            if name in ("h1", "h2"):
                key = f"h{self.seq.nextf('toc')}"
                self.canv.bookmarkPage(key)
                self.notify("TOCEntry", (0 if name == "h1" else 1, f.getPlainText(), self.page, key))


def make_toc():
    toc = TableOfContents()
    toc.levelStyles = [ParagraphStyle("t0", fontName="Helvetica-Bold", fontSize=10.5, leading=15, leftIndent=0, spaceBefore=4),
                       ParagraphStyle("t1", fontName="Helvetica", fontSize=9, leading=12, leftIndent=14, textColor=GREY)]
    return toc


# ------------------------------------------------------------------ diagrams
def _box(d, x, y, w, h, text, fill=LIGHT, stroke=BLUE, size=8.2, bold=False):
    d.add(RoundRect(x, y, w, h, 5, fillColor=fill, strokeColor=stroke, strokeWidth=1))
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        yy = y + h / 2 + (len(lines) - 1) * 5 - i * 10 - 3
        d.add(String(x + w / 2, yy, ln, textAnchor="middle", fontName="Helvetica-Bold" if bold else "Helvetica", fontSize=size, fillColor=NAVY))


def _arrow(d, x1, y1, x2, y2, colour=GREY):
    d.add(Line(x1, y1, x2, y2, strokeColor=colour, strokeWidth=1.2))
    import math
    a = math.atan2(y2 - y1, x2 - x1)
    for s in (+1, -1):
        d.add(Line(x2, y2, x2 - 6 * math.cos(a - s * 0.45), y2 - 6 * math.sin(a - s * 0.45), strokeColor=colour, strokeWidth=1.2))


def pipeline_diagram():
    d = Drawing(165 * mm, 112 * mm)
    W = 165 * mm
    bw, bh = 46 * mm, 15 * mm
    xs = [4 * mm, 59.5 * mm, 115 * mm]
    ys = [92 * mm, 66 * mm, 40 * mm, 14 * mm]
    _box(d, xs[0], ys[0], bw, bh, "Webcam\n(ThreadedCamera)", bold=True)
    _box(d, xs[1], ys[0], bw, bh, "Mirror + hand tracking\n(MediaPipe, 21 points)")
    _box(d, xs[2], ys[0], bw, bh, "Face lock (thread)\nis the admin here?")
    _arrow(d, xs[0] + bw, ys[0] + bh / 2, xs[1], ys[0] + bh / 2)
    _arrow(d, xs[1] + bw, ys[0] + bh / 2, xs[2], ys[0] + bh / 2)
    _box(d, xs[0], ys[1], bw, bh, "Pose recogniser\npalm/point/click/right/\nscroll/fist", size=7.6)
    _box(d, xs[1], ys[1], bw, bh, "Air gate\nhand raised? awake?")
    _box(d, xs[2], ys[1], bw, bh, "Hand ignored unless\nadmin face is present", fill=colors.HexColor("#fdf0e0"), stroke=AMBER)
    _arrow(d, xs[1] + bw / 2, ys[0], xs[0] + bw / 2, ys[1] + bh)
    _arrow(d, xs[2] + bw / 2, ys[0], xs[2] + bw / 2, ys[1] + bh, AMBER)
    _arrow(d, xs[0] + bw, ys[1] + bh / 2, xs[1], ys[1] + bh / 2)
    _box(d, xs[0], ys[2], bw, bh, "Controller\n(state machine)", bold=True)
    _arrow(d, xs[1] + bw / 2, ys[1], xs[0] + bw / 2 + 8 * mm, ys[2] + bh)
    _box(d, xs[1], ys[2], bw, bh, "Smoothing\nOne-Euro filter,\nrelative + acceleration", size=7.6)
    _arrow(d, xs[1], ys[2] + bh / 2, xs[0] + bw, ys[2] + bh / 2)
    _box(d, xs[0], ys[3], bw, bh, "Mouse (pynput)\nmove / click / scroll")
    _box(d, xs[1], ys[3], bw, bh, "Window mover\n(Win32 ctypes)")
    _box(d, xs[2], ys[3], bw, bh, "Preview window\n(own thread)")
    _arrow(d, xs[0] + bw / 2, ys[2], xs[0] + bw / 2, ys[3] + bh)
    _arrow(d, xs[0] + bw - 6 * mm, ys[2], xs[1] + 6 * mm, ys[3] + bh)
    d.add(String(W / 2, 2 * mm, "Everything on the left side of the loop runs once per camera frame (about 30 times a second).",
                 textAnchor="middle", fontName="Helvetica-Oblique", fontSize=7.6, fillColor=GREY))
    return d


def hand_glyph(up=(0, 0, 0, 0), thumb_out=False, pinch=False, fist=False, label="", w=34 * mm, h=44 * mm, hl=None):
    """A simple drawn hand. up = (index, middle, ring, pinky) raised?"""
    d = Drawing(w, h)
    s = w / 100.0
    skin, edge = colors.HexColor("#f2d7bd"), colors.HexColor("#8a6a4c")
    d.add(RoundRect(28 * s, 12 * s, 44 * s, 40 * s, 9 * s, fillColor=skin, strokeColor=edge, strokeWidth=1))
    for i, (x, top) in enumerate(((30, 112), (42.5, 120), (55, 117), (67, 106))):
        fh = (top - 40) * 0.85 if up[i] else 22
        if fist or not up[i]:
            fh = 20
        y0 = 48 * s
        d.add(RoundRect((x - 5.2) * s, y0, 10.4 * s, fh * s * 0.55 + 10 * s, 4 * s, fillColor=skin, strokeColor=edge, strokeWidth=1))
    if pinch:
        d.add(RoundRect(8 * s, 40 * s, 28 * s, 10 * s, 4 * s, fillColor=skin, strokeColor=edge, strokeWidth=1))
        d.add(Circle(32 * s, 66 * s, 5 * s, fillColor=None, strokeColor=GREEN, strokeWidth=1.6))
    elif thumb_out:
        d.add(RoundRect(6 * s, 30 * s, 30 * s, 10 * s, 4 * s, fillColor=skin, strokeColor=edge, strokeWidth=1))
    else:
        d.add(RoundRect(30 * s, 30 * s, 24 * s, 10 * s, 4 * s, fillColor=skin, strokeColor=edge, strokeWidth=1))
    d.add(String(w / 2, 2, label, textAnchor="middle", fontName="Helvetica-Bold", fontSize=7.6, fillColor=NAVY))
    return d


def pose_strip(items):
    """items: list of (kwargs-for-hand_glyph) -> a row of drawings."""
    cells = [[hand_glyph(**kw) for kw in items]]
    t = Table(cells, colWidths=[165 * mm / len(items)] * len(items))
    t.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    return [t, Spacer(1, 8)]


def landmark_diagram():
    d = Drawing(165 * mm, 78 * mm)
    s = 0.62 * 165 * mm / 100
    ox, oy = 52 * mm, 4 * mm
    pts = {0: (50, 5), 1: (36, 14), 2: (28, 26), 3: (23, 36), 4: (19, 45),
           5: (38, 46), 6: (36, 62), 7: (35, 72), 8: (34, 82),
           9: (50, 48), 10: (50, 66), 11: (50, 77), 12: (50, 88),
           13: (62, 46), 14: (64, 62), 15: (65, 72), 16: (66, 81),
           17: (73, 40), 18: (77, 53), 19: (79, 61), 20: (81, 69)}
    chains = [(0, 1, 2, 3, 4), (0, 5, 6, 7, 8), (9, 10, 11, 12), (13, 14, 15, 16), (0, 17, 18, 19, 20), (5, 9, 13, 17)]
    P_ = lambda i: (ox + pts[i][0] * s, oy + pts[i][1] * s * 0.75 * 1.05)
    for ch in chains:
        for a, b in zip(ch, ch[1:]):
            d.add(Line(*P_(a), *P_(b), strokeColor=LINE, strokeWidth=1.4))
    for i in pts:
        x, y = P_(i)
        knuckle = i in (5, 9, 13, 17)
        d.add(Circle(x, y, 2.6 if not knuckle else 3.4, fillColor=GREEN if knuckle else BLUE, strokeColor=colors.white, strokeWidth=0.5))
        d.add(String(x + 4, y - 2, str(i), fontName="Helvetica", fontSize=6.8, fillColor=NAVY))
    d.add(String(4 * mm, 70 * mm, "21 landmarks per hand", fontName="Helvetica-Bold", fontSize=9, fillColor=NAVY))
    d.add(String(4 * mm, 63 * mm, "0 = wrist", fontName="Helvetica", fontSize=8, fillColor=GREY))
    d.add(String(4 * mm, 57 * mm, "4, 8, 12, 16, 20 = fingertips", fontName="Helvetica", fontSize=8, fillColor=GREY))
    d.add(Circle(6 * mm, 50 * mm, 3.4, fillColor=GREEN, strokeColor=colors.white))
    d.add(String(10 * mm, 48.5 * mm, "5, 9, 13, 17 = knuckles; the cursor", fontName="Helvetica", fontSize=8, fillColor=GREY))
    d.add(String(10 * mm, 43.5 * mm, "follows the AVERAGE of these four", fontName="Helvetica", fontSize=8, fillColor=GREY))
    return d


def accel_curve(gmin=1.1, gmax=3.0, lo=0.04, hi=0.8):
    d = Drawing(150 * mm, 62 * mm)
    ox, oy, W, H = 14 * mm, 9 * mm, 128 * mm, 46 * mm
    d.add(Rect(ox, oy, W, H, fillColor=colors.white, strokeColor=LINE))
    pts = []
    n = 120
    for i in range(n + 1):
        v = 1.0 * i / n
        t = min(max((v - lo) / (hi - lo), 0.0), 1.0)
        ss = t * t * (3 - 2 * t)
        g = gmin + (gmax - gmin) * ss
        pts += [ox + W * v, oy + H * (g / 3.4)]
    d.add(PolyLine(pts, strokeColor=BLUE, strokeWidth=2))
    for gv in (1, 2, 3):
        y = oy + H * gv / 3.4
        d.add(Line(ox, y, ox + W, y, strokeColor=LINE, strokeWidth=0.4))
        d.add(String(ox - 3, y - 2, f"{gv}x", textAnchor="end", fontName="Helvetica", fontSize=7, fillColor=GREY))
    d.add(String(ox + W / 2, 1.5 * mm, "hand speed (camera widths per second)  ->  slow ... fast", textAnchor="middle",
                 fontName="Helvetica", fontSize=7.4, fillColor=GREY))
    d.add(String(ox + 3, oy + H + 2, "cursor gain (cursor speed / hand speed)", fontName="Helvetica", fontSize=7.4, fillColor=GREY))
    return d


def RoundRect(x, y, w, h, r, **kw):
    return Rect(x, y, w, h, rx=r, ry=r, **kw)
