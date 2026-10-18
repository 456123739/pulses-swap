"""平台相关：回收站 / DPI / 缩放。"""
from __future__ import annotations

import ctypes
try:                      # ctypes.wintypes 在非 Windows 上会抛 ValueError
    import ctypes.wintypes
except Exception:
    ctypes.wintypes = None
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import zipfile
from datetime import datetime
from pathlib import Path
from tkinter import *
from tkinter import filedialog

import customtkinter as ctk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False
    TkinterDnD = None
    DND_FILES = None

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False
    Observer = None
    FileSystemEventHandler = object

from .. import config
from ..config import *

# ==================== Windows 原生回收站 ====================
FO_DELETE = 0x0003
FOF_ALLOWUNDO = 0x0040
FOF_NOCONFIRMATION = 0x0010
FOF_NOERRORUI = 0x0400
FOF_SILENT = 0x0004
FOF_NOCONFIRMMKDIR = 0x0200


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.wintypes.HWND),
        ("wFunc", ctypes.wintypes.UINT),
        ("pFrom", ctypes.wintypes.LPCWSTR),
        ("pTo", ctypes.wintypes.LPCWSTR),
        ("fFlags", ctypes.wintypes.USHORT),
        ("fAnyOperationsAborted", ctypes.wintypes.BOOL),
        ("hNameMappings", ctypes.wintypes.LPVOID),
        ("lpszProgressTitle", ctypes.wintypes.LPCWSTR),
    ]


def move_to_recycle_bin(path) -> bool:
    """使用 Windows 原生 SHFileOperationW 将文件/文件夹送入回收站"""
    if not IS_WINDOWS:
        return False
    try:
        p = Path(path)
        if not p.exists():
            return True
        path_str = str(p.resolve()) + '\0\0'
        op = _SHFILEOPSTRUCTW()
        op.hwnd = None
        op.wFunc = FO_DELETE
        op.pFrom = path_str
        op.pTo = None
        op.fFlags = (FOF_ALLOWUNDO | FOF_NOCONFIRMATION |
                     FOF_NOERRORUI | FOF_SILENT | FOF_NOCONFIRMMKDIR)
        op.fAnyOperationsAborted = False
        op.hNameMappings = None
        op.lpszProgressTitle = None
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        return (result == 0) and (not op.fAnyOperationsAborted)
    except Exception:
        return False

# ==================== DPI / 缩放 ====================
# Windows 上必须做两件事，缺一个都会出问题：
#   · 进程声明 DPI 感知 —— 否则系统会把窗口位图整体拉伸，字就是糊的；
#   · 自绘的 tk.Canvas 用原始像素，得乘上和 CTk 相同的缩放系数，
#     否则系统 125%/150% 下会和 CTk 控件错位（CTk 控件自己会缩放）。


def enable_high_resolution_timer() -> None:
    """Windows 默认定时器精度约 15.6ms：after(17) 实际会变成 ~31ms，
    60fps 的补间直接掉到 30fps，观感就是「一卡一卡」。

    timeBeginPeriod(1) 把精度提到 1ms（用完在退出时 timeEndPeriod 还回去）。
    非 Windows 平台无事发生。
    """
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:
        pass


def release_high_resolution_timer() -> None:
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.winmm.timeEndPeriod(1)
    except Exception:
        pass


def enable_dpi_awareness() -> float:
    """声明 DPI 感知并返回系统缩放系数（1.0 / 1.25 / 1.5 …）。

    必须在任何窗口创建之前调用 —— CTk 自己也会声明，但它在第一个控件
    创建时才做，那时窗口已经按未感知状态建好了，仍会被拉伸。
    """
    if not IS_WINDOWS:
        return 1.0
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)      # PER_MONITOR_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            return 1.0
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        try:
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)   # LOGPIXELSX
        finally:
            ctypes.windll.user32.ReleaseDC(0, hdc)
        return max(1.0, min(3.0, float(dpi) / 96.0))
    except Exception:
        return 1.0


def sync_ui_scale(root_widget) -> float:
    """root 建好后同步一次：CTk 的控件缩放 × 自绘控件用的像素换算。

    窗口尺寸也必须一起放大（set_window_scaling）。只放大控件不放大窗口，
    内容就撑不下 —— 表现是列表被撑得很大、下面的一键替换/日志被挤出窗口，
    看起来像「强制展示所有条目、不允许被裁切」。
    """
    try:
        config.UI_SCALE = float(ctk.ScalingTracker.get_widget_scaling(root_widget))
    except Exception:
        config.UI_SCALE = 1.0
    try:
        ctk.set_window_scaling(config.UI_SCALE)
    except Exception:
        pass
    return config.UI_SCALE


