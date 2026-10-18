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
    try:
        # 33 = DWMWA_WINDOW_CORNER_PREFERENCE：按设计令牌给窗口圆角
        corner = ctypes.c_int(DWM_CORNER_PREF)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner))
    except Exception:
        pass


def _set_app_user_model_id() -> None:
    """设置进程 AppUserModelID。必须在任何 Tk 窗口创建之前调用，否则不生效。"""
    if not IS_WINDOWS:
        # ctypes.windll 只在 Windows 上存在，非 Windows 直接短路，避免 AttributeError
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID)
    except Exception:
        pass
