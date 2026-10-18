"""日志页"""
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
from .. import config
from ..utils import *
from ..animation import *
from ..widget import *
from ..dialogs import *
from ..managers import *
from ..pages import *



# ==================== 主窗口 ====================


class LogPageMixin:
    """日志页"""

    # ==================== 日志页 ====================
    def _build_log_page(self):
        page = ctk.CTkFrame(self.stack.canvas, fg_color=C_WINDOW_BG)
        log_group = ctk.CTkFrame(page, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                  border_width=BORDER_W, border_color=C_BORDER_SOFT)
        log_group.pack(fill=BOTH, expand=True)
        attach_hover_glow(log_group)
        make_label(log_group, text="运行日志", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        log_content = ctk.CTkFrame(log_group, fg_color="transparent")
        log_content.pack(fill=BOTH, expand=True, padx=PAD_CARD_X,
                         pady=(0, PAD_CARD_Y))
        log_toolbar = ctk.CTkFrame(log_content, fg_color="transparent")
        log_toolbar.pack(fill=X, pady=(0, PAD_TIGHT))
        self.log_toggle_btn = make_button(log_toolbar, "显示完整日志",
                                           command=self.toggle_log_mode)
        self.log_toggle_btn.pack(side=LEFT)
        self.log_clear_btn = make_button(log_toolbar, "清空", command=self.clear_log)
        self.log_clear_btn.pack(side=LEFT, padx=(PAD_TIGHT, 0))
        self.log_text = ctk.CTkTextbox(log_content, height=H_LOG_BOX,
                                        fg_color=C_INPUT_BG,
                                        border_color=C_BORDER_SOFT, border_width=BORDER_W,
                                        corner_radius=R_CONTROL, text_color=C_TEXT_MAIN,
                                        font=(FONT_FAMILY_MONO, FS_BODY), wrap="word")
        self.log_text.pack(fill=BOTH, expand=True)

        self.log_manager = LogManager(self.log_text, self.root)
        return page
