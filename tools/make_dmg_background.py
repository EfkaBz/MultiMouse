"""Render the background of the macOS disk image (installer/mac/dmg-background.tiff).

    python tools/make_dmg_background.py

The window is 640 x 400 points: MultiMouse.app sits at (160, 190), Applications at (480, 190)
(build.py places the icons at the same spots).
"""
import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "installer", "mac")
W, H = 640, 400
FONTS = ["/System/Library/Fonts/SFNS.ttf", "/System/Library/Fonts/HelveticaNeue.ttc"]


def font(size, weight=None):
    for path in FONTS:
        try:
            f = ImageFont.truetype(path, size)
            if weight:
                try:
                    f.set_variation_by_name(weight)
                except Exception:
                    pass
            return f
        except OSError:
            continue
    return ImageFont.load_default()


def render(k):
    img = Image.new("RGB", (W * k, H * k), (0xF5, 0xF5, 0xF7))
    d = ImageDraw.Draw(img)

    def text(y, s, size, color, weight=None):
        f = font(size * k, weight)
        w = d.textlength(s, font=f)
        d.text(((W * k - w) / 2, y * k), s, font=f, fill=color)

    text(34, "Installer MultiMouse", 22, (0x1D, 0x1D, 0x1F), "Semibold")
    text(66, "Glissez MultiMouse dans le dossier Applications", 13, (0x6E, 0x6E, 0x73))

    # arrow between the two icons
    y = 190 * k
    x0, x1 = 238 * k, 402 * k
    blue = (0x00, 0x7A, 0xFF)
    d.line((x0, y, x1 - 10 * k, y), fill=blue, width=3 * k)
    d.polygon([(x1, y), (x1 - 14 * k, y - 8 * k), (x1 - 14 * k, y + 8 * k)], fill=blue)

    text(318, "Premier lancement : clic droit sur MultiMouse › Ouvrir.", 12, (0x6E, 0x6E, 0x73))
    text(338, "Autorisez-le ensuite dans Réglages Système › Confidentialité et sécurité :", 12, (0x6E, 0x6E, 0x73))
    text(356, "Accessibilité et Surveillance de l'entrée.", 12, (0x6E, 0x6E, 0x73))
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    one, two = os.path.join(OUT, "bg.png"), os.path.join(OUT, "bg@2x.png")
    render(1).save(one, dpi=(72, 72))
    render(2).save(two, dpi=(144, 144))
    # one TIFF with both resolutions: sharp on Retina screens
    subprocess.check_call(["tiffutil", "-cathidpicheck", one, two, "-out", os.path.join(OUT, "dmg-background.tiff")])
    os.remove(one)
    os.remove(two)
    print("background written to", OUT)


if __name__ == "__main__":
    main()
