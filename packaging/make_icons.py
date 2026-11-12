"""Build the app's logo files from assets/logo-hand-cursor-master.png, preserving its transparency.

    python packaging/make_icons.py

Writes the README/guide logo, transparent logo, UI logo and a Windows icon with seven sizes.
"""
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER = os.path.join(ROOT, "assets", "logo-hand-cursor-master.png")
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main():
    master = Image.open(MASTER).convert("RGBA")
    master.resize((1024, 1024), Image.LANCZOS).save(os.path.join(ROOT, "assets", "logo.png"), optimize=True)
    cut = master.resize((512, 512), Image.LANCZOS)
    cut.resize((256, 256), Image.LANCZOS).save(os.path.join(ROOT, "packaging", "app.ico"), sizes=SIZES)
    cut.save(os.path.join(ROOT, "assets", "logo-transparent.png"), optimize=True)
    cut.save(os.path.join(ROOT, "src", "hexra", "ui", "logo.png"), optimize=True)
    print("wrote assets/logo.png, assets/logo-transparent.png, src/hexra/ui/logo.png, packaging/app.ico")


if __name__ == "__main__":
    main()