def px(value):
    """设计稿像素 → 当前缩放下的像素（只给 tk.Canvas / grid minsize 用）。"""
    return int(round(float(value) * config.UI_SCALE))


def tk_font(family, size_px, weight=None):
    """原生 Tk 控件用的字体元组（Listbox / Canvas 文字）。

    Tk 里**正数**字号是「磅」，会被 tk scaling 再乘一次（96dpi 下 1.33，
    150% 下 2.0），和 CTk 的像素字号完全对不上 —— 表现就是同一个界面里
    原生控件的字比 CTk 控件大 30%~100%。**负数**字号才是像素，这里统一用负值，
    并且自己乘 UI_SCALE，和 CTk 控件严格同一套缩放。
    """
    size = max(1, int(round(float(size_px) * config.UI_SCALE)))
    if weight:
        return (family, -size, weight)
    return (family, -size)


def lock_ctk_scaling(scale) -> float:
    """锁死 CTk 的缩放，同时**彻底关掉它的 DPI 自动检测**。

    这是 Win11「明明没写半透明，窗口却半透明」的真正根因：
    customtkinter 的 ScalingTracker.check_dpi_scaling() 每 100ms 轮询一次
    （scaling_tracker.py:184），一旦判定 DPI 变化就
        window.attributes("-alpha", 0.15) → 改缩放 → attributes("-alpha", 1)
    在 Win11 上这套「先透明再还原」会：
      · 让 DWM 重新评估窗口材质，Mica/亚克力被重新打开（就是壁纸透进来）；
      · 弹窗/窗口重新映射时误判一次 DPI 变化，主窗口瞬间掉到 15% 不透明度；
      · 中途只要缩放回调抛一次异常，alpha 就永远停在 0.15（几乎看不见）。
    我们自己做 DPI 感知（enable_dpi_awareness）+ 自己做缩放，
    不需要 CTk 这套轮询，直接把它摘掉：alpha 从此只有我们自己写。
    """
    try:
        tracker = ctk.ScalingTracker
    except Exception:
        return float(scale or 1.0)
    scale = max(0.4, float(scale or 1.0))
    try:
        tracker.deactivate_automatic_dpi_awareness = True
    except Exception:
        pass
    try:
        # 置 True：add_widget/add_window 就不会再挂 100ms 轮询
        tracker.update_loop_running = True
    except Exception:
        pass
    try:
        # 双保险：即使将来 CTk 改了内部实现，也不会再走到那段 alpha 闪切
        tracker.check_dpi_scaling = classmethod(lambda cls: None)
    except Exception:
        pass
    try:
        # 已登记窗口的 DPI 缓存归一成 1.0，之后缩放系数 = 我们显式设的值，
        # 不会和真实 DPI 再乘一次（那就是双重缩放）
        for window in list(tracker.window_dpi_scaling_dict):
            tracker.window_dpi_scaling_dict[window] = 1.0
    except Exception:
        pass
    for setter in (ctk.set_widget_scaling, ctk.set_window_scaling):
        try:
            setter(scale)
        except Exception:
            pass
    return scale


# ==================== 程序入口 ====================
def apply_window_icon(window) -> None:
    """设置窗口/任务栏/Alt-Tab 图标。任一方式失败都不影响启动。"""
    # 1) Windows：iconbitmap(default=...) 最稳，同时作用于后续所有 toplevel
    try:
        ico = resource_path("icon.ico")
        if IS_WINDOWS and ico.exists():
            window.iconbitmap(default=str(ico))
    except Exception:
        pass
    # 2) 跨平台：iconphoto。PhotoImage 必须挂在对象上保留引用，
    #    否则被 GC 回收后图标会消失。
    try:
        png = resource_path("icon.png")
        if png.exists():
            img = PhotoImage(file=str(png))
            window.iconphoto(True, img)
            window._pulses_icon_ref = img
    except Exception:
        pass


# Windows 任务栏按钮的图标不取窗口图标，而是取进程 AppUserModelID 对应的图标
# （快捷方式图标 / exe 内嵌图标）。不显式设置时任务栏会退回 Tk 默认羽毛图标。
# 取值与 installer.iss 的 publisher 命名保持一致。
APP_USER_MODEL_ID = "Pulses0Studio.PulsesSwap"


