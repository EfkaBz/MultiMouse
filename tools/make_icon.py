"""Render the MultiMouse icon (same design as the logo in the UI) into multimouse/assets.

    python tools/make_icon.py
"""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "multimouse", "assets")
S = 1024  # supersampled canvas, downscaled for every size


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def render():
    top, bottom = (0x5A, 0xC8, 0xFA), (0x58, 0x56, 0xD6)
    grad = Image.new("RGB", (S, S))
    px = grad.load()
    for y in range(S):
        for x in range(S):
            px[x, y] = lerp(top, bottom, (x + y) / (2 * S - 2))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 0.225), fill=255)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)

    u = S / 40  # the UI logo is drawn on a 40x40 grid
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((6 * u, 10 * u, 19 * u, 19 * u), radius=2 * u, fill=(255, 255, 255, 242))
    left = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(left).rounded_rectangle((21 * u, 10 * u, 34 * u, 19 * u), radius=2 * u, fill=(255, 255, 255, 153))
    img = Image.alpha_composite(img, left)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((15 * u, 22 * u, 25 * u, 35 * u), radius=5 * u, fill=(255, 255, 255, 255))
    d.line((20 * u, 22.5 * u, 20 * u, 27 * u), fill=(0x58, 0x56, 0xD6, 255), width=int(1.4 * u))
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    img = render()
    img.resize((512, 512), Image.LANCZOS).save(os.path.join(OUT, "icon.png"))
    img.resize((256, 256), Image.LANCZOS).save(
        os.path.join(OUT, "icon.ico"), sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
    # Installer header image (Inno Setup wants an opaque BMP)
    for name, size in (("wizard-small.bmp", 110), ("wizard-small-55.bmp", 55)):
        bg = Image.new("RGB", (size, size), (255, 255, 255))
        icon = img.resize((int(size * 0.86),) * 2, Image.LANCZOS)
        off = (size - icon.width) // 2
        bg.paste(icon, (off, off), icon)
        bg.save(os.path.join(OUT, name))
    print("icons written to", OUT)


if __name__ == "__main__":
    main()
