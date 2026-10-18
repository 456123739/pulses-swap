"""
Win11 不透明逻辑的离线验证：伪造 ctypes.windll，检查真正下发的 DWM 属性。

（Linux 上跑不了真 DWM，但可以验证「我们会下发哪些属性、值是多少」，
 以及失焦/弹窗/轮询这些触发路径有没有真的调用到。）
"""
import ctypes
import importlib.util
import time
import types

SRC = "/home/admin/111/pulses-swap/src/pulses_swap.py"
spec = importlib.util.spec_from_file_location("ps", SRC)
ps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ps)

FAIL = []


def check(label, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + label + ("" if cond else "  " + str(detail)))
    if not cond:
        FAIL.append(label)


calls = []


class FakeDwm:
    def DwmSetWindowAttribute(self, hwnd, attr, ptr, size):
        val = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_int)).contents.value
        calls.append((hwnd, attr, val))
        return 0


# 拆分后各模块 `from .config import *` 会留下 IS_WINDOWS 快照，逐个打补丁
ps.config.IS_WINDOWS = True
ps.IS_WINDOWS = True
import importlib as _il
_mods = [ps.utils, ps.app, ps.dialogs]
for _name in ("pulses.core.platform", "pulses.ui.window", "pulses.ui.app"):
    try:
        _mods.append(_il.import_module(_name))
    except Exception:
        pass
for _m in _mods:
    _m.IS_WINDOWS = True
ps.ctypes.windll = types.SimpleNamespace(
    dwmapi=FakeDwm(),
    user32=types.SimpleNamespace(GetParent=lambda h: h + 1000,
                                 GetDC=lambda h: 1, ReleaseDC=lambda h, d: 1),
    shcore=types.SimpleNamespace(SetProcessDpiAwareness=lambda v: 0),
    gdi32=types.SimpleNamespace(GetDeviceCaps=lambda a, b: 96),
    winmm=types.SimpleNamespace(timeBeginPeriod=lambda v: 0, timeEndPeriod=lambda v: 0))

print("== 1. 下发的 DWM 属性 ==")
root = ps.ctk.CTk()
root.geometry("500x400")
root.update()
calls.clear()
ps.make_window_opaque(root)
got = {}
for _h, attr, val in calls:
    got.setdefault(attr, val)
check("DWMWA_SYSTEMBACKDROP_TYPE(38) = 1（DWMSBT_NONE，禁掉 Mica）",
      got.get(38) == 1, got)
check("DWMWA_MICA_EFFECT(1029) = 0（旧版 Win11 兜底）", got.get(1029) == 0, got)
check("DWMWA_USE_IMMERSIVE_DARK_MODE(20) = 0（浅色标题栏）", got.get(20) == 0, got)
check("DWMWA_WINDOW_CORNER_PREFERENCE(33) = 2（圆角）", got.get(33) == 2, got)

print("== 2. 触发路径：失焦 / 弹窗 / 轮询 ==")
ps.DatabaseLocatorDialog.show = lambda self: None
root.destroy()
root = ps.ctk.CTk()
ps.apply_font_fallbacks()
ps.sync_ui_scale(root)
root.geometry("900x600")
root.update()
app = ps.PulsesSwapApp(root)


def pump(ms):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        root.update()
        time.sleep(0.005)


pump(800)
check("防护已装配", hasattr(app, "_opacity_last"))
time.sleep(0.4)
calls.clear()
root.event_generate("<FocusIn>")
pump(300)
check("失焦/聚焦时会补一次不透明", len(calls) >= 4, len(calls))
check("补的那次也带 38=1", any(a == 38 and v == 1 for _h, a, v in calls), calls[:4])
win = ps.ctk.CTkToplevel(root)
win.geometry("300x200")
win.update()
time.sleep(0.4)
calls.clear()
app._on_opacity_event()
pump(200)
check("有弹窗时主窗口与弹窗都被覆盖", len({h for h, _a, _v in calls}) >= 2,
      len({h for h, _a, _v in calls}))
win.destroy()
root.destroy()

print()
if FAIL:
    print(f"!!! {len(FAIL)} 项失败: {FAIL}")
    raise SystemExit(1)
print("Win11 不透明逻辑验证：全部通过")
