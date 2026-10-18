"""带 hover / 按下过渡的按钮。"""
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

class AnimatedButton(ctk.CTkButton):
    """带曲线过渡的按钮：hover / 按下都是逐帧混色，而不是瞬间跳色。

    CTk 自带的 hover 是「瞬时换色」，这里把它的 hover 目标设成底色把它架空，
    再由本类用补间驱动 fg_color。CTk 内部处理器与本类处理器在同一次事件
    分发里先后执行，本类每次都从当前插值色继续，因此不会看到跳变。
    """

    def __init__(self, master, base_color, hover_target, press_color=None,
                 **kwargs):
        kwargs["fg_color"] = base_color
        # hover_color 交给 CTk 用「目标色」：CTk 自己也会在进出/点击动画里
        # 瞬时刷一次颜色，如果这里填底色，就会把我逐帧混出来的中间色顶掉
        # （表现是 hover 一下又弹回原色）。填目标色两边一致，不会打架。
        kwargs["hover_color"] = hover_target
        super().__init__(master, **kwargs)
        self._base_color = base_color
        self._hover_target = hover_target
        self._press_color = press_color or hover_target
        self._current = base_color
        self._hovering = False
        try:
            self.bind("<Enter>", self._anim_enter, add="+")
            self.bind("<Leave>", self._anim_leave, add="+")
            self.bind("<ButtonPress-1>", self._anim_press, add="+")
            self.bind("<ButtonRelease-1>", self._anim_release, add="+")
        except Exception:
            pass

    def _enabled(self):
        try:
            return str(self.cget("state")) == "normal"
        except Exception:
            return True

    def _reassert(self):
        try:
            self.configure(fg_color=self._current)
        except Exception:
            pass

    def _to(self, target, duration=110):
        if target == self._current:
            return
        start = self._current

        def frame(e, raw):
            self._current = lerp_color(start, target, e)
            try:
                self.configure(fg_color=self._current)
            except Exception:
                pass

        frame(0.0, 0.0)
        tween(self, "bg", duration, frame, easing=ease_out_cubic,
              fps=FPS_COLOR)

    # 注意：处理函数一律用 _anim_* 命名，绝不能叫 _on_enter/_on_leave/
    # _on_release —— CTkButton 在 __init__ 里 bind("<ButtonRelease-1>",
    # self._on_release)，那是它执行 command 的地方；一旦被同名覆盖，
    # 按钮就变成「点下去什么都不执行」。
    def _anim_enter(self, _event=None):
        self._hovering = True
        self._reassert()
        if self._enabled():
            self._to(self._hover_target)

    def _anim_leave(self, _event=None):
        self._hovering = False
        self._reassert()
        self._to(self._base_color)

    def _anim_press(self, _event=None):
        self._reassert()
        if self._enabled():
            self._to(self._press_color, 70)

    def _anim_release(self, _event=None):
        self._reassert()
        if not self._enabled():
            return
        self._to(self._hover_target if self._hovering else self._base_color, 120)
