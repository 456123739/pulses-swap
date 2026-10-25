"""主窗口出现 / 关闭动画的几何计算。

Tk 不能像 WPF 那样给整个窗口套 RenderTransform，所以这里用
「窗口位置 + alpha」做一个等价的轻量弹出：起始时窗口下移、透明，
然后快速回到最终位置。尺寸插值保留给调用方，但主窗口动画刻意不改
尺寸——Tk 每次改 geometry 尺寸都会重排整棵控件树，大界面上会卡。
纯函数放在这里，方便单测。
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional


_GEOMETRY_RE = re.compile(r"^(\d+)x(\d+)([+-]\d+)([+-]\d+)$")


@dataclass(frozen=True)
class WindowRect:
    """Tk geometry 的矩形：左上角 + 客户区尺寸。"""

    x: int
    y: int
    width: int
    height: int

    def geometry(self) -> str:
        # 多显示器时 x/y 可能为负；不能拼成 "+-12"。
        x = f"+{self.x}" if self.x >= 0 else str(self.x)
        y = f"+{self.y}" if self.y >= 0 else str(self.y)
        return f"{self.width}x{self.height}{x}{y}"


def parse_geometry(value) -> Optional[WindowRect]:
    """解析 ``1280x900+320+50``；格式不对返回 None，不抛异常。"""
    match = _GEOMETRY_RE.match(str(value or "").strip())
    if not match:
        return None
    width, height, x, y = (int(part) for part in match.groups())
    return WindowRect(x=x, y=y, width=width, height=height)


def pop_rect(final: WindowRect, scale: float = 0.966,
             offset_y: int = 26, min_width: int = 1,
             min_height: int = 1) -> WindowRect:
    """最终矩形 → 入场/退场的起始矩形（以中心为锚点，整体下移）。"""
    scale = min(1.0, max(0.5, float(scale)))
    width = min(final.width, max(int(min_width), round(final.width * scale)))
    height = min(final.height, max(int(min_height), round(final.height * scale)))
    x = final.x + (final.width - width) // 2
    y = final.y + (final.height - height) // 2 + int(offset_y)
    return WindowRect(x, y, width, height)


def lerp_rect(start: WindowRect, end: WindowRect, progress: float) -> WindowRect:
    """按进度插值；终端严格落在 end，避免浮点误差留下 1px。"""
    t = 0.0 if progress <= 0 else (1.0 if progress >= 1 else float(progress))
    if t >= 1.0:
        return end
    if t <= 0.0:
        return start
    return WindowRect(
        round(start.x + (end.x - start.x) * t),
        round(start.y + (end.y - start.y) * t),
        round(start.width + (end.width - start.width) * t),
        round(start.height + (end.height - start.height) * t),
    )
