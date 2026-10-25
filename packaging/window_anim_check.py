"""
窗口出现 / 关闭动画自检。

不依赖真实整合包：直接构造主窗口，确认
  1. 出现时先处于「最终位置下方 + 透明」，再收束到最终矩形；
  2. 关闭时先下移/淡出，动画结束后窗口确实隐藏；
  3. 动画不会把窗口留在半透明状态。

    python packaging/window_anim_check.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import customtkinter as ctk  # noqa: E402

import pulses_swap as ps  # noqa: E402
from pulses.ui.window_motion import parse_geometry  # noqa: E402

FAIL: list[str] = []


def check(label, condition, detail=""):
    print(("  ok   " if condition else "  FAIL ") + label
          + ("" if condition else f"  {detail}"))
    if not condition:
        FAIL.append(label)


class CheckApp(ps.PulsesSwapApp):
    def _init_database_flow(self):
        # 自检不需要数据库，也不弹定位框。
        pass


def pump_until(root, predicate, seconds=2.0):
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        root.update()
        if predicate():
            return True
        time.sleep(0.004)
    return bool(predicate())


ps.config.ANIMATIONS_ENABLED = True
root = ctk.CTk()
root.withdraw()
ps.apply_font_fallbacks()
ps.sync_ui_scale(root)
app = CheckApp(root)
root.update_idletasks()
app.show_window()

final = app._window_final_rect
start = parse_geometry(root.geometry())
alpha0 = float(root.attributes("-alpha"))
check("出现动画：起始矩形可解析", start is not None, root.geometry())
check("出现动画：先透明", alpha0 <= 0.02, alpha0)
if start is not None and final is not None:
    offset = max(8, ps.px(26))
    check("出现动画：起始位置在最终位置下方",
          start.y == final.y + offset, (start, final, offset))
    check("出现动画：尺寸不缩放（避免内部重排）",
          (start.width, start.height) == (final.width, final.height),
          (start, final))

opened = pump_until(root, lambda: not app._window_animating, 2.0)
check("出现动画：能收束", opened)
check("出现动画：结束后不透明",
      abs(float(root.attributes("-alpha")) - 1.0) < 1e-6,
      root.attributes("-alpha"))
end_rect = parse_geometry(root.geometry())
check("出现动画：结束时回到最终矩形", end_rect == final, (end_rect, final))

# 关闭：request_exit 与标题栏关闭按钮走同一条路径
close_started = time.perf_counter()
app.request_exit()
app.request_exit()  # 重入应当是 no-op，不能重启一条关闭补间
check("关闭动画：已进入关闭流程",
      bool(getattr(app, "_window_closing", False)))
samples = []
deadline = time.perf_counter() + 2.0
while time.perf_counter() < deadline:
    root.update()
    try:
        samples.append((float(root.attributes("-alpha")),
                        root.winfo_rooty(), bool(root.winfo_viewable())))
    except Exception:
        break
    if not root.winfo_viewable():
        break
    time.sleep(0.004)

elapsed_close = time.perf_counter() - close_started
check("关闭动画：窗口已隐藏", not bool(root.winfo_viewable()))
check("关闭动画：快速完成（<1s）", elapsed_close < 1.0, elapsed_close)
alphas = [s[0] for s in samples]
ys = [s[1] for s in samples]
check("关闭动画：alpha 单调淡出",
      len(alphas) >= 2 and alphas[-1] <= 0.02
      and all(a >= b - 0.02 for a, b in zip(alphas, alphas[1:])),
      alphas[:6])
check("关闭动画：窗口向下收回",
      bool(ys) and max(ys) > min(ys),
      (min(ys) if ys else None, max(ys) if ys else None))

try:
    root.destroy()
except Exception:
    pass

print()
if FAIL:
    print(f"!!! {len(FAIL)} 项失败: {FAIL}")
    raise SystemExit(1)
print("窗口出现/关闭动画：全部通过")
