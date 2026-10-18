"""worker 线程 → 主线程投递。"""
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
