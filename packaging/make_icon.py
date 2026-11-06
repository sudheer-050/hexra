"""Draws app.ico (a white hand with a green cursor ring on a dark tile)."""
from PIL import Image, ImageDraw

S = 256
im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(im)
d.rounded_rectangle((8, 8, S - 8, S - 8), 48, fill=(24, 40, 72, 255))
white = (240, 240, 240, 255)
d.rounded_rectangle((78, 120, 178, 214), 30, fill=white)
for x, top in ((82, 52), (110, 38), (138, 46), (166, 70)):
    d.rounded_rectangle((x - 11, top, x + 11, 150), 11, fill=white)
d.rounded_rectangle((44, 120, 96, 146), 13, fill=white)
d.ellipse((150, 150, 206, 206), outline=(60, 220, 120, 255), width=10)
im.save("app.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
