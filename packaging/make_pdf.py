"""Builds the Hexra guide PDF.   usage: python make_pdf.py <output.pdf>"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, NextPageTemplate, PageBreak, Paragraph, Spacer

from content_a import part1
from content_b import part2
from content_c import part3
from pdf_lib import B, BODY, Doc, H1, H2, P, make_toc, table

REQUESTS = [
    ("Set-up", "read the shared conversation/folder and complete the setup; 'tell me what to run'; 'it tracks both hands but does not move the cursor'"),
    ("Ideas", "face and mood; an app for deaf people (ASL, not Braille); full sentences; text first; use existing datasets; start with the alphabet"),
    ("ASL project", "how much space; download; 'I want to test anyway'; use the existing data and my finger mapping; 'it is not tracking my fingers'; 'match my hand'; "
                    "slower calibration; 'is this for training?'; 'does a user need to train again?'"),
    ("New project", "'leave this separate, create a new project that controls my screen'; fist moves the window under the cursor"),
    ("Controls", "'how to test'; 'it is not moving the cursor'; 'what are the controls' (three times); pointing and right click overlap; open palm moves the cursor; "
                 "keep the earlier options; right click = two fingers; scroll did not work; fist moves the window under the cursor"),
    ("Smoothness", "smooth movement for an unsteady hand; only react when the hand is in the air; faster response and capture speed"),
    ("Scroll / right click", "flip them: two fingers scroll in four directions; three fingers right click"),
    ("Drag", "'I pinched and moved the tab, then it stopped in the middle'; 'it is lagging, I moved slowly'; 'it shows 15 to 31 ms'"),
    ("Cursors", "'if I cannot add individual cursors, do not do it, but check'"),
    ("Cameras", "two cameras; stereo 3D; scan and use as many as connected; no printer; automatic; 'why did only one stay on'; 'remove it for now'"),
    ("Speed", "'respond fast just like a mouse'; 'will a USB-C camera reduce delay'; 'how can I make it faster'"),
    ("Screens", "'what if I have an extended screen'; make it access it; 'I should be able to control that screen as well'"),
    ("Precision", "'the fist released in the middle and the cursor moved normally'; 'make precision better, I want it perfect'"),
    ("Admin face", "'it should match only the admin face'; 'how to run'; 'failed, the version number is wrong'; 'it works great'"),
    ("Active area", "'why does it work only inside the yellow box'; apply the edge margin change; the blue line / ball problem"),
    ("Bugs", "'when I rotate my hand it counts as right click'; 'scrolling fingers curled and acted as a fist'"),
    ("Window commands", "'best controls to close, minimise, enlarge, shrink and split without overlap'; 'fist already moves, won't it be misunderstood, and the controls seem small'"),
    ("This document", "'a PDF on each and every part: how I changed it, where I started, every small detail, how to use it' plus 'an exe installation file with the whole setup and no additional file'"),
]


def cover():
    t = ParagraphStyle("ct", fontName="Helvetica-Bold", fontSize=38, leading=44, textColor=colors.white)
    st = ParagraphStyle("cs", fontName="Helvetica", fontSize=16, leading=22, textColor=colors.HexColor("#b7c6e6"))
    sm = ParagraphStyle("cm", fontName="Helvetica", fontSize=10.5, leading=15, textColor=colors.HexColor("#b7c6e6"))
    logo = Image(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "logo.png"), width=38 * mm, height=38 * mm)
    logo.hAlign = "LEFT"
    return [Spacer(1, 40 * mm), logo, Spacer(1, 10 * mm), Paragraph("Hexra", t), Spacer(1, 6 * mm),
            Paragraph("Your hands, in control.", st), Spacer(1, 14 * mm),
            Paragraph("User guide, how it works inside, and the full story of how it was built: where it started, every change, and why.", sm),
            Spacer(1, 60 * mm), Paragraph("Version 1.1.1 &nbsp;|&nbsp; Windows 10/11 &nbsp;|&nbsp; Python 3.10 &nbsp;|&nbsp; 111 automated tests", sm),
            NextPageTemplate("main"), PageBreak()]


def main(out):
    doc = Doc(out, "Hexra - guide and project history")
    toc = make_toc()
    story = cover()
    story += [Paragraph("Contents", ParagraphStyle("ch", parent=H1)), toc, PageBreak()]
    story += part1() + part2() + part3()
    story += [PageBreak(), P("Appendix: everything you asked for, in order", H1),
              P("Condensed from your messages. Each line became one or more of the changes in section 12.")]
    story += table([["Topic", "Your requests"]] + [[a, b] for a, b in REQUESTS], [32, 133])
    story += [P("Appendix: quick reference card", H1)]
    story += table([["Hand shape", "Action"], ["Open palm", "move cursor (hold 1 s in the air to wake)"], ["One finger", "pause cursor"],
                    ["Pinch thumb + index", "click; hold and move = drag"], ["Three fingers (index, middle, ring)", "right click"],
                    ["Two fingers (index, middle) and move", "scroll up/down/left/right"], ["Fist", "grab the window under the cursor and move it"],
                    ["F8 / e", "engage or pause"], ["F9 / q", "quit"]], [80, 85])
    doc.multiBuild(story)
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "Hexra-Guide.pdf")
