"""控件工厂与列表滚动条。"""
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
from .button import AnimatedButton

# ==================== 控件工厂 ====================
def make_button(parent, text, command=None, width=None, state="normal", accent=False):
    """统一按钮工厂：返回的按钮自带 hover / 按下的曲线过渡。"""
    kwargs = dict(
        text=text, command=command,
        text_color=C_TEXT_INVERSE if accent else C_TEXT_MAIN,
        border_color=C_ACCENT if accent else C_BORDER_SOFT,
        border_width=BORDER_W, corner_radius=R_CONTROL,
        font=(config.FONT_FAMILY, FS_BODY), height=H_CONTROL, state=state)
    if width is not None:
        kwargs['width'] = width
    if accent:
        # 按下要更沉一档：之前 press_color 直接用了 hover 色，按下去看不出变化
        return AnimatedButton(parent, C_ACCENT, C_ACCENT_HOVER,
                               press_color=C_ACCENT_PRESSED, **kwargs)
    return AnimatedButton(parent, C_PANEL_ALT_BG, C_ACCENT_SOFT,
                           press_color=lerp_color(C_ACCENT_SOFT, C_ACCENT, 0.45),
                           **kwargs)


def make_entry(parent, textvariable=None, placeholder="", width=None):
    kwargs = dict(
        fg_color=C_INPUT_BG, border_color=C_BORDER_SOFT, border_width=BORDER_W,
        corner_radius=R_CONTROL, text_color=C_TEXT_MAIN,
        placeholder_text=placeholder, placeholder_text_color=C_TEXT_MUTED,
        font=(config.FONT_FAMILY, FS_BODY), height=H_CONTROL)
    if textvariable is not None:
        kwargs['textvariable'] = textvariable
    if width is not None:
        kwargs['width'] = width
    return ctk.CTkEntry(parent, **kwargs)


def make_display_box(parent, text="", width=None, height=H_CONTROL):
    frame = ctk.CTkFrame(parent, fg_color=C_INPUT_BG, border_color=C_BORDER_SOFT,
                          border_width=BORDER_W, corner_radius=R_CONTROL,
                          height=height)
    frame.pack_propagate(False)
    label = ctk.CTkLabel(frame, text=text, text_color=C_TEXT_SECONDARY,
                          font=(config.FONT_FAMILY, FS_SMALL), anchor="w",
                          fg_color="transparent")
    label.pack(fill=BOTH, expand=True, padx=PAD_INNER)
    return frame, label


def open_path(path) -> bool:
    """在系统文件管理器里打开路径（Windows / macOS / Linux 都支持）。

    原来直接用 os.startfile —— 那是 Windows 专有 API，Linux 版点了
    「打开TACZ / 目录 / 数据库」全都静默失败（只往日志里写一条错误）。
    """
    target = str(path)
    try:
        if IS_WINDOWS:
            os.startfile(target)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def make_list_scroll(parent, listbox, width=10):
    """给 tk.Listbox 配一条细滚动条 + 顺滑滚轮。

    tk.Listbox 本身没有滚动条（要自己配），而且默认滚轮是「一格一行」，
    条目多的时候一格一格跳，手感很卡。这里统一滚 3 行/格，
    并且只在指针位于列表上时生效（返回 "break" 不让事件冒到外层）。
    """
    # height=1 很关键：CTkScrollbar 默认 200x200，不压下去会把列表容器
    # 的「请求高度」顶到 200+，卡片下限跟着虚高，导入框就会被挤出卡片。
    # 实际高度由 pack(fill="y") 决定，这里只要请求值够小。
    bar = ctk.CTkScrollbar(
        parent, width=px(width), height=1, corner_radius=R_PROGRESS,
        fg_color="transparent", button_color=C_BORDER,
        button_hover_color=C_ACCENT, command=listbox.yview)
    listbox.configure(yscrollcommand=bar.set)

    def _scroll(units):
        """逐帧滑过去，而不是整行一跳。

        Tk 的 Listbox 只能按「行」滚，直接 yview_scroll 会一顿一顿的；
        这里把目标位置换算成视图比例，用补间在 140ms 内滑过去。
        """
        total = max(1, listbox.size())
        first, last = listbox.yview()
        visible = max(0.0, last - first)
        start = first
        target = min(max(0.0, first + units / total), max(0.0, 1.0 - visible))
        if abs(target - start) < 1e-6:
            return "break"

        def frame(e, raw):
            try:
                listbox.yview_moveto(start + (target - start) * e)
            except Exception:
                pass

        tween(listbox, "scroll", 140, frame, easing=ease_out_cubic)
        return "break"

    def _on_wheel(event):
        delta = getattr(event, "delta", 0) or 0
        return _scroll(-3 if delta > 0 else 3)

    def _on_wheel_x11(event):
        return _scroll(-3 if event.num == 4 else 3)

    for seq, fn in (("<MouseWheel>", _on_wheel),
                    ("<Button-4>", _on_wheel_x11),
                    ("<Button-5>", _on_wheel_x11)):
        try:
            listbox.bind(seq, fn, add="+")
        except Exception:
            pass
    return bar


def make_label(parent, text="", fg=None, bg=None, font_size=FS_BODY, bold=False,
               justify=None):
    if fg is None:
        fg = C_TEXT_MAIN
    weight = "bold" if bold else "normal"
    kwargs = dict(text=text, text_color=fg,
                  font=(config.FONT_FAMILY, font_size, weight),
                  anchor="w")
    kwargs['fg_color'] = bg if bg is not None else "transparent"
    # justify 只在显式传入时下发，避免影响其余单行标签的外观。
    # （原来多行提示写的是 justify=LEFT，但本工厂没有该参数 -> 一进设置页就 TypeError）
    if justify is not None:
        kwargs['justify'] = justify
    return ctk.CTkLabel(parent, **kwargs)
