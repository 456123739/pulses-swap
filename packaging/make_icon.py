"""生成应用图标 —— 与宣传片同一套设计语言：水墨淡色底 + 青绿脉冲环。

用法: python3 packaging/make_icon.py

输出（三端打包都用这几个文件）：
    packaging/icon.ico   Windows：exe / 安装器 / 快捷方式
    packaging/icon.png   窗口图标、README、商店展示
    packaging/icon.icns  macOS：.app 的 Dock 图标

**换成自己的 logo**：把图丢到 packaging/logo.png（正方形、透明底最佳），
再跑一次本脚本 —— 会用它替换掉下面这套程序化绘制的图标，三个格式一起重出。
"""
from PIL import Image, ImageDraw, ImageFont
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


LOGO = pathlib.Path(__file__).parent / "logo.png"


def build_from_logo(size):
    """用户给的 logo：等比放进正方形画布，套同一套圆角遮罩。"""
    S = 1024
    src = Image.open(LOGO).convert("RGBA")
    # 等比缩放（contain），不要拉伸变形
    scale = min(S / src.width, S / src.height)
    fitted = src.resize((max(1, int(src.width * scale)),
                         max(1, int(src.height * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    canvas.paste(fitted, ((S - fitted.width) // 2, (S - fitted.height) // 2),
                 fitted)
    # logo 自带的透明边缘已经很干净，这里只在四周补一点留白
    pad = int(S * 0.06)
    inner = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    inner.paste(canvas.resize((S - 2 * pad, S - 2 * pad), Image.LANCZOS),
                (pad, pad))
    out = inner.resize((size, size), Image.LANCZOS)
    out.putalpha(rounded_mask(size, int(size * 0.22)))
    return out


# ==================== SW 字母标 ====================
# 高级感靠三件事：几何无衬线的字母、克制的双色、干净的圆角底。
# 字母用 URW Gothic Demi（Avant Garde 一脉的几何体），系统没有就退回
# DejaVu Sans Bold —— 反正打包机上只要有其一即可。
SW_FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/urw-base35/URWGothic-Demi.otf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/seguisb.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)

TILE_TOP = (46, 69, 71)        # #2E4547
TILE_BOTTOM = (29, 46, 48)     # #1D2E30
INK_ON_TILE = (255, 255, 255)
TEAL = (91, 168, 154)          # #5BA89A


def _sw_font():
    for path in SW_FONT_CANDIDATES:
        if pathlib.Path(path).exists():
            return path
    return None


def _tile(size):
    """深墨底 + 极轻的上下渐变，圆角 22%。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for y in range(size):
        f = y / max(1, size - 1)
        c = tuple(int(TILE_TOP[i] + (TILE_BOTTOM[i] - TILE_TOP[i]) * f)
                  for i in range(3))
        d.line([(0, y), (size, y)], fill=c + (255,))
    img.putalpha(rounded_mask(size, int(size * 0.22)))
    return img


def _monogram(size, width_ratio=0.54, tracking=0.12,
              colors=(INK_ON_TILE, TEAL)):
    """SW 连排：按墨迹框居中，tracking 是相对 S 宽度的字距。

    字距必须留够 —— S 的收笔和 W 的左斜线贴在一起时，小尺寸会糊成一团。
    """
    path = _sw_font()
    if path is None:                      # 没有可用字体就退回纯几何方块，不至于崩
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        return img
    probe = ImageFont.truetype(path, 400)
    tmp = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    s_box = tmp.textbbox((0, 0), "S", font=probe)
    w_box = tmp.textbbox((0, 0), "W", font=probe)
    base_w = (s_box[2] - s_box[0]) + (w_box[2] - w_box[0])
    fs = max(8, int(400 * (size * width_ratio) / base_w))

    font = ImageFont.truetype(path, fs)
    s_box = tmp.textbbox((0, 0), "S", font=font)
    w_box = tmp.textbbox((0, 0), "W", font=font)
    s_w, s_h = s_box[2] - s_box[0], s_box[3] - s_box[1]
    w_w, w_h = w_box[2] - w_box[0], w_box[3] - w_box[1]
    gap = int(s_w * tracking)
    group_w = s_w + gap + w_w
    group_h = max(s_h, w_h)

    # W 的右斜线在视觉上更"重"，整体往左挪 1.5% 做光学居中
    x0 = (size - group_w) / 2 - size * 0.008
    y0 = (size - group_h) / 2

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((x0 - s_box[0], y0 - s_box[1]), "S", font=font,
           fill=colors[0] + (255,))
    d.text((x0 + s_w + gap - w_box[0], y0 - w_box[1]), "W", font=font,
           fill=colors[1] + (255,))
    return img


def build_sw(size):
    # 小尺寸要"光学加粗"：16/32px 下同样的占比会显得又小又细，
    # 所以 ≤64px 时把字母放大一档，任务栏里才立得住。
    ratio = 0.62 if size <= 64 else 0.56
    S = 1024
    img = _tile(S)
    img.alpha_composite(_monogram(S, width_ratio=ratio))
    return img.resize((size, size), Image.LANCZOS)


def build(size):
    if LOGO.exists():
        return build_from_logo(size)
    return build_sw(size)


here = pathlib.Path(__file__).parent
sizes = [16, 24, 32, 48, 64, 128, 256]
frames = [build(s) for s in sizes]
frames[-1].save(here / "icon.ico", format="ICO",
                sizes=[(s, s) for s in sizes], append_images=frames[:-1])
build(512).save(here / "icon.png")

# macOS 的 .app 只认 .icns（Pillow 从 9.x 起能直接写，内部会生成 16~1024 各档）
try:
    build(1024).save(here / "icon.icns", format="ICNS")
    print("icon.ico / icon.png / icon.icns ok  ->", here,
      "（来源: logo.png）" if LOGO.exists() else "（程序化绘制）")
except Exception as exc:                      # 老版本 Pillow 没有 ICNS 写入
    print(f"icon.ico / icon.png ok  -> {here}（icon.icns 生成失败: {exc}）")
