"""字体令牌与回退链。"""
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



# ==================== 字体令牌 ====================
# 跨平台回退链：先 Apple 字体，再 Windows 中文字体，最后通用无衬线。
# 启动时由 apply_font_fallbacks() 取第一个系统真实存在的族。
FONT_STACK_CN = (
    "SF Pro Display", "SF Pro Text", "PingFang SC", "Helvetica Neue",
    "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI",
    "Noto Sans CJK SC", "DejaVu Sans", "Arial",
)
FONT_STACK_MONO = (
    "SF Mono", "JetBrains Mono", "Cascadia Mono",
    "Consolas", "Menlo", "DejaVu Sans Mono", "Courier New",
)
# 兜底值（Windows 必备中文字体）；apply_font_fallbacks() 会就地更新这三个名字。

FONT_FAMILY_CN   = "Microsoft YaHei UI"
FONT_FAMILY      = FONT_FAMILY_CN
FONT_FAMILY_MONO = "Consolas"

# 字号阶梯（整体上移 1~2pt，拉开层级、避免拥挤）
FS_TINY    = 11   # 提示 / 说明小字（原 10，用户反馈太小 → +1）
FS_SMALL   = 12   # 次要信息、单行标签、单选项（原 11）
FS_BODY    = 13   # 正文与控件默认字号（原 12）
FS_SUBHEAD = 15   # 卡片小节标题（原 13 粗体）
FS_TITLE   = 17   # 对话框主标题（原 15 粗体）
FS_DISPLAY = 21   # 展示型标题（原 19）


def resolve_font_family(stack, fallback):
    """从回退链中挑第一个系统可用的字体族；无 Tk 环境时返回 fallback。"""
    try:
        from tkinter import font as tkfont
        available = set(tkfont.families())
    except Exception:
        return fallback
    for name in stack:
        if name in available:
            return name
    return fallback


def apply_font_fallbacks():
    """创建 root 之后调用：把 FONT_FAMILY* 解析成当前平台真实存在的字体族。"""
    global FONT_FAMILY_CN, FONT_FAMILY, FONT_FAMILY_MONO
    FONT_FAMILY_CN = resolve_font_family(FONT_STACK_CN, FONT_FAMILY_CN)
    FONT_FAMILY = FONT_FAMILY_CN
    FONT_FAMILY_MONO = resolve_font_family(FONT_STACK_MONO, FONT_FAMILY_MONO)
    # 同步到 config 聚合层：各模块读的是 config.FONT_FAMILY（调用时求值），
    # 不同步的话它们会一直用初始值，回退链形同虚设。
    try:
        from .. import config as _cfg
        _cfg.FONT_FAMILY = FONT_FAMILY
        _cfg.FONT_FAMILY_CN = FONT_FAMILY_CN
        _cfg.FONT_FAMILY_MONO = FONT_FAMILY_MONO
    except Exception:
        pass
    return FONT_FAMILY_CN, FONT_FAMILY_MONO


ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")
ctk.set_widget_scaling(1.0)
