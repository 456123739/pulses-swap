"""
把文件/文件夹送进系统回收站。

在线同步会删除"本地多余"的枪包，删错了要能找回来，所以默认走回收站：

  · Windows：SHFileOperationW + FOF_ALLOWUNDO（与资源管理器删除等价）
  · Linux/macOS：freedesktop 回收站规范（~/.local/share/Trash）
  · 都不支持时返回 False，由调用方决定是否硬删

与 ``pulses.core.platform.move_to_recycle_bin`` 是同一套逻辑，但这里不依赖
tkinter，方便命令行与测试直接使用。
"""
from __future__ import annotations

import ctypes
import os
import shutil
import sys
import time
import urllib.parse
from pathlib import Path

IS_WINDOWS = sys.platform.startswith("win")

# ---- Windows 常量 ----
FO_DELETE = 3
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400
FOF_NOCONFIRMMKDIR = 0x0200


def move_to_trash(path) -> bool:
    """送进回收站；成功返回 True。"""
    target = Path(path)
    if not target.exists():
        return True
    if IS_WINDOWS:
        return _windows_trash(target)
    return _freedesktop_trash(target)


def _windows_trash(path: Path) -> bool:
    try:
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("wFunc", wintypes.UINT),
                ("pFrom", wintypes.LPCWSTR),
                ("pTo", wintypes.LPCWSTR),
                ("fFlags", ctypes.c_uint16),
                ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", wintypes.LPCWSTR),
            ]

        source = str(path.resolve()) + "\0\0"
        op = SHFILEOPSTRUCTW()
        op.hwnd = None
        op.wFunc = FO_DELETE
        op.pFrom = source
        op.pTo = None
        op.fFlags = (FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI
                     | FOF_SILENT | FOF_NOCONFIRMMKDIR)
        op.fAnyOperationsAborted = False
        op.hNameMappings = None
        op.lpszProgressTitle = None
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        return result == 0 and not op.fAnyOperationsAborted
    except Exception:
        return False


def _trash_root() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "Trash"


def _freedesktop_trash(path: Path) -> bool:
    try:
        root = _trash_root()
        files_dir = root / "files"
        info_dir = root / "info"
        files_dir.mkdir(parents=True, exist_ok=True)
        info_dir.mkdir(parents=True, exist_ok=True)

        name = path.name or "item"
        stem, suffix = (name, "") if path.is_dir() else _split_suffix(name)
        candidate = name
        index = 1
        while (files_dir / candidate).exists() or (info_dir / f"{candidate}.trashinfo").exists():
            candidate = f"{stem}.{index}{suffix}"
            index += 1

        info_path = info_dir / f"{candidate}.trashinfo"
        encoded = urllib.parse.quote(str(path.resolve()))
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        with open(info_path, "w", encoding="utf-8") as fh:
            fh.write(f"[Trash Info]\nPath={encoded}\nDeletionDate={stamp}\n")

        destination = files_dir / candidate
        try:
            os.replace(path, destination)
        except OSError:
            if path.is_dir():
                shutil.move(str(path), str(destination))
            else:
                shutil.copy2(str(path), str(destination))
                path.unlink()
        return True
    except Exception:
        return False


def _split_suffix(name: str) -> tuple[str, str]:
    if "." in name and not name.startswith("."):
        stem, suffix = name.rsplit(".", 1)
        return stem, "." + suffix
    return name, ""


def delete(path) -> bool:
    """先试回收站，失败再硬删。"""
    target = Path(path)
    if not target.exists():
        return True
    if move_to_trash(target):
        return True
    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return True
    except Exception:
        return False
