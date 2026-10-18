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
    def export_preset(self):
        if not self.preset_manager or not self.current_selected_preset or self.loading_presets:
            show_warning("提示", "请先选择一个预设")
            return
        if self.is_applying:
            show_warning("操作进行中", "请等待当前操作完成")
            return

        name = self.current_selected_preset
        info = self.preset_manager.presets.get(name)
        if not info:
            return

        if name == "default":
            show_warning("无法导出",
                "不允许导出名为 'default' 的预设。\n\n"
                "请先通过右键菜单「重命名」将该预设改为其他名称，再执行导出。")
            return

        version = info.get('version', 'v1.0.0')
        default_fn = generate_export_filename(name, version, False)
        p = filedialog.asksaveasfilename(
            title="导出完整预设包", initialfile=default_fn,
            defaultextension=".fgcpack",
            filetypes=[("Pulses Swap 完整包", "*.fgcpack")])
        if not p:
            return
        export_path = Path(p)

        self.set_busy_state(True, "导出")
        self.progress_bar.pack(fill=X, pady=(0, 4))
        self.progress_label.pack(fill=X, pady=(0, 4))
        self.progress_bar.set(0)
        self.progress_label.configure(text="准备导出...")

        def worker():
            def cb(c, t, m):
                self.show_progress(c, t, m)
            try:
                ok = self.preset_manager.export_preset(name, export_path, cb)
                ui_call(self.root, self._on_export_finished, ok, export_path)
            except Exception as e:
                self.log_manager.log(f"导出错误: {e}", 'ERROR')
                ui_call(self.root, self._on_export_finished, False, export_path)
        threading.Thread(target=worker, daemon=True).start()

    def export_incremental(self):
        if not self.preset_manager or not self.current_selected_preset or self.loading_presets:
            show_warning("提示", "请先选择一个预设")
            return
        if self.is_applying:
            show_warning("操作进行中", "请等待当前操作完成")
            return
        name = self.current_selected_preset
        info = self.preset_manager.presets.get(name)
        if not info:
            return
        if not info.get('applied', False):
            show_warning("提示", "只能对已应用的预设导出增量更新")
            return
        changes = self.preset_manager.detect_changes(name)
        total = len(changes['added']) + len(changes['removed']) + len(changes['modified'])
        if total == 0:
            show_info("提示", "未检测到任何变更，无需导出")
            return
        if not ask_yes_no("确认导出增量包",
            f"检测到以下变更:\n\n"
            f"新增: {len(changes['added'])} 个\n"
            f"移除: {len(changes['removed'])} 个\n"
            f"修改: {len(changes['modified'])} 个\n\n"
            f"是否导出增量更新包？\n\n"
            f"注意：导出后将自动同步校验数据。"):
            return
        pack_name = self.current_pack_path.name if self.current_pack_path else "Unknown"
        version = info.get('version', 'v1.0.0')
        next_inc = info.get('incremental_count', 0) + 1
        default_fn = generate_export_filename(pack_name, version, True, next_inc)
        p = filedialog.asksaveasfilename(
            title="导出增量更新包", initialfile=default_fn,
            defaultextension=".fgcupdate",
            filetypes=[("Pulses Swap 增量更新包", "*.fgcupdate")])
        if not p:
            return
        export_path = Path(p)
        self.set_busy_state(True, "导出更新")
        self.progress_bar.pack(fill=X, pady=(0, 4))
        self.progress_label.pack(fill=X, pady=(0, 4))
        self.progress_bar.set(0)
        self.progress_label.configure(text="准备导出...")

        def worker():
            def cb(c, t, m):
                self.show_progress(c, t, m)
            try:
                ok = self.preset_manager.export_incremental(name, export_path, cb)
                ui_call(self.root, self._on_export_inc_finished, ok, export_path)
            except Exception as e:
                self.log_manager.log(f"导出增量包错误: {e}", 'ERROR')
                ui_call(self.root, self._on_export_inc_finished, False, export_path)
        threading.Thread(target=worker, daemon=True).start()

    def _on_export_finished(self, success, export_path):
        self.hide_progress()
        self.set_busy_state(False, "")
        if success:
            show_info("导出成功", f"预设已导出到:\n{export_path}")
        else:
            show_error("导出失败", "预设导出失败，请查看日志")
        self._update_preset_list()

    def _on_export_inc_finished(self, success, export_path):
        self.hide_progress()
        self.set_busy_state(False, "")
        if success:
            show_info("导出成功",
                f"增量更新包已导出到:\n{export_path}\n\n"
                f"校验数据已自动同步为最新")
        else:
            show_error("导出失败", "增量包导出失败，请查看日志")
        self._update_preset_list()
        self.refresh_gunpacks(use_cache=False)

    # ==================== 导入 ====================
    def do_import_preset(self, import_path: Path):
        self.set_busy_state(True, "导入")
        self.progress_bar.pack(fill=X, pady=(0, 4))
        self.progress_label.pack(fill=X, pady=(0, 4))
        self.progress_bar.set(0)
        self.progress_label.configure(text="准备导入...")

        def worker():
            def cb(c, t, m):
                self.show_progress(c, t, m)
            try:
                ok = self.preset_manager.import_preset(import_path, cb)
                ui_call(self.root, self._on_import_finished, ok, import_path)
            except Exception as e:
                self.log_manager.log(f"导入错误: {e}", 'ERROR')
                ui_call(self.root, self._on_import_finished, False, import_path)
        threading.Thread(target=worker, daemon=True).start()

    def do_import_incremental(self, import_path: Path):
        self.set_busy_state(True, "导入更新")
        self.progress_bar.pack(fill=X, pady=(0, 4))
        self.progress_label.pack(fill=X, pady=(0, 4))
        self.progress_bar.set(0)
        self.progress_label.configure(text="准备导入...")

        def worker():
            try:
                ok = self.preset_manager.import_incremental(import_path)
                ui_call(self.root, self._on_import_inc_finished, ok, import_path)
            except Exception as e:
                self.log_manager.log(f"导入增量包错误: {e}", 'ERROR')
                ui_call(self.root, self._on_import_inc_finished, False, import_path)
        threading.Thread(target=worker, daemon=True).start()

    def _on_import_finished(self, success, import_path: Path):
        self.hide_progress()
        self.set_busy_state(False, "")
        if not success:
            show_error("导入失败", "预设导入失败，请查看日志")
            return
        self._update_preset_list()
        self.refresh_gunpacks(use_cache=False)
        self._update_guide()
        self._ask_delete_source_package(import_path, "预设导入成功！")

    def _on_import_inc_finished(self, success, import_path: Path):
        self.hide_progress()
        self.set_busy_state(False, "")
        if not success:
            show_error("更新失败", "增量更新失败，请查看日志")
            return
        self.refresh_gunpacks(use_cache=False)
        self._update_preset_list()
        self._update_guide()
        self._ask_delete_source_package(import_path, "增量更新已成功应用！")

    def _ask_delete_source_package(self, import_path: Path, success_msg: str):
        try:
            if not import_path.exists():
                show_info("导入完成", success_msg)
                return
            try:
                size_str = format_size(import_path.stat().st_size)
            except Exception:
                size_str = "未知"
            reply = ask_yes_no(
                "导入完成",
                f"{success_msg}\n\n"
                f"是否删除源压缩包以节省存储空间？\n\n"
                f"文件: {import_path.name}\n"
                f"大小: {size_str}\n"
                f"位置: {import_path.parent}\n\n"
                f"（会移入回收站，可随时找回）")
            if not reply:
                return
            if move_to_recycle_bin(import_path):
                self.log_manager.log(
                    f"已将源压缩包移至回收站: {import_path.name}", 'SUCCESS')
                return
            try:
                import_path.unlink()
                self.log_manager.log(
                    f"已删除源压缩包（无法移入回收站）: {import_path.name}", 'SUCCESS')
            except Exception as e:
                self.log_manager.log(f"删除源压缩包失败: {e}", 'WARNING')
                show_warning("警告",
                    f"删除源压缩包失败，请手动处理。\n\n错误: {e}")
        except Exception as e:
            self.log_manager.log(f"处理源压缩包时出错: {e}", 'WARNING')
            show_info("导入完成", success_msg)

    # ==================== 进度条 ====================
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
            self.export_preset_btn.configure(state="disabled")
            self.export_incremental_btn.configure(state="disabled")
            self.create_preset_btn.configure(state="disabled")
            self.refresh_preset_btn.configure(state="disabled")
            self.refresh_gunpack_btn.configure(state="disabled")
            self.select_pack_btn.configure(state="disabled")
            self.open_pack_btn.configure(state="disabled")
            self.open_tacz_btn.configure(state="disabled")
            self.save_version_btn.configure(state="disabled")
            self.open_db_btn.configure(state="disabled")
            self.close_pack_btn.configure(state="disabled")
            self.preset_listbox.config(state=DISABLED)
        else:
            self.is_applying = False
            self.apply_btn.configure(state="normal", text="Step 4 · 一键替换")
            self.export_preset_btn.configure(state="normal")
            self.create_preset_btn.configure(state="normal")
            self.refresh_preset_btn.configure(state="normal")
            self.refresh_gunpack_btn.configure(state="normal")
            self.select_pack_btn.configure(state="normal")
            self.save_version_btn.configure(state="normal")
            self.open_db_btn.configure(state="normal")
            self.close_pack_btn.configure(state="normal")
            if self.current_pack_path:
                self.open_pack_btn.configure(state="normal")
                self.open_tacz_btn.configure(state="normal")
            self.preset_listbox.config(state=NORMAL)
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
            self.log_manager.log(f"预设 '{preset_name}' 所有枪包校验通过 ✓ (共 {total} 个)", 'SUCCESS')

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
                for i in range(self.preset_listbox.size()):
                    if (preset_name_of(self.preset_listbox.get(i))
                            == self.preset_manager.current_preset):
                        self.preset_listbox.selection_set(i)
                        self.on_preset_selected(None)
                        break
            self.log_manager.log("预设应用成功！", 'SUCCESS')
        else:
            show_error("错误", "预设应用失败，请查看日志")
        self._start_watcher()
        self._update_guide()
