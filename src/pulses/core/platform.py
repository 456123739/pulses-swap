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
