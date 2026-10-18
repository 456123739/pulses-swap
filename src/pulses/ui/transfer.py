"""导出 / 导入 / 进度 / 枪包列表 / 应用"""
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


class TransferMixin:
    """导出 / 导入 / 进度 / 枪包列表 / 应用"""

    # ==================== 导出 ====================
    def show_progress(self, current, total, message=""):
        if total > 0:
            pct = current / total
            ui_call(self.root, lambda: self._animate_progress(pct))
            ui_call(self.root, lambda: self.progress_label.configure(
                text=f"{message} ({current}/{total})"))
        ui_call(self.root, lambda: self.root.update_idletasks())

    def _animate_progress(self, target):
        """进度条曲线推进，避免长任务里一格一格地跳。"""
        start = float(getattr(self, "_progress_value", 0.0))
        if abs(target - start) < 0.0005:
            return

        def frame(e, raw):
            self._progress_value = lerp(start, target, e)
            try:
                self.progress_bar.set(self._progress_value)
            except Exception:
                pass

        frame(0.0, 0.0)
        tween(self.progress_bar, "value", 170, frame, easing=ease_out_cubic)

    def hide_progress(self):
        ui_call(self.root, lambda: self.progress_bar.pack_forget())
        ui_call(self.root, lambda: self.progress_label.pack_forget())
        ui_call(self.root, lambda: setattr(self, "_progress_value", 0.0))
        ui_call(self.root, lambda: self.root.update_idletasks())

    def set_busy_state(self, busy, operation=""):
        if busy:
            self.is_applying = True
            self.apply_btn.configure(state="disabled", text=f"{operation}中...")
            self.create_preset_btn.configure(state="disabled")
            self.select_pack_btn.configure(state="disabled")
            self.save_version_btn.configure(state="disabled")
            self.preset_cards.set_enabled(False)
        else:
            self.is_applying = False
            self.apply_btn.configure(state="normal", text="一键替换")
            self.create_preset_btn.configure(state="normal")
            self.select_pack_btn.configure(state="normal")
            self.save_version_btn.configure(state="normal")
            self.preset_cards.set_enabled(True)
            if not self.current_selected_preset:
                self.apply_btn.configure(state="disabled")

    # ==================== 枪包列表 ====================
    def refresh_gunpacks(self, use_cache: bool = False):
        if not self.preset_manager or not self.current_selected_preset or self.loading_presets:
            self.gunpack_listbox.delete(0, END)
            self.gunpack_count_label.configure(text="共 0 个枪包")
            return
        preset_name = self.current_selected_preset
        if preset_name not in self.preset_manager.presets:
            self.gunpack_listbox.delete(0, END)
            self.gunpack_count_label.configure(text="共 0 个枪包")
            return

        self.gunpack_listbox.delete(0, END)
        info = self.preset_manager.presets[preset_name]

        current = self.preset_manager.get_current_gunpacks_for_preset(
            preset_name, use_cache=use_cache)
        if use_cache and not current:
            current = self.preset_manager.get_current_gunpacks_for_preset(
                preset_name, use_cache=False)

        if current:
            conv = {}
            for n, v in current.items():
                if isinstance(v, list):
                    conv[n] = {'type': 'zip', 'size': 0, 'file_count': 1}
                else:
                    conv[n] = v
            current = conv

        indexed = info.get('gunpacks', {})
        if indexed:
            conv = {}
            for n, v in indexed.items():
                if isinstance(v, list):
                    conv[n] = {'type': 'zip', 'size': 0, 'file_count': 1}
                else:
                    conv[n] = v
            indexed = conv

        if not current and not indexed:
            self.gunpack_listbox.insert(END, "(此预设暂无枪包)")
            self.gunpack_listbox.itemconfig(0, fg=C_STATUS_EMPTY)
            self.gunpack_count_label.configure(text="共 0 个枪包")
            return

        cur_names = set(current.keys())
        idx_names = set(indexed.keys())
        missing = sorted(idx_names - cur_names)
        extra = sorted(cur_names - idx_names)
        modified = []
        normal = []
        for n in sorted(cur_names & idx_names):
            if not fingerprints_match(current[n], indexed[n]):
                modified.append(n)
            else:
                normal.append(n)

        location = "Tacz文件夹" if info.get('applied', False) else "预设文件夹"
        total = len(missing) + len(extra) + len(modified) + len(normal)

        for name in missing:
            self.gunpack_listbox.insert(END, f"× {name}")
            i = self.gunpack_listbox.size() - 1
            self.gunpack_listbox.itemconfig(i, fg=C_STATUS_MISSING, bg=C_STATUS_MISSING_BG)

        for name in extra:
            self.gunpack_listbox.insert(END, f"⊙ {name}")
            i = self.gunpack_listbox.size() - 1
            self.gunpack_listbox.itemconfig(i, fg=C_STATUS_EXTRA, bg=C_STATUS_EXTRA_BG)

        for name in modified:
            self.gunpack_listbox.insert(END, f"~ {name}")
            i = self.gunpack_listbox.size() - 1
            self.gunpack_listbox.itemconfig(i, fg=C_STATUS_MODIFIED, bg=C_STATUS_MODIFIED_BG)

        for name in normal:
            self.gunpack_listbox.insert(END, f"✓ {name}")
            i = self.gunpack_listbox.size() - 1
            self.gunpack_listbox.itemconfig(i, fg=C_STATUS_NORMAL, bg=C_STATUS_NORMAL_BG)

        if missing or extra or modified:
            self.gunpack_count_label.configure(
                text=f"共 {total} 个枪包 (正常:{len(normal)} "
                     f"缺失:{len(missing)} 多余:{len(extra)} 变更:{len(modified)})")
        else:
            self.gunpack_count_label.configure(
                text=f"共 {total} 个枪包 (来自 {location})")

        if missing or extra or modified:
            lines = [f"预设 '{preset_name}' 校验结果 (从{location}读取):"]
            if normal:
                pv = ', '.join(normal[:5]) + (" ..." if len(normal) > 5 else "")
                lines.append(f"  ✓ 正常: {len(normal)} 个 ({pv})")
            if missing:
                pv = ', '.join(missing[:5]) + (" ..." if len(missing) > 5 else "")
                lines.append(f"  × 缺失: {len(missing)} 个 ({pv})")
            if extra:
                pv = ', '.join(extra[:5]) + (" ..." if len(extra) > 5 else "")
                lines.append(f"  ⊙ 多余: {len(extra)} 个 ({pv})")
            if modified:
                pv = ', '.join(modified[:5]) + (" ..." if len(modified) > 5 else "")
                lines.append(f"  ~ 变更: {len(modified)} 个 ({pv})")
            self.log_manager.log("\n".join(lines), 'WARNING')
        else:
            self.log_manager.log(f"预设 '{preset_name}' 所有枪包校验通过（共 {total} 个）", 'SUCCESS')

    # ==================== 预设应用 ====================
    def apply_preset(self):
        if not self.preset_manager or not self.tacz_path or self.loading_presets:
            return
        if self.is_applying:
            show_warning("操作进行中", "请等待当前操作完成")
            return
        if not self.current_selected_preset:
            show_warning("提示", "请先选择一个预设")
            return
        name = self.current_selected_preset
        if name not in self.preset_manager.presets:
            return
        if self.preset_manager.presets[name].get('applied', False):
            show_info("提示", f"预设 '{name}' 已经应用")
            return
        if not ask_yes_no("确认替换",
                f"确定要应用预设 '{name}' 吗？\n\n这将替换Tacz文件夹中的所有枪包！"):
            return

        self._stop_watcher()
        self.set_busy_state(True, "替换")
        self.progress_bar.pack(fill=X, pady=(0, 4))
        self.progress_label.pack(fill=X, pady=(0, 4))
        self.progress_bar.set(0)
        self.progress_label.configure(text="准备替换...")

        def cb(c, t, m):
            self.show_progress(c, t, m)

        def worker():
            try:
                result = self.preset_manager.apply_preset(name, cb)
                ui_call(self.root, self._on_apply_finished, result)
            except Exception as e:
                self.log_manager.log(f"错误: {e}", 'ERROR')
                ui_call(self.root, self._on_apply_finished, False)
        threading.Thread(target=worker, daemon=True).start()

    def _on_apply_finished(self, success):
        self.hide_progress()
        self.set_busy_state(False, "")
        if success:
            self._update_preset_list()
            self.refresh_gunpacks(use_cache=False)
            if self.preset_manager and self.preset_manager.current_preset:
                applied = self.preset_manager.current_preset
                self.preset_cards.select(applied, notify=False)
                self.on_preset_selected(applied)
            self.log_manager.log("预设应用成功！", 'SUCCESS')
        else:
            show_error("错误", "预设应用失败，请查看日志")
        self._start_watcher()
        self._update_guide()
