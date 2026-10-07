"""
make_icons.py — 把网上的 SVG 图标烘成 Tk Canvas 图元坐标
=========================================================
为什么这么做：
  · 直接用 emoji 当图标：颜色不跟主题走、不能干净旋转、没装 emoji 字库就掉方框；
  · 手写「圆 + 放射线」那种：形状不像，用户一眼就看出来不是齿轮；
  · 运行时读 SVG / 依赖图标库：打包体积、网络、字体渲染都是坑。

所以：构建期从 CDN 取官方 SVG（Lucide，ISC 许可），把 path/circle 展平成折线，
      归一化到 -1..1，直接写进 src/pulses_swap.py 的 _ICON_PRIMS。
      运行时不联网、不依赖任何库，坐标是纯数据，能染色、能旋转。

用法：
    python packaging/make_icons.py            # 联网取最新并回写源码
    python packaging/make_icons.py --dry-run  # 只打印，不改文件
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from pathlib import Path

# 图标源：仓库内 packaging/icons/*.svg（用户指定），可再按需从 CDN 取。
#   filled=True  → 填充型图标（实心轮廓）：按 even-odd 把外轮廓和内部的孔
#                  合并成一个 polygon，Tk 填充时会自动挖洞（已实测）
#   filled=False → 描边型图标（Lucide/Feather 那种线稿）
# stroke：该图标在 20px 下用的描边宽度。三个图标必须分开定 ——
#   home 是细线稿（笔画 38/1024 ≈ 0.74px@20px），不描够 2px 会被 Tk 的
#        非抗锯齿栅格化成虚线段（就是「抠图没抠干净」那种割裂感）；
#   log  的横线与间隙都窄，描太粗会糊成一坨；
#   gear 是实心大块，描粗了中心孔就没了。
ICONS = {
    "home": {"file": "home.svg", "filled": True, "stroke": 2.0},
    "gear": {"file": "gear.svg", "filled": True, "stroke": 0.8},
    "log":  {"file": "log.svg",  "filled": True, "stroke": 1.1},
}
ICON_DIR = Path(__file__).resolve().parent / "icons"

CDN = "https://cdn.jsdelivr.net/npm/{path}"

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "pulses_swap.py"

DEFAULT_VIEWBOX = 24.0  # 没写 viewBox 时的兜底（Lucide 是 24x24）
SAMPLES_PER_CURVE = 8   # 曲线/圆弧展平密度（之后还会做抽稀）
SIMPLIFY_EPS = 0.028        # 描边型抽稀容差（归一化坐标，≈17px 下的 0.24px）
SIMPLIFY_EPS_FILLED = 0.045  # 填充型可以更狠：实心形状看不出这点偏差


def fetch(path: str) -> str:
    with urllib.request.urlopen(CDN.format(path=path), timeout=30) as resp:
        return resp.read().decode("utf-8")


def _dedupe(pts, eps=1e-6):
    out = []
    for pt in pts:
        if not out or abs(out[-1][0] - pt[0]) > eps or abs(out[-1][1] - pt[1]) > eps:
            out.append(pt)
    return out


def _rdp(pts, eps):
    """Douglas-Peucker 抽稀：弧线展平后点太密，抽完再写进源码。"""
    if len(pts) < 3:
        return pts
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    dx, dy = x2 - x1, y2 - y1
    norm = (dx * dx + dy * dy) ** 0.5
    worst, index = -1.0, 0
    for i in range(1, len(pts) - 1):
        px, py = pts[i]
        if norm < 1e-12:
            dist = ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
        else:
            dist = abs(dy * px - dx * py + x2 * y1 - y2 * x1) / norm
        if dist > worst:
            worst, index = dist, i
    if worst <= eps:
        return [pts[0], pts[-1]]
    left = _rdp(pts[:index + 1], eps)
    right = _rdp(pts[index:], eps)
    return left[:-1] + right


def flatten_path(d: str, samples: int = SAMPLES_PER_CURVE, eps: float = None):
    """把一条 path 展平成若干条折线（每条是一串 (x, y)）。"""
    from svg.path import parse_path

    polylines = []
    current = []
    for seg in parse_path(d):
        start = (seg.start.real, seg.start.imag)
        end = (seg.end.real, seg.end.imag)
        if not current:
            current.append(start)
        elif abs(current[-1][0] - start[0]) > 1e-6 or \
                abs(current[-1][1] - start[1]) > 1e-6:
            polylines.append(current)
            current = [start]
        # 直线段只留端点；曲线段按密度采样
        if type(seg).__name__ == "Line":
            current.append(end)
        else:
            for i in range(1, samples + 1):
                pt = seg.point(i / samples)
                current.append((pt.real, pt.imag))
    if current:
        polylines.append(current)
    cleaned = []
    for pts in polylines:
        pts = _dedupe(pts)
        if len(pts) >= 2:
            cleaned.append(_rdp(pts, SIMPLIFY_EPS if eps is None else eps))
    return cleaned


def _signed_area(poly):
    total = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def _point_in_poly(pt, poly):
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            if x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                inside = not inside
    return inside


def group_subpaths(subpaths):
    """把「外轮廓 + 内部的孔」合并成一个 polygon（Tk 用 even-odd 填充，会自动挖洞）。

    subpaths: [ [(x, y), ...], ... ]
    返回: [[外轮廓点..., 孔1点..., 孔2点...], ...]
    """
    items = []
    for pts in subpaths:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        items.append({"pts": pts, "area": abs(_signed_area(pts)),
                      "bbox": (min(xs), min(ys), max(xs), max(ys))})
    items.sort(key=lambda it: -it["area"])

    groups = []
    for item in items:
        if item.get("used"):
            continue
        group = list(item["pts"])
        item["used"] = True
        outer = item
        for other in items:
            if other.get("used") or other is outer:
                continue
            x1, y1, x2, y2 = other["bbox"]
            ox1, oy1, ox2, oy2 = outer["bbox"]
            if not (x1 >= ox1 and y1 >= oy1 and x2 <= ox2 and y2 <= oy2):
                continue
            if _point_in_poly(other["pts"][0], outer["pts"]):
                group.extend(other["pts"])
                other["used"] = True
        groups.append(group)
    return groups


def _viewbox(svg: str):
    """从 viewBox 里取宽高 —— 不同图标集差很多（Lucide 24、iconfont 1024），
    写死会让坐标整体放大几十倍。"""
    m = re.search(r'viewBox="\s*([-\d.]+)[ ,]+([-\d.]+)[ ,]+([-\d.]+)[ ,]+([-\d.]+)', svg)
    if m:
        w, h = float(m.group(3)), float(m.group(4))
        if w > 0 and h > 0:
            return w, h
    for attr in ("width", "height"):
        m = re.search(rf'{attr}="([\d.]+)"', svg)
        if m and float(m.group(1)) > 0:
            v = float(m.group(1))
            return v, v
    return DEFAULT_VIEWBOX, DEFAULT_VIEWBOX


def svg_to_prims(svg: str, filled: bool = False):
    """返回 Tk 图元描述：("line"/"solid", x1,y1,...) / ("oval", ...)（坐标已归一化）"""
    prims = []
    vb_w, vb_h = _viewbox(svg)
    half_x, half_y = vb_w / 2.0, vb_h / 2.0

    def norm_x(v):
        return round((v - half_x) / half_x, 4)

    def norm_y(v):
        return round((v - half_y) / half_y, 4)

    def norm(v):
        return norm_x(v)

    for d in re.findall(r'<path[^>]*\sd="([^"]+)"', svg):
        subpaths = flatten_path(
            d, eps=SIMPLIFY_EPS_FILLED if filled else None)
        if filled:
            groups = group_subpaths(subpaths)
        else:
            groups = subpaths
        for pts in groups:
            flat = []
            for x, y in pts:
                flat.extend((norm_x(x), norm_y(y)))
            if len(flat) >= 6:
                prims.append(("solid" if filled else "line",) + tuple(flat))

    for attrs in re.findall(r"<circle[^>]*/>", svg):
        cx = float(re.search(r'cx="([-\d.]+)"', attrs).group(1))
        cy = float(re.search(r'cy="([-\d.]+)"', attrs).group(1))
        r = float(re.search(r'r="([-\d.]+)"', attrs).group(1))
        prims.append(("oval", norm(cx - r), norm(cy - r),
                      norm(cx + r), norm(cy + r)))

    for attrs in re.findall(r"<rect[^>]*/>", svg):
        x = float(re.search(r'x="([-\d.]+)"', attrs).group(1))
        y = float(re.search(r'y="([-\d.]+)"', attrs).group(1))
        w = float(re.search(r'width="([-\d.]+)"', attrs).group(1))
        h = float(re.search(r'height="([-\d.]+)"', attrs).group(1))
        prims.append(("line", norm(x), norm(y), norm(x + w), norm(y),
                      norm(x + w), norm(y + h), norm(x), norm(y + h),
                      norm(x), norm(y)))
    return prims


def render_stroke_block(table: dict) -> str:
    lines = ["# 每个图标在 20px 下的描边宽度（见 make_icons.py 的选型注释）",
             "_ICON_STROKE = {"]
    for key, cfg in ICONS.items():
        lines.append(f'    "{key}": {cfg.get("stroke", 1.0)},')
    lines.append("}")
    return "\n".join(lines)


def render_block(table: dict) -> str:
    lines = ["_ICON_PRIMS = {"]
    for key, prims in table.items():
        lines.append(f'    "{key}": (')
        for prim in prims:
            body = ", ".join(f"{v}" for v in prim[1:])
            lines.append(f'        ("{prim[0]}", {body}),')
        lines.append("    ),")
    lines.append("}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--offline", action="store_true",
                    help="用 /tmp/icons 里已下载的 svg")
    args = ap.parse_args()

    table = {}
    for local, cfg in ICONS.items():
        path = ICON_DIR / cfg["file"]
        if not path.is_file():
            print(f"缺少图标文件: {path}", file=sys.stderr)
            return 1
        prims = svg_to_prims(path.read_text(encoding="utf-8"),
                             filled=cfg.get("filled", False))
        table[local] = prims
        pts = sum(len(p) - 1 for p in prims)
        kind = "填充" if cfg.get("filled") else "描边"
        print(f"  {local:6s} <- icons/{cfg['file']:10s} [{kind}] "
              f"{len(prims):2d} 图元 / {pts} 点")

    block = render_block(table) + "\n\n" + render_stroke_block(table)
    if args.dry_run:
        print(block)
        return 0

    src = SRC.read_text(encoding="utf-8")
    pattern = re.compile(
        r"_ICON_PRIMS = \{.*?\n\}\n(?:\n*# .*\n_ICON_STROKE = \{.*?\n\})?\n",
        re.S)
    if not pattern.search(src):
        print("源码里找不到 _ICON_PRIMS 块", file=sys.stderr)
        return 1
    SRC.write_text(pattern.sub(block + "\n", src, count=1), encoding="utf-8")
    print(f"已写回 {SRC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
