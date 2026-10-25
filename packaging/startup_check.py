"""
启动自检：走**真实入口** main()，确认双击 exe 能起来。

其它脚本都是直接构造 PulsesSwapApp，绕过了 main() 里那几行
（AppUserModelID / DPI 感知 / 缩放锁 / 窗口材质）。这些名字一旦在重构中
从 star-import 里漏掉，测试全绿但程序一启动就 NameError —— 这里专门兜这个洞。

    python packaging/startup_check.py
"""
from __future__ import annotations

import sys
import time
import tkinter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import customtkinter as ctk  # noqa: E402

import pulses_swap as ps  # noqa: E402
from pulses.ui import app as app_module  # noqa: E402

FAIL: list[str] = []


def check(label, condition, detail=""):
    print(("  ok   " if condition else "  FAIL ") + label
          + ("" if condition else f"  {detail}"))
    if not condition:
        FAIL.append(label)


# 启动流程会在 after(150) 弹出「定位数据库」，这里没有真实整合包，直接跳过
app_module.PulsesSwapApp._init_database_flow = lambda self: None


def _fake_mainloop(self, *args, **kwargs):
    """不进事件循环：把窗口建出来，并跑完开窗补间（约 0.6s）。"""
    for _ in range(90):
        try:
            self.update()
        except Exception:
            break
        if float(self.attributes("-alpha")) >= 0.999:
            # 多跑几帧，确保 on_done 已经写回最终矩形
            for _ in range(3):
                self.update()
                time.sleep(0.01)
            break
        time.sleep(0.01)


tkinter.Tk.mainloop = _fake_mainloop
try:
    ctk.CTk.mainloop = _fake_mainloop
except Exception:
    pass

print("== 真实入口 main() ==")
crashed = None
try:
    app_module.main()
except Exception as exc:                      # noqa: BLE001 - 要看到原始异常
    crashed = exc

check("main() 没有抛异常", crashed is None, repr(crashed))
root = tkinter._default_root
check("建出了主窗口", root is not None and bool(root.winfo_exists()))
if root is not None:
    title = str(root.title())
    check(f"标题带版本号（{title}）", ps.VERSION in title, title)
    try:
        alpha = float(root.attributes("-alpha"))
    except Exception:
        alpha = 1.0
    check("窗口不透明（-alpha = 1.0）", abs(alpha - 1.0) < 1e-6, alpha)
    check("窗口有实际尺寸", root.winfo_width() > 400 and root.winfo_height() > 300,
          (root.winfo_width(), root.winfo_height()))
    try:
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        cx = root.winfo_rootx() + root.winfo_width() // 2
        cy = root.winfo_rooty() + root.winfo_height() // 2
        check(f"窗口基本居中（中心 {cx},{cy} / 屏幕 {sw},{sh}）",
              abs(cx - sw // 2) <= 50 and abs(cy - sh // 2) <= 60,
              (cx, cy, sw, sh))
    except Exception:
        pass

check("CTk 的自动 DPI 轮询已关闭",
      ctk.ScalingTracker.deactivate_automatic_dpi_awareness is True)
check("widget_scaling 由我们自己下发",
      ctk.ScalingTracker.widget_scaling == ps.config.UI_SCALE,
      (ctk.ScalingTracker.widget_scaling, ps.config.UI_SCALE))

if root is not None:
    try:
        root.destroy()
    except Exception:
        pass

print()
if FAIL:
    print(f"!!! {len(FAIL)} 项失败: {FAIL}")
    raise SystemExit(1)
print("启动自检：全部通过")
