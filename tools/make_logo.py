"""Krijon logon e aplikacionit: assets/logo.png, assets/logo_64.png, assets/logo.ico.

Përdorim:  python tools/make_logo.py   (kërkon Pillow: pip install pillow)
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "assets"
S = 2048  # vizatojmë të madh dhe e zvogëlojmë, për skaje të lëmuara

TOP_LEFT = (255, 94, 98)     # e kuqe-portokalli
BOTTOM_RIGHT = (123, 47, 247)  # vjollcë
ACCENT = (233, 69, 96)
WHITE = (255, 255, 255, 255)


def gradient(size: int) -> Image.Image:
    small = Image.new("RGB", (256, 256))
    px = small.load()
    for y in range(256):
        for x in range(256):
            t = (x + y) / 510
            px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(TOP_LEFT, BOTTOM_RIGHT))
    return small.resize((size, size), Image.BICUBIC)


def u(v: float) -> int:
    return round(v * S)


def note_head(layer: Image.Image, cx: float, cy: float) -> None:
    head = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(head).ellipse([u(cx - 0.105), u(cy - 0.075), u(cx + 0.105), u(cy + 0.075)], fill=WHITE)
    head = head.rotate(25, resample=Image.BICUBIC, center=(u(cx), u(cy)))
    layer.alpha_composite(head)


def make() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # Sfondi: katror me qoshe të rrumbullakëta, me gradient
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=u(0.23), fill=255)
    img.paste(gradient(S), (0, 0), mask)

    # Nota muzikore e dyfishtë (♫)
    notes = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(notes)
    h1, h2 = (0.30, 0.66), (0.60, 0.58)
    stem_w = 0.045
    s1x = h1[0] + 0.088
    s2x = h2[0] + 0.088
    top1, top2 = 0.24, 0.16
    d.rectangle([u(s1x - stem_w), u(top1), u(s1x), u(h1[1] - 0.02)], fill=WHITE)
    d.rectangle([u(s2x - stem_w), u(top2), u(s2x), u(h2[1] - 0.02)], fill=WHITE)
    beam = 0.095
    d.polygon(
        [(u(s1x - stem_w), u(top1)), (u(s2x), u(top2)), (u(s2x), u(top2 + beam)), (u(s1x - stem_w), u(top1 + beam))],
        fill=WHITE,
    )
    note_head(notes, *h1)
    note_head(notes, *h2)

    # Hapësirë rreth distinktivit që të duket i ndarë nga nota
    cut = Image.new("L", (S, S), 255)
    bx, by, br = 0.755, 0.755, 0.165
    ImageDraw.Draw(cut).ellipse([u(bx - br - 0.035), u(by - br - 0.035), u(bx + br + 0.035), u(by + br + 0.035)], fill=0)
    notes.putalpha(Image.composite(notes.getchannel("A"), Image.new("L", (S, S), 0), cut))
    img.alpha_composite(notes)

    # Distinktivi i shkarkimit: rreth i bardhë me shigjetë poshtë
    d = ImageDraw.Draw(img)
    d.ellipse([u(bx - br), u(by - br), u(bx + br), u(by + br)], fill=WHITE)
    shaft_w = 0.042
    d.rectangle([u(bx - shaft_w / 2), u(by - 0.095), u(bx + shaft_w / 2), u(by + 0.02)], fill=ACCENT)
    d.polygon([(u(bx - 0.075), u(by + 0.0)), (u(bx + 0.075), u(by + 0.0)), (u(bx), u(by + 0.08))], fill=ACCENT)
    d.rectangle([u(bx - 0.085), u(by + 0.098), u(bx + 0.085), u(by + 0.122)], fill=ACCENT)
    return img


def checkbox(checked: bool, size: int = 48) -> Image.Image:
    """Ikona e checkbox-it për UI (vizatohet 4x më e madhe për skaje të lëmuara)."""
    k = size * 4
    img = Image.new("RGBA", (k, k), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    box = [k * 0.08, k * 0.08, k * 0.92, k * 0.92]
    if checked:
        d.rounded_rectangle(box, radius=k * 0.2, fill=ACCENT)
        w = round(k * 0.11)
        d.line([(k * 0.27, k * 0.52), (k * 0.43, k * 0.68), (k * 0.74, k * 0.34)], fill=WHITE, width=w, joint="curve")
    else:
        d.rounded_rectangle(box, radius=k * 0.2, fill=(38, 38, 54), outline=(82, 82, 108), width=round(k * 0.06))
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    checkbox(True).save(OUT / "check_on.png")
    checkbox(False).save(OUT / "check_off.png")
    big = make()
    big.resize((512, 512), Image.LANCZOS).save(OUT / "logo.png")
    big.resize((64, 64), Image.LANCZOS).save(OUT / "logo_64.png")
    big.resize((256, 256), Image.LANCZOS).save(
        OUT / "logo.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    )
    print(f"Logo u krijua në {OUT}")


if __name__ == "__main__":
    main()
