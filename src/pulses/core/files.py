"""文件与格式化小工具。"""
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
