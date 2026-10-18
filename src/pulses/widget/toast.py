"""右上角浮出提示。"""
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
from ..utils import *
from ..animation import *

class Toast:
    """右上角浮出提示：曲线滑入 + 自动淡出，全程不阻塞操作。"""

    def __init__(self, host, text, kind="success", duration_ms=1700):
        self.host = host
        self.color = {"success": C_SUCCESS, "info": C_ACCENT,
                      "warning": C_WARNING, "error": C_ERROR}.get(kind, C_ACCENT)
        self.frame = ctk.CTkFrame(host.overlay_host, fg_color=C_PANEL_BG,
                                   corner_radius=R_CONTROL,
                                   border_width=BORDER_W,
                                   border_color=self.color)
        self.label = ctk.CTkLabel(self.frame, text=text, text_color=self.color,
                                   font=(config.FONT_FAMILY, FS_SMALL),
                                   fg_color="transparent")
        self.label.pack(padx=PAD_CARD_X, pady=PAD_TIGHT)
        # _slide > 0 表示浮层右边缘越出容器右边缘（= 在屏幕外），
        # 入场从 +28 滑到 0，出场再滑回去 —— 之前符号写反了，
        # 变成「从里往外滑」，看着像往右弹一下。
        self._slide = 28.0
        self._hold_ms = duration_ms
        self._place()
        self._play_in()

    def _place(self):
        try:
            self.frame.place(relx=1.0, rely=0.0, anchor="ne",
                              x=-PAD_WINDOW + self._slide, y=PAD_WINDOW)
        except Exception:
            pass

    def _play_in(self):
        def frame(e, raw):
            self._slide = lerp(28.0, 0.0, e)
            self._place()

        def done():
            try:
                self.host.root.after(self._hold_ms, self._play_out)
            except Exception:
                pass

        frame(0.0, 0.0)
        tween(self.frame, "toast_in", 200, frame, done, easing=ease_out_back)

    def _play_out(self):
        def frame(e, raw):
            self._slide = lerp(0.0, 28.0, e)
            self._place()
            try:
                self.frame.configure(
                    fg_color=lerp_color(C_PANEL_BG, C_WINDOW_BG, e),
                    border_color=lerp_color(self.color, C_WINDOW_BG, e))
                self.label.configure(
                    text_color=lerp_color(self.color, C_WINDOW_BG, e))
            except Exception:
                pass

        tween(self.frame, "toast_out", 190, frame, self.close,
              easing=ease_in_out_cubic)

    def close(self):
        cancel_all_tweens(self.frame)
        # 清掉宿主持有的引用，否则 app._toast 会一直指向已销毁的浮层
        try:
            if getattr(self.host, "_toast", None) is self:
                self.host._toast = None
        except Exception:
            pass
        try:
            self.frame.destroy()
        except Exception:
            pass
