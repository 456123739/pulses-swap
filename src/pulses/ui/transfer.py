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
        # 进度回调来自工作线程：Tk 控件只能在主线程动
        if threading.current_thread() is not threading.main_thread():
            ui_call(self.root, self.show_progress, current, total, message)
            return
        self._inline_progress(current, total, message)
        if total > 0:
            pct = current / total
            self._animate_progress(pct)
            self.set_status(f"{message} ({current}/{total})", "busy",
                            progress=pct)
        else:
            self.set_status(message or "处理中…", "busy")
        self.root.update_idletasks()

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

    def _inline_progress(self, current, total, message=""):
        """主操作下面那条细进度：替换 / 同步都喂它。"""
        bar = getattr(self, "inline_progress", None)
        label = getattr(self, "inline_label", None)
        if bar is None:
            return
        ratio = (float(current) / float(total)) if total else 0.0
        ratio = max(0.0, min(1.0, ratio))
        try:
            if not bar.winfo_ismapped():
                bar.place(relx=0.0, rely=1.0, y=-16, relwidth=0.62, anchor="sw")
                if label is not None:
                    label.place(relx=1.0, rely=1.0, y=-20, anchor="se")
            bar.set(ratio)
            if label is not None:
                text = message or f"{current}/{total}"
                label.configure(text=text)
        except Exception:
            pass

    def hide_progress(self):
        for name in ("inline_progress", "inline_label"):
            widget = getattr(self, name, None)
            if widget is not None:
                try:
                    widget.place_forget()
                except Exception:
                    pass
        self._progress_value = 0.0
        try:
            self.progress_bar.pack_forget()
        except Exception:
            pass
        self.set_status("", "muted")
        try:
            self.root.update_idletasks()
        except Exception:
            pass

    def set_busy_state(self, busy, operation=""):
        def _set_state(name, state):
            widget = getattr(self, name, None)
            if widget is not None:
                try:
                    widget.configure(state=state)
                except Exception:
                    pass

        if busy:
            self.is_applying = True
            _set_state("publish_btn", "disabled")
            _set_state("sync_btn", "disabled")
            _set_state("apply_alt_btn", "disabled")
            self.apply_btn.configure(state="disabled", text=f"{operation}中...")
            self.create_preset_btn.configure(state="disabled")
            self.select_pack_btn.configure(state="disabled")
            self.save_version_btn.configure(state="disabled")
            self.preset_cards.set_enabled(False)
        else:
            self.is_applying = False
            self.apply_btn.configure(state="normal", text="一键替换")
            _set_state("publish_btn", "normal")
            _set_state("sync_btn", "normal")
            _set_state("apply_alt_btn", "normal")
            self.create_preset_btn.configure(state="normal")
            self.select_pack_btn.configure(state="normal")
            self.save_version_btn.configure(state="normal")
            self.preset_cards.set_enabled(True)
            name = getattr(self, "current_selected_preset", None)
            info = {}
            try:
                info = (self.preset_manager.presets.get(name) or {}) \
                    if (self.preset_manager and name) else {}
            except Exception:
                info = {}
            if not name:
                self.apply_btn.configure(state="disabled", text="一键替换")
            elif info.get("applied"):
                self.apply_btn.configure(state="disabled", text="已应用")
            else:
                self.apply_btn.configure(state="normal", text="一键替换")

    # ==================== 枪包列表 ====================
    def _sync_gunpack_empty(self):
        """枪包列表为空时显示空状态，别留一块空灰底。"""
        box = getattr(self, "gunpack_empty", None)
        if box is None:
            return
        try:
            empty = self.gunpack_listbox.size() == 0
            if empty:
                # 空状态文案跟随当前上下文，不能永远写“先选一个整合包”：
                # 已经选好预设时，用户需要的是“这个预设还没有枪包”。
                if not getattr(self, "current_pack_path", None):
                    title, hint = "还没有枪包", "先选择一个整合包"
                elif not getattr(self, "current_selected_preset", None):
                    title, hint = "还没有枪包", "先在左边选择一个预设"
                elif str(self.gunpack_count_label.cget("text")).startswith("读取"):
                    title, hint = "正在读取枪包…", ""
                else:
                    title, hint = "这个预设还没有枪包", "把 zip 或文件夹拖进来"
                try:
                    box.update_text(title, hint)
                except Exception:
                    pass
                self.gunpack_listbox.pack_forget()
                self.gunpack_scroll.pack_forget()
                if not box.winfo_ismapped():
                    box.pack(fill=BOTH, expand=True)
            else:
                box.pack_forget()
                if not self.gunpack_listbox.winfo_ismapped():
                    self.gunpack_listbox.pack(side=LEFT, fill=BOTH, expand=True,
                                              padx=(PAD_INNER, 0), pady=PAD_INNER)
                    self.gunpack_scroll.pack(side=RIGHT, fill=Y,
                                             padx=(2, PAD_XS), pady=PAD_INNER)
        except Exception:
            pass

    def refresh_gunpacks(self, use_cache: bool = False):
        """刷新枪包列表：读盘/比对放工作线程，主线程只做渲染。

        以前这里在主线程 os.walk + 读 fingerprint，TACZ 目录大时点一下
        预设会卡住整窗；现在先显示「读取中」，结果回来再一次性铺列表。
        """
        if (not self.preset_manager or not self.current_selected_preset
                or self.loading_presets):
            self.gunpack_listbox.delete(0, END)
            self.gunpack_count_label.configure(text="共 0 个枪包")
            self._sync_gunpack_empty()
            return
        preset_name = self.current_selected_preset
        if preset_name not in self.preset_manager.presets:
            self.gunpack_listbox.delete(0, END)
            self.gunpack_count_label.configure(text="共 0 个枪包")
            self._sync_gunpack_empty()
            return

        self.gunpack_listbox.delete(0, END)
        self.gunpack_count_label.configure(text="读取枪包…")
        self._sync_gunpack_empty()
        seq = int(getattr(self, "_gunpack_seq", 0)) + 1
        self._gunpack_seq = seq
        manager = self.preset_manager
        info = dict(manager.presets.get(preset_name) or {})
        indexed = dict(info.get("gunpacks") or {})
        applied = bool(info.get("applied"))

        def worker():
            try:
                current = manager.get_current_gunpacks_for_preset(
                    preset_name, use_cache=use_cache)
                if use_cache and not current:
                    current = manager.get_current_gunpacks_for_preset(
                        preset_name, use_cache=False)
                ui_call(self.root, self._render_gunpacks, seq, preset_name,
                        current, indexed, applied)
            except Exception as exc:                # noqa: BLE001
                ui_call(self.root, self._gunpacks_failed, seq, preset_name, exc)

        threading.Thread(target=worker, daemon=True).start()

    def _gunpacks_failed(self, seq, preset_name, error):
        if seq != getattr(self, "_gunpack_seq", 0) or \
                preset_name != self.current_selected_preset:
            return
        self.log_manager.log(f"读取枪包列表失败: {error}", 'ERROR')
        self.gunpack_listbox.delete(0, END)
        self.gunpack_count_label.configure(text="共 0 个枪包")
        self._sync_gunpack_empty()

    def _render_gunpacks(self, seq, preset_name, current, indexed, applied):
        if seq != getattr(self, "_gunpack_seq", 0):
            return
        if (preset_name != self.current_selected_preset
                or not self.preset_manager):
            return
        if current:
            conv = {}
            for n, v in current.items():
                if isinstance(v, list):
                    conv[n] = {'type': 'zip', 'size': 0, 'file_count': 1}
                else:
                    conv[n] = v
            current = conv
        if indexed:
            conv = {}
            for n, v in indexed.items():
                if isinstance(v, list):
                    conv[n] = {'type': 'zip', 'size': 0, 'file_count': 1}
                else:
                    conv[n] = v
            indexed = conv

        self.gunpack_listbox.delete(0, END)
        if not current and not indexed:
            self.gunpack_count_label.configure(text="共 0 个枪包")
            self._sync_gunpack_empty()
            return

        def kind_of(name: str) -> str:
            fp = current.get(name) or indexed.get(name) or {}
            return str(fp.get("type") or "zip")

        def label_of(name: str) -> str:
            return f"{name}（文件夹）" if kind_of(name) == "folder" else name

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

        location = "Tacz文件夹" if applied else "预设文件夹"
        total = len(missing) + len(extra) + len(modified) + len(normal)

        for name in missing:
            self.gunpack_listbox.insert(END, f"× {label_of(name)}")
            i = self.gunpack_listbox.size() - 1
            self.gunpack_listbox.itemconfig(
                i, fg=C_STATUS_MISSING, bg=C_STATUS_MISSING_BG)
        for name in extra:
            self.gunpack_listbox.insert(END, f"⊙ {label_of(name)}")
            i = self.gunpack_listbox.size() - 1
            self.gunpack_listbox.itemconfig(
                i, fg=C_STATUS_EXTRA, bg=C_STATUS_EXTRA_BG)
        for name in modified:
            self.gunpack_listbox.insert(END, f"~ {label_of(name)}")
            i = self.gunpack_listbox.size() - 1
            self.gunpack_listbox.itemconfig(
                i, fg=C_STATUS_MODIFIED, bg=C_STATUS_MODIFIED_BG)
        for name in normal:
            self.gunpack_listbox.insert(END, f"✓ {label_of(name)}")
            i = self.gunpack_listbox.size() - 1
            self.gunpack_listbox.itemconfig(
                i, fg=C_STATUS_NORMAL, bg=C_STATUS_NORMAL_BG)

        folders = sum(1 for n in list(cur_names | idx_names)
                      if kind_of(n) == "folder")
        zips = total - folders
        mix = f"{zips} zip · {folders} 文件夹" if folders else f"{zips} zip"
        if missing or extra or modified:
            self.gunpack_count_label.configure(
                text=f"共 {total} 个（{mix}） 正常:{len(normal)} "
                     f"缺失:{len(missing)} 多余:{len(extra)} 变更:{len(modified)}")
        else:
            self.gunpack_count_label.configure(
                text=f"共 {total} 个（{mix}）· 来自 {location}")
        self._sync_gunpack_empty()

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
            self.log_manager.log(
                f"预设 '{preset_name}' 所有枪包校验通过（共 {total} 个）",
                'SUCCESS')

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
        self.set_status("准备替换...", "busy", progress=0.0)

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
            # 应用完把预设计数/指纹按 tacz 现状重算一遍：否则预设目录已经空了，
            # 索引还停在 0 个枪包，下次启动会误报「检测到新增 3 个」。
            try:
                if (self.preset_manager and self.preset_manager.current_preset):
                    self.preset_manager.update_preset_index(
                        self.preset_manager.current_preset, from_tacz=True)
            except Exception:
                pass
            self._update_preset_list()
            self.refresh_gunpacks(use_cache=False)
            if self.preset_manager and self.preset_manager.current_preset:
                applied = self.preset_manager.current_preset
                self.preset_cards.select(applied, notify=False)
                self.on_preset_selected(applied)
            # 应用把预设目录搬进了 tacz：之前的云端计划是按旧位置算的，
            # 不复查一次，卡片会挂着「有 N 个更新」这种幽灵状态。
            try:
                name_now = (self.preset_manager.current_preset
                            if self.preset_manager else None)
                if name_now and self.online is not None and (
                        self.online.is_bound(name_now)
                        or (self.is_developer
                            and self.online.cloud_path_of(name_now))):
                    self._online_check(name_now)
            except Exception:
                pass
            self.log_manager.log("预设应用成功！", 'SUCCESS')
            self.set_status("预设已应用", "success")
        else:
            # 失败时 apply_preset 会把 applied 标记回滚：界面也必须跟着回到
            # 「未应用」，否则卡片还挂着「已应用」，用户以为换成功了。
            try:
                self._update_preset_list()
                if self.current_selected_preset:
                    self.on_preset_selected(self.current_selected_preset)
            except Exception:
                pass
            self.set_status("预设应用失败", "error")
            show_error("错误", "预设应用失败，请查看日志")
        self._start_watcher()
        self._update_guide()