def make_window_opaque(window) -> bool:
    """把窗口设成完全不透明（禁用 Win11 的 Mica / Acrylic 背景材质）。

    必须能反复调用：窗口失焦、弹出子窗口、切换主题时 DWM 会**重新评估**
    窗口材质，Mica 会自己回来 —— 这正是「一有弹窗在前面，主窗口就变
    半透明」的成因。所以除了启动时，还要在焦点/映射变化时补一次。
    """
    if not IS_WINDOWS:
        return False
    try:
        window.attributes("-alpha", 1.0)
    except Exception:
        pass
    try:
        window.attributes("-transparentcolor", "")
    except Exception:
        pass
    try:
        hwnd = (ctypes.windll.user32.GetParent(window.winfo_id())
                or window.winfo_id())
        _apply_opaque_window(hwnd)
        return True
    except Exception:
        return False


def refresh_window_opacity(root) -> int:
    """给主窗口与所有子窗口重新上一次「不透明」，返回处理了几个窗口。"""
    if not IS_WINDOWS:
        return 0
    count = 0
    if make_window_opaque(root):
        count += 1
    try:
        for child in root.winfo_children():
            try:
                if child.winfo_class() == "Toplevel":
                    if make_window_opaque(child):
                        count += 1
            except Exception:
                pass
    except Exception:
        pass
    return count


def _color_ref(hex_color: str) -> int:
    """'#RRGGBB' → Win32 COLORREF（0x00BBGGRR）。解析失败返回 -1（调用方跳过）。"""
    try:
        text = str(hex_color).lstrip("#")
        if len(text) != 6:
            return -1
        r = int(text[0:2], 16)
        g = int(text[2:4], 16)
        b = int(text[4:6], 16)
        return (b << 16) | (g << 8) | r
    except Exception:
        return -1


def _apply_opaque_window(hwnd) -> None:
    """把 Win11 窗口设成完全不透明（禁用 Mica / Acrylic 背景材质）。

    关键在 DWMWA_SYSTEMBACKDROP_TYPE(38)：值 0 是「自动」，系统会自己挑
    Mica/Acrylic —— 那就是壁纸透进来的原因；必须显式设成 1(DWMSBT_NONE)。
    """
    if not IS_WINDOWS:
        return
    try:
        none_backdrop = ctypes.c_int(1)      # DWMSBT_NONE
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 38, ctypes.byref(none_backdrop), ctypes.sizeof(none_backdrop))
    except Exception:
        pass
    try:
        # Win11 早期版本用未公开的 DWMWA_MICA_EFFECT(1029)，关掉它兜底
        mica_off = ctypes.c_int(0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 1029, ctypes.byref(mica_off), ctypes.sizeof(mica_off))
    except Exception:
        pass
    try:
        light_titlebar = ctypes.c_int(0)     # 浅色标题栏（与主题一致）
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(light_titlebar),
            ctypes.sizeof(light_titlebar))
    except Exception:
        pass
    # 标题栏 / 边框 / 标题文字显式上色（Win11 22H2+）。
    # 不设的话 DWM 会按系统主题给标题栏铺一层带材质的底 —— 那层同样会透出壁纸，
    # 而且和我们的 #F5F7F8 对不上，看起来像「窗口没画完」。
    for attr, color in ((35, C_WINDOW_BG),      # DWMWA_CAPTION_COLOR
                        (36, C_TEXT_MAIN),      # DWMWA_TEXT_COLOR
                        (34, C_BORDER_SOFT)):   # DWMWA_BORDER_COLOR
        value = _color_ref(color)
        if value < 0:
            continue
        try:
            ref = ctypes.c_int(value)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attr, ctypes.byref(ref), ctypes.sizeof(ref))
        except Exception:
            pass
    try:
        # 33 = DWMWA_WINDOW_CORNER_PREFERENCE：按设计令牌给窗口圆角
        corner = ctypes.c_int(DWM_CORNER_PREF)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner))
    except Exception:
        pass


def set_app_user_model_id() -> None:
    """设置进程 AppUserModelID。必须在任何 Tk 窗口创建之前调用，否则不生效。"""
    if not IS_WINDOWS:
        # ctypes.windll 只在 Windows 上存在，非 Windows 直接短路，避免 AttributeError
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID)
    except Exception:
        pass


