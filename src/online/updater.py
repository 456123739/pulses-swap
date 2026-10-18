"""
安装器：把暂存区的内容换进正式目录。

核心要求是"装坏了不能半新半旧"。做法：

  · 单文件：同卷临时文件 + ``os.replace``，原子替换
  · 文件夹：``目标 → .pulses-old``、``新目录 → 目标``、删 ``.pulses-old``，
    两步改名之间写日志；程序崩溃后下次启动按日志补完或回退

日志落在 ``staging/journal.json``，只记录"正在换目录"这一步。
"""
from __future__ import annotations

import json
import os
import shutil
import time

from . import trash
from .errors import OnlineError
from .hashing import target_of

TEMP_SUFFIX = ".pulses-new"
OLD_SUFFIX = ".pulses-old"


class Installer:
    """把 staging 里的内容安装到 root（预设目录或 TACZ 目录）。"""

    def __init__(self, root: str, staging_dir: str, *, log=None):
        self.root = os.path.abspath(root)
        self.staging_dir = os.path.abspath(staging_dir)
        self.journal_path = os.path.join(self.staging_dir, "journal.json")
        self.log = log

    # ------------------------------------------------------------------
    def _log(self, message: str, level: str = "INFO", **kwargs) -> None:
        if not self.log:
            return
        try:
            self.log(message, level, **kwargs)
            return
        except TypeError:
            pass
        try:
            self.log(message, level)
            return
        except TypeError:
            pass
        try:
            self.log(message)
        except Exception:
            pass

    # ---------- 日志 ----------
    def _read_journal(self) -> list[dict]:
        if not os.path.isfile(self.journal_path):
            return []
        try:
            with open(self.journal_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            ops = data.get("ops")
            return [op for op in ops if isinstance(op, dict)] \
                if isinstance(ops, list) else []
        except (OSError, ValueError):
            return []

    def _write_journal(self, ops: list[dict]) -> None:
        if not ops:
            try:
                os.unlink(self.journal_path)
            except OSError:
                pass
            return
        os.makedirs(os.path.dirname(self.journal_path), exist_ok=True)
        temp = self.journal_path + ".tmp"
        with open(temp, "w", encoding="utf-8") as fh:
            json.dump({"root": self.root, "ops": ops}, fh, ensure_ascii=False)
        os.replace(temp, self.journal_path)

    def _journal_add(self, op: dict) -> None:
        ops = [o for o in self._read_journal() if o.get("dest") != op.get("dest")]
        ops.append(op)
        self._write_journal(ops)

    def _journal_update(self, dest: str, **changes) -> None:
        ops = self._read_journal()
        for op in ops:
            if op.get("dest") == dest:
                op.update(changes)
        self._write_journal(ops)

    def _journal_drop(self, dest: str) -> None:
        ops = [o for o in self._read_journal() if o.get("dest") != dest]
        self._write_journal(ops)

    # ---------- 路径工具 ----------
    def _dest_of(self, entry: dict) -> str:
        if entry.get("type") == "folder":
            name = entry.get("target") or target_of(entry["path"])
            return os.path.join(self.root, name)
        return os.path.join(self.root, entry["path"])

    @staticmethod
    def _temp_beside(dest: str) -> str:
        parent = os.path.dirname(dest) or "."
        return os.path.join(parent, "." + os.path.basename(dest) + TEMP_SUFFIX)

    @staticmethod
    def _old_beside(dest: str) -> str:
        parent = os.path.dirname(dest) or "."
        return os.path.join(parent, "." + os.path.basename(dest) + OLD_SUFFIX)

    @staticmethod
    def _move(src: str, dest: str) -> None:
        """优先改名（同卷瞬时完成），跨卷才真复制。"""
        try:
            os.replace(src, dest)
            return
        except OSError:
            pass
        if os.path.isdir(src):
            shutil.copytree(src, dest, dirs_exist_ok=True)
            shutil.rmtree(src, ignore_errors=True)
        else:
            os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
            shutil.copy2(src, dest)
            os.unlink(src)

    @staticmethod
    def _remove(path: str) -> None:
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path, ignore_errors=True)
            elif os.path.exists(path):
                os.unlink(path)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # 崩溃恢复
    # ------------------------------------------------------------------
    def recover(self) -> list[str]:
        """按日志补完或回退上次中断的安装。返回处理记录。"""
        notes: list[str] = []
        ops = self._read_journal()
        for op in ops:
            dest = str(op.get("dest") or "")
            temp = str(op.get("temp") or "")
            old = str(op.get("old") or "")
            if not dest:
                continue
            if op.get("kind") == "dir":
                if temp and os.path.exists(temp):
                    if not os.path.exists(dest):
                        self._move(temp, dest)
                        notes.append(f"补完替换：{os.path.basename(dest)}")
                    else:
                        self._remove(temp)
                        notes.append(f"清理残留：{os.path.basename(dest)}")
                elif old and os.path.exists(old) and not os.path.exists(dest):
                    self._move(old, dest)
                    notes.append(f"回退替换：{os.path.basename(dest)}")
                if old and os.path.exists(old):
                    self._remove(old)
            else:
                if temp and os.path.exists(temp):
                    self._remove(temp)
                    notes.append(f"清理残留：{os.path.basename(dest)}")
        if ops:
            self._write_journal([])
        notes.extend(self._sweep_leftovers())
        return notes

    def _sweep_leftovers(self) -> list[str]:
        """扫掉根目录里上次没清干净的 .pulses-new / .pulses-old。"""
        notes: list[str] = []
        try:
            names = os.listdir(self.root)
        except OSError:
            return notes
        for name in names:
            if name.endswith(TEMP_SUFFIX) or name.endswith(OLD_SUFFIX):
                full = os.path.join(self.root, name)
                self._remove(full)
                notes.append(f"清理残留：{name}")
        return notes

    # ------------------------------------------------------------------
    # 安装
    # ------------------------------------------------------------------
    def install(self, entry: dict, staged_path: str) -> str:
        """把 staged_path 安装到目标位置，返回最终路径。"""
        if not os.path.exists(staged_path):
            raise OnlineError(f"暂存文件不见了：{entry.get('path')}")
        os.makedirs(self.root, exist_ok=True)
        dest = self._dest_of(entry)
        if entry.get("type") == "folder":
            self._install_dir(staged_path, dest, entry)
        else:
            self._install_file(staged_path, dest)
        return dest

    def _install_file(self, staged: str, dest: str) -> None:
        temp = self._temp_beside(dest)
        self._remove(temp)
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        self._journal_add({"kind": "file", "dest": dest, "temp": temp})
        self._move(staged, temp)
        os.replace(temp, dest)          # 同卷 → 原子；跨卷时 temp 已在同卷
        self._journal_drop(dest)

    def _install_dir(self, staged: str, dest: str, entry: dict) -> None:
        temp = self._temp_beside(dest)
        old = self._old_beside(dest)
        self._remove(temp)
        self._remove(old)
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        self._move(staged, temp)        # 先挪到目标同卷
        self._journal_add({"kind": "dir", "dest": dest, "temp": temp,
                           "old": old, "state": "ready",
                           "path": entry.get("path"), "at": time.time()})
        # 旧目录让位
        if os.path.exists(dest):
            self._journal_update(dest, state="swapping")
            try:
                os.replace(dest, old)
            except OSError:
                shutil.move(dest, old)
        # 新目录就位
        self._journal_update(dest, state="installing")
        try:
            os.replace(temp, dest)
        except OSError:
            shutil.move(temp, dest)
        self._journal_update(dest, state="cleanup")
        self._remove(old)
        self._journal_drop(dest)

    # ------------------------------------------------------------------
    # 删除本地多余
    # ------------------------------------------------------------------
    def remove_local(self, entry: dict) -> bool:
        """把本地多余的文件/文件夹送进回收站。"""
        path = self._dest_of(entry)
        if not os.path.exists(path):
            return True
        ok = trash.delete(path)
        self._log(f"{'已删除' if ok else '删除失败'}：{os.path.basename(path)}",
                  "INFO" if ok else "ERROR")
        return ok
