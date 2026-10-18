"""
通用工具：回收站 / 线程投递 / DPI / 小工具
（由单文件按分区拆分而来，逻辑未改动）
"""
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

from . import config
from .config import *
from .utils import *
from . import config



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

# ==================== 线程 → 主线程投递 ====================
# Tkinter 的 after() 从 worker 线程调用并不可靠：主线程不在 mainloop 里时
# 会直接抛 RuntimeError("main thread is not in main loop")，worker 线程当场死掉
# —— 表现就是「预设列表永远停在加载中」+ 日志里一堆报错。
# 这里统一走队列：worker 只管入队，主线程每 25ms 取一次。
_UI_QUEUE: "queue.Queue" = queue.Queue()
_UI_PUMP_RUNNING = False


def ui_call(root, func=None, *args) -> None:
    """线程安全地把调用切回主线程执行。"""
    if func is None:
        return
    if threading.current_thread() is threading.main_thread():
        try:
            root.after(0, func, *args)
            return
        except Exception:
            pass          # 退化成队列，绝不抛给调用方
    _UI_QUEUE.put((func, args))


def start_ui_pump(root, interval_ms: int = 25) -> None:
    """主线程轮询队列（只需启动一次）。"""
    global _UI_PUMP_RUNNING
    if _UI_PUMP_RUNNING:
        return
    _UI_PUMP_RUNNING = True

    def _pump():
        while True:
            try:
                func, args = _UI_QUEUE.get_nowait()
            except queue.Empty:
                break
            try:
                func(*args)
            except Exception:
                safe_print("UI 任务执行失败:", traceback.format_exc())
        try:
            root.after(interval_ms, _pump)
        except Exception:
            pass

    try:
        root.after(interval_ms, _pump)
    except Exception:
        pass


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

# ==================== 辅助函数 ====================
def sanitize_filename(name: str) -> str:
    if not name:
        return "unnamed"
    safe = "".join(c if c.isalnum() or c in " _-." else "_" for c in name)
    return safe.strip() or "unnamed"


def get_pack_id(pack_path: Path) -> str:
    name = pack_path.name
    safe_name = sanitize_filename(name)
    path_hash = hashlib.md5(str(pack_path.resolve()).encode('utf-8')).hexdigest()[:6]
    return f"{safe_name}_{path_hash}"


def generate_export_filename(preset_name: str, version: str,
                              is_incremental: bool, increment: int = 0) -> str:
    safe_preset = sanitize_filename(preset_name)
    safe_version = sanitize_filename(version) if version else "v1.0.0"
    if is_incremental:
        return f"{safe_preset}-{safe_version}-更新-{increment}.fgcupdate"
    return f"{safe_preset}-{safe_version}-完整.fgcpack"


def format_size(size_bytes: int) -> str:
    try:
        size = float(size_bytes)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    except Exception:
        return f"{size_bytes} B"


def get_item_fingerprint(item_path: Path) -> dict:
    if not item_path.exists():
        return {}
    if item_path.is_file():
        try:
            stat = item_path.stat()
            return {'type': 'zip', 'size': stat.st_size, 'file_count': 1}
        except Exception:
            return {}
    total_size = 0
    file_count = 0
    try:
        for item in item_path.rglob('*'):
            if item.is_file():
                total_size += item.stat().st_size
                file_count += 1
    except Exception:
        pass
    return {'type': 'folder', 'size': total_size, 'file_count': file_count}


def fingerprints_match(a: dict, b: dict) -> bool:
    if not a or not b:
        return False
    if a.get('size') != b.get('size'):
        return False
    if a.get('file_count', 0) != b.get('file_count', 0):
        return False
    return True


def locate_tacz_by_path(path: Path) -> Path | None:
    """
    从给定路径定位 tacz 文件夹。
    1) 如果是文件，从父目录开始；
    2) 本层找 tacz；
    3) 向上逐层找（最多 8 层）。
    返回 tacz 文件夹路径，找不到返回 None。
    """
    if not path:
        return None
    try:
        p = path if path.is_dir() else path.parent
    except Exception:
        return None
    # 本层
    c = p / 'tacz'
    if c.exists() and c.is_dir():
        return c
    # 向上
    current = p
    for _ in range(8):
        c = current / 'tacz'
        if c.exists() and c.is_dir():
            return c
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None
