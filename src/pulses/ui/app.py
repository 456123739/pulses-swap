"""主窗口装配：把各 mixin 组合成 PulsesSwapApp，并提供 main()。"""
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


from .window import WindowMixin
from .page_home import HomePageMixin
from .page_log import LogPageMixin
from .database import DatabaseMixin
from .packs import PacksMixin
from .transfer import TransferMixin
from .misc import MiscMixin


class PulsesSwapApp(WindowMixin, HomePageMixin, LogPageMixin, DatabaseMixin,
                    PacksMixin, TransferMixin, MiscMixin):
    """主窗口：行为分散在 ui/ 下的各个 mixin 里，这里只做装配。"""

    def __init__(self, root):
        self.root = root
        self.root.title(f"{PROJECT_NAME} v{VERSION}")
        # 高分屏下窗口会被 window_scaling 放大，启动尺寸要按屏幕收口，
        # 否则 125%/150% 时窗口可能比屏幕还高。
        try:
            scr_w = int(self.root.winfo_screenwidth() or WINDOW_W)
            scr_h = int(self.root.winfo_screenheight() or WINDOW_H)
        except Exception:
            scr_w, scr_h = WINDOW_W, WINDOW_H
        scale = config.UI_SCALE if config.UI_SCALE > 0 else 1.0
        win_w = int(min(WINDOW_W, max(WINDOW_MIN_W, scr_w / scale - 40)))
        win_h = int(min(WINDOW_H, max(WINDOW_MIN_H, scr_h / scale - 90)))
        self.root.geometry(f"{win_w}x{win_h}")
        self.root.minsize(WINDOW_MIN_W, WINDOW_MIN_H)

        # ==================== Win11 透明修复 ====================
        try:
            self.root.attributes('-alpha', 1.0)
        except Exception:
            pass
        try:
            self.root.wm_attributes('-alpha', 1.0)
        except Exception:
            pass
        try:
            self.root.attributes('-transparentcolor', '')
        except Exception:
            pass
        try:
            self.root.configure(fg_color=C_WINDOW_BG)
        except Exception:
            try:
                self.root.configure(bg=C_WINDOW_BG)
            except Exception:
                pass

        self._disable_win11_transparency()
        # ========================================================

        self.current_pack_path: Path | None = None
        self.tacz_path: Path | None = None
        self.preset_manager: PresetManager | None = None
        self.log_manager: LogManager | None = None
        self.settings = AppSettings()
        self.recent_manager: RecentPacksManager | None = None
        self.tacz_watcher: TaczWatcher | None = None

        self.is_applying = False
        self.current_selected_preset: str | None = None
        self.show_full_log = False
        self.loading_presets = False
        self.recent_visible = False
        self.dont_remind_this_session = False
        self.db_ready = False
        self.last_after_migrate_mode = "mark"

        self.guide: GuideManager | None = None

        # worker 线程 → 主线程的投递队列，越早启动越好
        start_ui_pump(self.root)
        self.setup_ui()
        self.setup_menu()

        self._install_opacity_guard()
        self.root.after(150, self._init_database_flow)


def main():
    # 第一件事：任务栏图标归属必须在任何窗口存在之前定好
    _set_app_user_model_id()
    # 第二件：DPI 感知也要在窗口创建之前声明，否则 Windows 会拉伸位图（字糊）
    detected_scale = enable_dpi_awareness()
    # 第三件：把 Windows 定时器精度提到 1ms，否则补间只有 ~30fps（一卡一卡）
    enable_high_resolution_timer()
    if HAS_DND:
        try:
            root = TkinterDnD.Tk()
            root.configure(bg=C_WINDOW_BG)
        except Exception:
            root = ctk.CTk()
    else:
        root = ctk.CTk()

    # 窗口图标：源码运行取 packaging/，打包运行取 sys._MEIPASS
    apply_window_icon(root)

    # 字体回退链：root 就绪后解析一次，供所有控件工厂使用
    apply_font_fallbacks()
    # 自绘控件（Canvas / grid minsize）要按同一系数放大，别和 CTk 控件错位
    scale = sync_ui_scale(root)
    safe_print(f"DPI 检测: {detected_scale:.2f} · UI 缩放: {scale:.2f}")

    # ==================== Win11 透明修复（第一道） ====================
    try:
        root.attributes('-alpha', 1.0)
    except Exception:
        pass
    try:
        root.wm_attributes('-alpha', 1.0)
    except Exception:
        pass
    try:
        root.attributes('-transparentcolor', '')
    except Exception:
        pass
    try:
        root.configure(fg_color=C_WINDOW_BG)
    except Exception:
        try:
            root.configure(bg=C_WINDOW_BG)
        except Exception:
            pass

    def _disable_dwm(hwnd_root):
        if not IS_WINDOWS:
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(hwnd_root.winfo_id())
            if not hwnd:
                hwnd = hwnd_root.winfo_id()
            _apply_opaque_window(hwnd)
        except Exception:
            pass

    try:
        root.update_idletasks()
        _disable_dwm(root)
    except Exception:
        pass
    # ================================================================

    app = PulsesSwapApp(root)

    try:
        root.after(80, lambda: _disable_dwm(root))
    except Exception:
        pass

    def on_closing():
        # 退出语义与界面内的「退出程序」完全一致（见 request_exit）
        app.request_exit()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
