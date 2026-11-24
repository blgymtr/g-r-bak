"""Program simgesini (varliklar/gor-bak.ico) çizer."""
import os

from PIL import Image, ImageDraw

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CIKTI = os.path.join(KOK, "varliklar", "gor-bak.ico")


def ciz(boyut: int) -> Image.Image:
    o = 4  # yüksek çözünürlükte çiz, sonra küçült
    b = boyut * o
    im = Image.new("RGBA", (b, b), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, b - 1, b - 1), radius=int(b * 0.2), fill=(22, 34, 48, 255))
    # röntgen filmi: açık gri dikdörtgen içinde kaburga çizgileri
    x0, y0, x1, y1 = int(b * 0.16), int(b * 0.14), int(b * 0.66), int(b * 0.70)
    d.rounded_rectangle((x0, y0, x1, y1), radius=int(b * 0.05), fill=(48, 66, 86, 255))
    cx = (x0 + x1) // 2
    d.line((cx, y0 + b * 0.06, cx, y1 - b * 0.06), fill=(210, 222, 235, 255), width=max(2, int(b * 0.035)))
    for i in range(4):
        y = y0 + b * (0.12 + i * 0.105)
        g = b * (0.16 - i * 0.012)
        d.arc((cx - g, y - b * 0.05, cx, y + b * 0.09), 180, 300, fill=(210, 222, 235, 255), width=max(2, int(b * 0.03)))
        d.arc((cx, y - b * 0.05, cx + g, y + b * 0.09), 240, 360, fill=(210, 222, 235, 255), width=max(2, int(b * 0.03)))
    # büyüteç
    r = b * 0.2
    mx, my = b * 0.62, b * 0.60
    d.ellipse((mx - r, my - r, mx + r, my + r), outline=(111, 182, 255, 255), width=max(3, int(b * 0.06)))
    d.line((mx + r * 0.72, my + r * 0.72, b * 0.90, b * 0.88), fill=(111, 182, 255, 255), width=max(4, int(b * 0.09)))
    return im.resize((boyut, boyut), Image.LANCZOS)


if __name__ == "__main__":
    os.makedirs(os.path.dirname(CIKTI), exist_ok=True)
    buyuk = ciz(256)
    buyuk.save(CIKTI, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    buyuk.save(os.path.join(KOK, "varliklar", "gor-bak.png"))
    print(CIKTI)