# ==================== 对外别名 ====================
# `from ..utils import *` 不会带出下划线开头的名字，app.main() 里要用这两个，
# 所以显式给一份公开别名（曾经因为漏了这一步，双击 exe 直接 NameError 起不来）。
apply_opaque_window = _apply_opaque_window


# ==================== 身份配色（玩家 / 开发者）====================
# 只换「强调色系 + 页面底」，卡片仍然是白的，所以切身份不会整屏变色，
# 但一眼能看出现在是谁的界面。
ROLE_THEME = {
    "player": {
        "accent": "#5BA89A", "accent_hover": "#4A9285",
        "accent_pressed": "#3D7A6E", "accent_soft": "#D6E8E4",
        "window": "#F2F3F5", "input": "#F4F6F7",
    },
    "developer": {
        # 比 #5C6E96 再压深一档：软底上的小字才够 4.5:1，
        # 白字压在实心按钮上也不会发灰
        "accent": "#4E5F84", "accent_hover": "#42506F",
        "accent_pressed": "#35415A", "accent_soft": "#E6EBF4",
        "window": "#F2F3F7", "input": "#F4F5F9",
    },
}

_SWAP_PROPS = ("fg_color", "text_color", "border_color", "hover_color",
               "progress_color", "button_color", "selected_color",
               "text_color_disabled")


def _channel_map(mapping):
    """把 (旧值, 新值) 直接做成小写查找表。"""
    return {str(old).lower(): str(new) for old, new in mapping.items()}


def role_color_map(previous: str, target: str) -> dict:
    a = ROLE_THEME.get(previous) or ROLE_THEME["player"]
    b = ROLE_THEME.get(target) or ROLE_THEME["player"]
    return _channel_map({
        a["accent"]: b["accent"],
        a["accent_hover"]: b["accent_hover"],
        a["accent_pressed"]: b["accent_pressed"],
        a["accent_soft"]: b["accent_soft"],
        a["window"]: b["window"],
        a["input"]: b["input"],
    })


def theme_widgets(widget, previous: str, target: str) -> int:
    """widget 可以是单个控件，也可以是控件列表/元组（页面不在 winfo_children 里）。"""
    if isinstance(widget, (list, tuple, set)):
        return sum(theme_widgets(w, previous, target) for w in widget)
    """把一棵控件树里「玩家配色」换成目标身份配色，返回改了几个。

    CTk 控件在创建时就把颜色烘进画布，换身份只能重刷一遍。逐控件改属性
    比重建整棵界面安全得多，也不会丢状态。
    """
    mapping = role_color_map(previous, target)
    if not mapping or previous == target:
        return 0
    touched = 0
    stack = [widget]
    while stack:
        node = stack.pop()
        try:
            stack.extend(node.winfo_children())
        except Exception:
            pass
        # AnimatedButton 内部记着三态颜色，不一起改的话 hover 会跳回旧色
        for attr in ("_base_color", "_hover_target", "_press_color", "_current"):
            try:
                value = getattr(node, attr, None)
                if isinstance(value, str) and value.lower() in mapping:
                    setattr(node, attr, mapping[value.lower()])
                    touched += 1
            except Exception:
                pass
        # 注意：CTk 控件的 keys() 返回的是内部画布的选项，不含 fg_color 等，
        # 不能用 "prop in keys()" 判断，直接 cget 试探（读不到就跳过）
        changed = {}
        for prop in _SWAP_PROPS:
            try:
                value = node.cget(prop)
            except Exception:
                continue
            if isinstance(value, str) and value.lower() in mapping:
                changed[prop] = mapping[value.lower()]
        if changed:
            try:
                node.configure(**changed)
                touched += 1
            except Exception:
                pass
        # 自绘分段控件：内部缓存了颜色，需要同步
        if hasattr(node, "_pill_color"):
            for attr, key in (("_pill_color", "accent_soft"),
                              ("_hover_color", "accent_soft"),
                              ("_text_color", "text_main"),
                              ("_active_text_color", "accent"),
                              ("_bg", "card")):
                try:
                    value = getattr(node, attr, None)
                    if isinstance(value, str) and value.lower() in mapping:
                        setattr(node, attr, mapping[value.lower()])
                except Exception:
                    pass
            try:
                node.select(node.current(), animate=False)
            except Exception:
                pass
    return touched
