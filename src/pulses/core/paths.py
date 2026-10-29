"""程序常量与路径解析。"""
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


# ==================== 常量定义 ====================
VERSION = "3.0.3"
AUTHOR = "NimShade"
PROJECT_NAME = "Pulses Swap"

IS_WINDOWS = sys.platform.startswith('win')

if getattr(sys, 'frozen', False):
    PROGRAM_DIR = Path(sys.executable).parent
else:
    PROGRAM_DIR = Path(__file__).parent

CONFIG_FILENAME = "PulsesSwap_config.json"
DATABASE_DIRNAME = "PulsesSwap_database"
APP_DIRNAME = "PulsesSwap"


def safe_print(*args, **kwargs) -> None:
    """windowed 打包（console=False）时 sys.stdout 为 None，直接 print 会抛
    AttributeError 并把异常处理路径本身弄崩，这里统一兜底。"""
    try:
        print(*args, **kwargs)
    except Exception:
        pass


def is_dir_writable(directory: Path) -> bool:
    """真实写测试：建目录 → 写临时文件 → 删掉。

    不用 os.access()：在 Windows 上它只看只读属性位，
    对 C:\\Program Files 这类 ACL 拒绝的目录会误报为可写。
    """
    probe = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / f".pulses_write_test_{os.getpid()}_{time.time_ns()}"
        with open(probe, 'w', encoding='utf-8') as f:
            f.write('ok')
        return True
    except Exception:
        return False
    finally:
        if probe is not None:
            try:
                probe.unlink()
            except Exception:
                pass


def get_user_data_dir() -> Path:
    """跨平台用户数据目录：Windows 用 %LOCALAPPDATA%\\PulsesSwap，
    其他平台用 $XDG_DATA_HOME/PulsesSwap 或 ~/.local/share/PulsesSwap。"""
    if IS_WINDOWS:
        base = os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA')
        if base:
            return Path(base) / APP_DIRNAME
        return Path.home() / 'AppData' / 'Local' / APP_DIRNAME
    xdg = os.environ.get('XDG_DATA_HOME')
    if xdg:
        return Path(xdg) / APP_DIRNAME
    return Path.home() / '.local' / 'share' / APP_DIRNAME


def resolve_data_base_dir() -> tuple[Path, bool]:
    """解析数据根目录。返回 (根目录, 是否处于便携模式)。

    优先级：
      1. 程序目录可写 → 直接用程序目录（绿色/便携模式，行为与旧版完全一致）
      2. 程序目录不可写，但数据库确实就在程序目录下
         → 仍然用程序目录（不改变已有用户的数据位置）
      3. 否则 → 用户数据目录（安装到 C:\\Program Files 时的正常路径）。
         即使回退，旧版写在程序目录的 PulsesSwap_config.json 仍会被
         load_db_path() 读到，老用户记下的数据库位置不会丢。
    """
    if is_dir_writable(PROGRAM_DIR):
        return PROGRAM_DIR, True
    if (PROGRAM_DIR / DATABASE_DIRNAME).exists():
        return PROGRAM_DIR, True
    return get_user_data_dir(), False


DATA_BASE_DIR, IS_PORTABLE_MODE = resolve_data_base_dir()

# v2.1 及以前固定把配置写在程序目录，读取时仍需兼容旧文件
LEGACY_BOOTSTRAP_FILE = PROGRAM_DIR / CONFIG_FILENAME

BOOTSTRAP_FILE = DATA_BASE_DIR / CONFIG_FILENAME
DEFAULT_DB_DIR = DATA_BASE_DIR / DATABASE_DIRNAME


def resource_path(filename: str) -> Path:
    """解析随程序分发的资源文件路径（源码运行 / PyInstaller frozen 都适用）。"""
    candidates = []
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        candidates.append(Path(meipass) / filename)
    here = Path(__file__).resolve().parent
    candidates.append(here / filename)                       # 与源码同级
    candidates.append(here.parent / 'packaging' / filename)  # 仓库内 packaging/
    # 拆分后 paths.py 在 src/pulses/core/，仓库根目录的 packaging/
    # 要往上三层；之前源码运行时 icon.png 找不到，窗口只能退回 Tk 默认图标。
    try:
        candidates.append(here.parents[2] / 'packaging' / filename)
    except Exception:
        pass
    for c in candidates:
        try:
            if c.exists():
                return c
        except Exception:
            continue
    return candidates[0]

LEGACY_DB_DIRNAME = "FGC_database"
LEGACY_CACHE_FILE = ".cache.json"
LEGACY_MIGRATED_MARKER = ".migrated_to_pulses_swap"
