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

# 图标源：都走 jsdelivr 上的官方包（Lucide / Feather，均 ISC，同一设计血统）
# 选型记录（放大 8 倍 + 真实 17px 都看过）：
#   lucide/settings  → 花瓣状、feather/settings 没中心孔 → 都像花
#   lucide/cog       → 轮辐，又变太阳
#   tabler/settings  → 外面套个方框，17px 下太碎
#   heroicons/cog-6-tooth → 直齿 + 中心孔，放大缩小都是标准齿轮 ✓
SOURCES = {
    "home": ("lucide-static@latest/icons/house.svg", "house"),
    "gear": ("heroicons@2.1.5/24/outline/cog-6-tooth.svg", "hero_cog"),
    "log":  ("lucide-static@latest/icons/scroll-text.svg", "scroll-text"),
}
CDN = "https://cdn.jsdelivr.net/npm/{path}"

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "pulses_swap.py"

VIEWBOX = 24.0          # Lucide 都是 24x24
SAMPLES_PER_CURVE = 8   # 曲线/圆弧展平密度（之后还会做抽稀）
SIMPLIFY_EPS = 0.028    # 抽稀容差（归一化坐标，≈17px 下的 0.24px）


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


def flatten_path(d: str, samples: int = SAMPLES_PER_CURVE):
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
            cleaned.append(_rdp(pts, SIMPLIFY_EPS))
    return cleaned


def svg_to_prims(svg: str):
    """返回 Tk 图元描述：("line", x1,y1,x2,y2...) / ("oval", ...)（坐标已归一化）"""
    prims = []
    half = VIEWBOX / 2.0

    def norm(v):
        return round((v - half) / half, 4)

    for d in re.findall(r'<path[^>]*\sd="([^"]+)"', svg):
        for pts in flatten_path(d):
            flat = []
            for x, y in pts:
                flat.extend((norm(x), norm(y)))
            if len(flat) >= 4:
                prims.append(("line",) + tuple(flat))

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
    for local, (path, cache_name) in SOURCES.items():
        try:
            svg = (Path("/tmp/icons") / f"{cache_name}.svg").read_text(
                encoding="utf-8") if args.offline else fetch(path)
        except Exception as exc:  # noqa: BLE001
            print(f"取 {path} 失败: {exc}", file=sys.stderr)
            return 1
        prims = svg_to_prims(svg)
        table[local] = prims
        pts = sum(len(p) - 1 for p in prims)
        print(f"  {local:6s} <- {path:52s} {len(prims):2d} 图元 / {pts} 点")

    block = render_block(table)
    if args.dry_run:
        print(block)
        return 0

    src = SRC.read_text(encoding="utf-8")
    pattern = re.compile(r"_ICON_PRIMS = \{.*?\n\}\n", re.S)
    if not pattern.search(src):
        print("源码里找不到 _ICON_PRIMS 块", file=sys.stderr)
        return 1
    SRC.write_text(pattern.sub(block + "\n", src, count=1), encoding="utf-8")
    print(f"已写回 {SRC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
