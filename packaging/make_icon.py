"""生成应用图标 —— 与宣传片同一套设计语言：水墨淡色底 + 青绿脉冲环。

用法: python3 packaging/make_icon.py
输出: packaging/icon.ico (多尺寸) 与 packaging/icon.png (512, 供 README/商店用)
"""
from PIL import Image, ImageDraw
import math, pathlib

ACCENT = (91, 168, 154)        # #5BA89A
ACCENT_DK = (61, 122, 110)     # #3D7A6E
ACCENT_LT = (127, 212, 193)    # #7FD4C1
INK = (44, 62, 63)             # #2C3E3F
SIZE = 512


def rounded_mask(size, radius):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def build(size):
    S = 1024  # 先大后缩，边缘更干净
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 底：淡色卡面，带一点自上而下的冷暖过渡
    for y in range(S):
        f = y / S
        r = int(247 + (237 - 247) * f)
        g = int(250 + (243 - 250) * f)
        b = int(251 + (245 - 251) * f)
        d.line([(0, y), (S, y)], fill=(r, g, b, 255))

    # 三道同心脉冲环（"Pulses"）
    cx = cy = S / 2
    for i, (rad, alpha, w) in enumerate([(300, 60, 16), (228, 110, 18), (156, 175, 20)]):
        d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad],
                  outline=ACCENT + (alpha,), width=w)

    # 中心：一个实心环 + 一道斜向高光，暗示"替换/同步"
    d.ellipse([cx - 96, cy - 96, cx + 96, cy + 96], fill=ACCENT + (255,))
    d.ellipse([cx - 52, cy - 52, cx + 52, cy + 52], fill=(255, 255, 255, 255))
    d.ellipse([cx - 26, cy - 26, cx + 26, cy + 26], fill=ACCENT_DK + (255,))

    # 顶部镜面高光
    hl = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hl)
    hd.ellipse([-S * 0.30, -S * 0.92, S * 1.30, S * 0.40], fill=(255, 255, 255, 46))
    img = Image.alpha_composite(img, hl)

    # 外描边
    d2 = ImageDraw.Draw(img)
    d2.rounded_rectangle([1, 1, S - 2, S - 2], radius=int(S * 0.22),
                         outline=(255, 255, 255, 200), width=3)
    d2.rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.22),
                         outline=ACCENT_DK + (90,), width=5)

    img = img.resize((size, size), Image.LANCZOS)
    img.putalpha(rounded_mask(size, int(size * 0.22)))
    return img


here = pathlib.Path(__file__).parent
sizes = [16, 24, 32, 48, 64, 128, 256]
frames = [build(s) for s in sizes]
frames[-1].save(here / "icon.ico", format="ICO",
                sizes=[(s, s) for s in sizes], append_images=frames[:-1])
build(512).save(here / "icon.png")
print("icon.ico /", "icon.png ok  ->", here)
