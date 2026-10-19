"""整合包与预设管理 / TACZ 监控"""
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


class PacksMixin:
    """整合包与预设管理 / TACZ 监控"""

    # ==================== 整合包管理 ====================
    def select_pack(self):
        if getattr(self, "online_busy", False) or getattr(self, "is_applying", False):
            show_warning("操作进行中", "正在同步/发布，等完成后再切换整合包。")
            return
        if not self.db_ready:
            show_warning("提示", "数据库未初始化，请重启程序")
            return
        if self.is_applying:
            show_warning("操作进行中", "请等待当前操作完成")
            return
        if self.loading_presets:
            show_info("加载中", "预设列表正在加载，请稍候...")
            return
        folder = filedialog.askdirectory(title="选择整合包根目录")
        if not folder:
            return
        self.load_pack(Path(folder))

    def load_pack(self, pack_path: Path):
        if not self.db_ready:
            show_warning("提示", "数据库未初始化")
            return
        tacz_path = pack_path / 'tacz'
        if not tacz_path.exists() or not tacz_path.is_dir():
            show_error("错误", "未找到tacz文件夹，请选择正确的整合包根目录")
            return

        legacy_dirs = LegacyDatabaseMigrator.find_legacy_databases(pack_path)
        if legacy_dirs:
            if ask_yes_no("检测到旧版数据库",
                f"在整合包中发现旧版数据库:\n{legacy_dirs[0]}\n\n"
                f"是否适配到当前数据库？\n"
                f"（可选择迁移后标记或删除原库）"):
                self.root.after(200, lambda p=legacy_dirs[0]:
                                 self.migrate_legacy_database(p))

        self.current_pack_path = pack_path
        self.tacz_path = tacz_path

        if getattr(self, "recent_visible", False):
            try:
                self.hide_recent()
            except Exception:
                pass

        pack_db_path = self.settings.get_db_path(pack_path)
        pack_db_path.mkdir(parents=True, exist_ok=True)

        self.pack_path_label.configure(text=str(pack_path), text_color=C_SUCCESS)
        self.pack_status_label.configure(text="已加载", text_color=C_SUCCESS)
        self._update_sidebar_status()
        self.pack_name_label.configure(text="当前预设：无", text_color=C_ACCENT)
        self._sync_tacz_shortcut()

        self.preset_manager = PresetManager(pack_db_path, self.log_manager,
                                             tacz_path, pack_name=pack_path.name)
        # 在线状态跟着这个整合包的数据库走（隐藏目录 .online）
        self._init_online(pack_db_path)
        if self.recent_manager:
            self.recent_manager.add(str(pack_path), pack_path.name)
            if self.recent_visible:
                self.update_recent_list()

        has_presets = any(p.is_dir() for p in pack_db_path.iterdir()
                          if not p.name.startswith('.'))
        if not has_presets:
            self._create_default_preset()

        self._start_watcher()

        self.loading_presets = True
        self._start_loading_dots("加载中")
        self._disable_buttons(True)
        self.preset_cards.set_loading(True)
        threading.Thread(target=self._load_presets_thread, daemon=True).start()

    def _load_presets_thread(self):
        try:
            self.preset_manager.load_all_presets(use_cache=True)
        except Exception as e:
            safe_print("加载预设线程出错:", traceback.format_exc())
            self.log_manager.log(f"加载预设失败: {e}", 'ERROR')
        finally:
            # 无论成功失败都要回到主线程收尾（否则按钮会一直锁着）
            ui_call(self.root, self._on_presets_loaded)

    def _on_presets_loaded(self):
        # 兜底放在最前面：只要回调跑到，界面就绝不能留在「按钮全禁用」的状态。
        # 之前加载线程一旦出错，_disable_buttons(True) 就再也解不开，
        # 表现就是「所有按钮按下去都没反应」。
        self.loading_presets = False
        self._stop_loading_dots()
        self._disable_buttons(False)
        self._set_pack_dependent_buttons(True)
        try:
            self._on_presets_loaded_body()
        except Exception as exc:
            safe_print("预设加载完成回调出错:", traceback.format_exc())
            self.log_manager.log(f"预设加载完成回调出错: {exc}", 'ERROR')

    def _on_presets_loaded_body(self):
        self._update_preset_list()
        # 单行日志模式下这条就是「加载完成」的主信息（细节条目见完整日志）
        pack_name = (self.current_pack_path.name
                     if self.current_pack_path else "整合包")
        self.log_manager.log(
            f"整合包已就绪: {pack_name} · 预设 {len(self.preset_manager.presets)} 个",
            'SUCCESS')
        if self.preset_manager.current_preset:
            self._check_applied_changes(self.preset_manager.current_preset)
        if self.preset_manager.presets:
            first = None
            for name, info in self.preset_manager.presets.items():
                if info.get('applied', False):
                    first = name
                    break
            if not first:
                first = list(self.preset_manager.presets.keys())[0]
            if first:
                self.preset_cards.select(first)
                self.on_preset_selected(first)
        self._update_guide()
        # 预设就绪后再做在线检查，别和加载抢 IO
        self.root.after(600, self._online_auto_check)

    def _disable_buttons(self, disabled: bool):
        state = "disabled" if disabled else "normal"
        try:
            self.create_preset_btn.configure(state=state)
            self.save_version_btn.configure(state=state)
            self.apply_btn.configure(state=state)
            self.select_pack_btn.configure(state=state)
            self.add_cloud_btn.configure(state=state)
            self.publish_btn.configure(state=state)
        except Exception:
            pass

    def _set_pack_dependent_buttons(self, enabled: bool) -> None:
        """只开关「依赖已加载整合包」的按钮。

        与「选择整合包 / 打开数据库」区分开：后两者任何时候都要可用，
        否则关掉一个包就再也选不了下一个。
        """
        state = "normal" if enabled else "disabled"
        for name in ("apply_btn", "publish_btn", "create_preset_btn",
                     "add_cloud_btn", "save_version_btn"):
            btn = getattr(self, name, None)
            if btn is not None:
                try:
                    btn.configure(state=state)
                except Exception:
                    pass

    # ==================== 加载指示动画 ====================
    def _start_loading_dots(self, prefix="刷新中"):
        """加载文字脉冲：小圆点逐帧增长（关掉动画时自动降级为静态一次到位）。"""
        def frame(e, raw):
            dots = "." * min(3, int(raw * 4))
            try:
                self.loading_label.configure(text=f"{prefix}{dots}")
            except Exception:
                pass

        frame(0.0, 0.0)
        if config.ANIMATIONS_ENABLED:
            tween(self.loading_label, "dots", 560, frame,
                  on_done=lambda: self._start_loading_dots(prefix),
                  easing=ease_linear)
        else:
            try:
                self.loading_label.configure(text=f"{prefix}…")
            except Exception:
                pass

    def _stop_loading_dots(self):
        cancel_tween(self.loading_label, "dots")
        try:
            self.loading_label.configure(text="")
        except Exception:
            pass

    def _animate_label_color(self, label, start, target, duration=190):
        """文字颜色过渡：状态/标题更新时不做生硬的瞬间换色。"""
        def frame(e, raw):
            try:
                label.configure(text_color=lerp_color(start, target, e))
            except Exception:
                pass

        frame(0.0, 0.0)
        tween(label, "color", duration, frame, easing=ease_out_cubic,
              fps=FPS_COLOR)

    def _create_default_preset(self):
        if not self.preset_manager:
            return
        if "default" in self.preset_manager.presets:
            return
        if self.preset_manager.create_preset("default", "v1.0.0"):
            gunpacks = self.preset_manager._get_gunpacks_from_folder(self.tacz_path)
            self.preset_manager.presets["default"]['gunpacks'] = gunpacks
            self.preset_manager.presets["default"]['applied'] = True
            self.preset_manager.current_preset = "default"
            index_data = {'name': "default", 'version': "v1.0.0",
                          'gunpacks': gunpacks, 'applied': True,
                          'incremental_count': 0}
            dp = Path(self.preset_manager.presets["default"]['path'])
            with open(dp / 'index.json', 'w', encoding='utf-8') as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)
            self.preset_manager.save_cache()
            self.pack_name_label.configure(text="当前预设：default")
            self.log_manager.log("默认预设创建成功", 'SUCCESS')

    def close_pack(self):
        if getattr(self, "online_busy", False):
            show_warning("操作进行中", "正在同步/发布，等完成后再关闭整合包。")
            return
        if self.is_applying:
            show_warning("操作进行中", "请等待当前操作完成")
            return
        if self.loading_presets:
            show_info("加载中", "预设列表正在加载，请稍候...")
            return
        self._stop_watcher()
        self._shutdown_online()
        self.current_pack_path = None
        self.tacz_path = None
        self.preset_manager = None
        self.current_selected_preset = None
        self.pack_path_label.configure(text="未选择", text_color=C_TEXT_SECONDARY)
        self.pack_status_label.configure(text="未加载", text_color=C_ERROR)
        self.pack_name_label.configure(text="当前预设：无", text_color=C_ACCENT)
        self.preset_cards.set_items([])
        self.gunpack_listbox.delete(0, END)
        self.preset_name_label.configure(text="未选择")
        self.preset_version_label.configure(text="无")
        self.preset_status_label.configure(text="未应用")
        self.preset_online_label.configure(text="未绑定",
                                           text_color=C_TEXT_MUTED)
        self.gunpack_count_label.configure(text="共 0 个枪包")
        self.version_entry.delete(0, END)
        try:
            self.source_btn.configure(text="填写链接")
            self.sync_btn.pack_forget()
            self.aux_row.grid_remove()
            self.apply_btn.configure(text="一键替换")
        except Exception:
            pass
        # 关闭后只有「整合包相关」的按钮该灰掉；「选择整合包 / 数据库」必须
        # 保持可用 —— 之前这里调了 _disable_buttons(True) 把包括「选择」在内
        # 的所有按钮全禁掉，之后没有任何地方再解开，关掉一个包就再也选不了
        # 下一个（用户反馈「选择是灰的」）。
        self._disable_buttons(False)
        self._set_pack_dependent_buttons(False)
        try:
            self._apply_role_actions()
        except Exception:
            pass
        self.log_manager.log("已关闭整合包", 'INFO', verbose=True)
        self._update_sidebar_status()
        self._update_guide()

    # ==================== TACZ 监控 ====================
    def _start_watcher(self):
        self._stop_watcher()
        if not HAS_WATCHDOG:
            self.log_manager.log(
                "未安装 watchdog，文件变更检测依赖手动刷新\n"
                "安装方法: pip install watchdog", 'WARNING')
            return
        if not self.tacz_path or not self.tacz_path.exists():
            return
        self.tacz_watcher = TaczWatcher(self.tacz_path,
                                         on_change_callback=self._on_tacz_changed,
                                         log_manager=self.log_manager)
        self.tacz_watcher.start()

    def _stop_watcher(self):
        if self.tacz_watcher:
            try:
                self.tacz_watcher.stop()
            except Exception:
                pass
            self.tacz_watcher = None

    def _on_tacz_changed(self):
        try:
            ui_call(self.root, self._do_tacz_refresh)
        except Exception:
            pass

    def _do_tacz_refresh(self):
        if self.is_applying or self.loading_presets:
            return
        if not self.preset_manager or not self.current_selected_preset:
            return
        info = self.preset_manager.presets.get(self.current_selected_preset)
        if not info or not info.get('applied', False):
            return
        self.refresh_gunpacks(use_cache=False)

    # ==================== 预设管理 ====================
    def _update_sidebar_status(self):
        """侧边栏底部状态卡：镜像 Step1/Step2 的状态，避免侧边栏下半部空着。"""
        try:
            self.sb_pack_label.configure(
                text=(self.current_pack_path.name if self.current_pack_path
                      else "未选择"))
        except Exception:
            pass
        # 状态那行直接镜像；预设那行保留「预设 · 」标签 —— 去掉前缀可读性反而丢了
        try:
            self.sb_status_label.configure(
                text=str(self.pack_status_label.cget("text")),
                text_color=self.pack_status_label.cget("text_color"))
        except Exception:
            pass
        try:
            text = str(self.pack_name_label.cget("text"))
            for cand in ("当前预设：", "当前预设: "):
                if text.startswith(cand):
                    text = text[len(cand):]
                    break
            self.sb_preset_label.configure(text=f"预设 · {text}",
                                            text_color=C_ACCENT)
        except Exception:
            pass

    def _update_preset_list(self):
        if not self.preset_manager:
            return
        if hasattr(self, "_preset_size_cache"):
            self._preset_size_cache.clear()
        self.preset_cards.set_loading(False)
        self._refresh_preset_cards()
        if self.preset_manager.current_preset:
            self.pack_name_label.configure(
                text=f"当前预设：{self.preset_manager.current_preset}")
        else:
            self.pack_name_label.configure(text="当前预设：无")
        if self.current_selected_preset:
            self.preset_cards.select(self.current_selected_preset,
                                     notify=False)
        self._update_sidebar_status()

    def refresh_presets(self):
        if not self.preset_manager or self.loading_presets:
            return
        self.loading_presets = True
        self._start_loading_dots("刷新中")
        self._disable_buttons(True)
        threading.Thread(target=self._refresh_presets_thread, daemon=True).start()

    def _refresh_presets_thread(self):
        try:
            self.preset_manager.load_all_presets(use_cache=False)
        except Exception as e:
            self.log_manager.log(f"刷新预设失败: {e}", 'ERROR')
        finally:
            ui_call(self.root, self._on_refresh_presets_done)

    def _on_refresh_presets_done(self):
        # 同上：先解锁，再做其余收尾
        self.loading_presets = False
        self._stop_loading_dots()
        self._disable_buttons(False)
        self._set_pack_dependent_buttons(True)
        try:
            self._apply_role_actions()
        except Exception:
            pass
        try:
            self._update_preset_list()
            self.log_manager.log("预设列表刷新完成", 'INFO', verbose=True)
            self._update_guide()
        except Exception as exc:
            safe_print("预设刷新回调出错:", traceback.format_exc())
            self.log_manager.log(f"预设刷新回调出错: {exc}", 'ERROR')

    def _sync_tacz_shortcut(self):
        """顶部「打开 TACZ」跟着整合包是否加载来开关。"""
        btn = getattr(self, "tacz_head_btn", None)
        if btn is None:
            return
        try:
            btn.configure(state="normal" if self.tacz_path else "disabled")
        except Exception:
            pass

    def on_preset_selected(self, name=None):
        if not self.preset_manager or self.loading_presets:
            return
        if not name:
            name = self.preset_cards.selected_name
        if not name:
            return
        self.preset_cards.select(name, notify=False)
        self.current_selected_preset = name
        self._sync_tacz_shortcut()
        info = self.preset_manager.presets.get(name)
        if not info:
            return
        self.preset_name_label.configure(text=name)
        self._animate_label_color(self.preset_name_label, C_TEXT_MUTED,
                                  C_TEXT_MAIN)
        version = info.get('version', 'v1.0.0')
        self.preset_version_label.configure(text=version)
        status = "已应用" if info.get('applied', False) else "未应用"
        self.preset_status_label.configure(text=status)
        self._update_preset_online_label(name)
        self._animate_label_color(
            self.preset_status_label, C_TEXT_MUTED,
            C_SUCCESS if info.get('applied') else C_WARNING)
        self.version_entry.delete(0, END)
        self.version_entry.insert(0, version)
        if info.get('applied', False):
            self.apply_btn.configure(state="disabled", text="已应用")
        else:
            self.apply_btn.configure(state="normal", text="一键替换")
        self.refresh_gunpacks(use_cache=False)
        self.log_manager.log(f"选择预设: {name}", 'INFO', verbose=True)
        self._update_sidebar_status()
        self._update_guide()

    def on_preset_action(self, name, kind):
        """卡片右侧按钮：更新 / 发布 / 绑定 / 检查。"""
        self.on_preset_selected(name)
        if kind == "sync":
            # 玩家：点了就更新，不弹选择框
            self._sync_now(name)
        elif kind == "publish":
            self.open_publish_dialog(name)
        elif kind == "source":
            self.open_source_dialog(name)
        elif kind == "check":
            self._online_check(name)
        else:
            self._sync_now(name)

    def show_preset_context_menu(self, name, event=None):
        if not self.preset_manager or self.loading_presets:
            return
        info = self.preset_manager.presets.get(name)
        if not info:
            return
        self.preset_cards.select(name, notify=False)
        self.on_preset_selected(name)
        # 自绘菜单：和卡片同一套样式，不再是系统方角菜单
        items = [("详情…", lambda: self.open_preset_detail(name)), None]
        if self.is_developer:
            items.append(("发布到云端…",
                          lambda: self.open_publish_dialog(name)))
        else:
            items.append(("检查更新", lambda: self._online_check(name)))
            items.append(("更新这个预设", lambda: self._sync_now(name)))
        items.append(("云端来源…", lambda: self.open_source_dialog(name)))
        if self.is_developer:
            items += [None, ("迁移预设…", lambda: self.migrate_preset(name))]
        items += [None, ("重命名…", lambda: self.rename_preset(name)), None]
        if name != "default":
            if info.get('applied', False):
                items.append(("删除预设（已应用，请先切换）", None))
            else:
                items.append(("删除预设", lambda: self.delete_preset(name)))

        x_root = y_root = None
        if event is not None and hasattr(event, "x_root"):
            x_root, y_root = event.x_root, event.y_root
        else:
            x_root, y_root = self.root.winfo_pointerxy()
        popup_menu(self, items, x_root, y_root, width=168)

    def migrate_preset(self, preset_name: str):
        if not self.preset_manager or self.loading_presets:
            return
        if self.is_applying:
            show_warning("操作进行中", "请等待当前操作完成")
            return

        info = self.preset_manager.presets.get(preset_name)
        if not info:
            return
        if info.get('applied', False):
            show_warning("提示",
                f"预设 '{preset_name}' 当前已应用。\n\n"
                f"请先切换到其他预设，再执行迁移。")
            return

        target_type = self._ask_migrate_target()
        if not target_type:
            return

        if target_type == 'pack':
            folder = filedialog.askdirectory(title="选择目标整合包根目录")
            if not folder:
                return
            target_pack = Path(folder)
            if not (target_pack / 'tacz').exists():
                show_error("错误",
                    "目标文件夹不是有效的整合包（缺少 tacz 文件夹）")
                return
            target_db = self.settings.get_db_path(target_pack)
        else:
            folder = filedialog.askdirectory(title="选择目标数据库文件夹",
                                              initialdir=str(PROGRAM_DIR))
            if not folder:
                return
            target_db = Path(folder)
            if not target_db.exists():
                show_error("错误", f"目标数据库不存在: {target_db}")
                return
            if not DatabaseLocator.is_valid_database(target_db):
                if ask_yes_no("新建数据库",
                    "目标文件夹不是有效数据库，是否初始化为新数据库？"):
                    DatabaseLocator.init_database(target_db)
                else:
                    return

        target_db.mkdir(parents=True, exist_ok=True)

        conflict_mode = 'rename'
        if (target_db / preset_name).exists():
            if not ask_yes_no("预设已存在",
                f"目标数据库中已存在预设 '{preset_name}'。\n\n"
                f"是否覆盖？（原预设会被移入回收站）"):
                return
            conflict_mode = 'overwrite'

        src_path = Path(info['path'])
        target_path = target_db / preset_name

        if not ask_yes_no("确认迁移",
            f"将把预设 '{preset_name}' 迁移到:\n{target_db}\n\n"
            f"源预设会被删除（移入回收站，可找回）。\n\n"
            f"是否继续？"):
            return

        self.progress_bar.pack(fill=X, pady=(0, 4))
        self.progress_label.pack(fill=X, pady=(0, 4))
        self.progress_bar.set(0)
        self.progress_label.configure(text="准备迁移...")
        self._disable_buttons(True)

        def worker():
            try:
                if target_path.exists():
                    if conflict_mode == 'overwrite':
                        self.preset_manager._safe_remove(target_path)
                shutil.copytree(src_path, target_path)

                idx = target_path / 'index.json'
                if idx.exists():
                    with open(idx, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    data['applied'] = False
                    with open(idx, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)

                src_removed = self.preset_manager._safe_remove(src_path)

                ui_call(self.root, self._on_migrate_preset_finished,
                                True, preset_name, target_db, src_removed)
            except Exception as e:
                self.log_manager.log(f"迁移预设失败: {e}", 'ERROR')
                ui_call(self.root, self._on_migrate_preset_finished,
                                False, preset_name, target_db, False)

        threading.Thread(target=worker, daemon=True).start()

    def _ask_migrate_target(self) -> str | None:
        dlg_w = DLG_SMALL[0]
        card = make_card(get_overlay_host(), self.root, width=dlg_w,
                          escape_value=None, title="迁移预设")
        frame = card.body

        make_label(frame, text="迁移预设到：",
                    fg=C_TEXT_MAIN, font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, pady=(0, PAD_GAP))

        mode_var = StringVar(value="pack")
        radio_pack = ctk.CTkRadioButton(frame, text="另一个整合包（使用其数据库）",
                                         variable=mode_var, value="pack",
                                         text_color=C_TEXT_MAIN,
                                         font=(config.FONT_FAMILY, FS_SMALL),
                                         fg_color=C_ACCENT,
                                         hover_color=C_ACCENT_HOVER,
                                         border_color=C_BORDER)
        radio_pack.pack(anchor=W, pady=(PAD_MICRO, 0))
        card.register_focusable(radio_pack)
        make_label(frame, text="  选择整合包根目录，预设会迁移到该整合包的数据库",
                    fg=C_TEXT_MUTED, font_size=FS_TINY).pack(
                        anchor=W, padx=PAD_INDENT, pady=(0, PAD_TIGHT))

        radio_db = ctk.CTkRadioButton(frame, text="另一个数据库（直接选择数据库文件夹）",
                                       variable=mode_var, value="db",
                                       text_color=C_TEXT_MAIN,
                                       font=(config.FONT_FAMILY, FS_SMALL),
                                       fg_color=C_ACCENT,
                                       hover_color=C_ACCENT_HOVER,
                                       border_color=C_BORDER)
        radio_db.pack(anchor=W, pady=(PAD_MICRO, 0))
        card.register_focusable(radio_db)
        make_label(frame, text="  选择已存在的数据库，或新建一个空数据库",
                    fg=C_TEXT_MUTED, font_size=FS_TINY).pack(
                        anchor=W, padx=PAD_INDENT, pady=(0, PAD_TIGHT))

        def on_ok():
            card.close(mode_var.get())

        def on_cancel():
            card.close(None)

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill=X, side=BOTTOM, pady=(PAD_GAP, 0))
        ok_btn = make_button(btn_frame, "下一步", command=on_ok, accent=True)
        ok_btn.pack(side=RIGHT, padx=PAD_XS)
        cancel_btn = make_button(btn_frame, "取消", command=on_cancel)
        cancel_btn.pack(side=RIGHT)
        card.register_focusable(ok_btn)
        card.register_focusable(cancel_btn)
        return card.wait()

    def _on_migrate_preset_finished(self, success: bool, preset_name: str,
                                     target_db: Path, src_removed: bool):
        self.progress_bar.pack_forget()
        self.progress_label.pack_forget()
        self._disable_buttons(False)

        if success:
            self.log_manager.log(
                f"预设 '{preset_name}' 已迁移到: {target_db}", 'SUCCESS')
            if src_removed:
                self.log_manager.log(
                    f"源预设已移入回收站，可随时找回", 'INFO')
            show_info("迁移成功",
                f"预设 '{preset_name}' 已迁移到:\n{target_db}\n\n"
                f"源预设已{'移入回收站' if src_removed else '保留'}。")
            self.refresh_presets()
        else:
            show_error("迁移失败", "预设迁移失败，请查看日志")

    def rename_preset(self, preset_name):
        if not self.preset_manager or self.loading_presets:
            return
        if getattr(self, "online_busy", False) or self.is_applying:
            show_warning("操作进行中", "正在同步/发布，完成后再改名。")
            return
        if preset_name in getattr(self, "online_checking", set()):
            show_warning("正在检查这个预设", "等检查完成后再改名。")
            return
        new_name = ask_text(self, "重命名预设", "新的预设名称",
                            initial=preset_name,
                            placeholder="例如 SSR 预设包", ok_text="重命名")
        if not new_name or not new_name.strip():
            return
        new_name = new_name.strip()
        if new_name == preset_name:
            return
        if new_name in self.preset_manager.presets:
            show_error("错误", f"预设 '{new_name}' 已存在")
            return
        for char in r'\/:*?"<>|':
            if char in new_name:
                show_error("错误", f"预设名称不能包含非法字符: {char}")
                return
        self.root.config(cursor="watch")
        try:
            if self.preset_manager.rename_preset(preset_name, new_name):
                self._after_rename_preset(preset_name, new_name)
                self.current_selected_preset = new_name
                self._update_preset_list()
                self.preset_cards.select(new_name, notify=False)
                self.on_preset_selected(new_name)
                self.toast(f"已重命名为「{new_name}」", "success")
            else:
                show_error("错误", "预设重命名失败")
        finally:
            self.root.config(cursor="")

    def delete_preset(self, preset_name):
        if not self.preset_manager or self.loading_presets:
            return
        if getattr(self, "online_busy", False) or self.is_applying:
            show_warning("操作进行中", "正在同步/发布，完成后再删除。")
            return
        if preset_name in getattr(self, "online_checking", set()):
            show_warning("正在检查这个预设", "等检查完成后再删除。")
            return
        if preset_name == "default":
            show_warning("提示", "不能删除默认预设")
            return
        info = self.preset_manager.presets.get(preset_name)
        if not info:
            return
        if info.get('applied', False):
            show_warning("提示",
                f"预设 '{preset_name}' 已应用，请先切换到其他预设再删除")
            return
        if not ask_yes_no("确认删除",
                f"确定要删除预设 '{preset_name}' 吗？\n\n此操作不可恢复！"):
            return
        try:
            if self.preset_manager.delete_preset(preset_name):
                # 删除要清干净：云端绑定、manifest 缓存、在线状态、体积缓存
                try:
                    if self.online is not None:
                        self.online.forget_preset(preset_name)
                except Exception:
                    pass
                for store in (self.online_states, self.online_pending):
                    try:
                        store.pop(preset_name, None)
                    except Exception:
                        pass
                try:
                    self._online_recheck.discard(preset_name)
                    self._preset_size_cache.pop(preset_name, None)
                except Exception:
                    pass
                if self.current_selected_preset == preset_name:
                    self.current_selected_preset = None
                    self.preset_name_label.configure(text="未选择")
                    self.preset_version_label.configure(text="无")
                    self.preset_status_label.configure(text="未应用")
                    self.preset_online_label.configure(text="未绑定",
                                                       text_color=C_TEXT_MUTED)
                    try:
                        self.source_btn.configure(text="填写链接")
                        self.sync_btn.pack_forget()
                        self.aux_row.grid_remove()
                    except Exception:
                        pass
                    self.version_entry.delete(0, END)
                    self.apply_btn.configure(state="disabled", text="一键替换")
                    self.gunpack_listbox.delete(0, END)
                    self.gunpack_count_label.configure(text="共 0 个枪包")
                self._update_preset_list()
                self.toast(f"已删除「{preset_name}」", "success")
                self._update_guide()
            else:
                show_error("错误", "删除预设失败")
        except Exception as e:
            show_error("错误", f"删除失败: {e}")

    def create_preset(self):
        if not self.preset_manager or self.loading_presets:
            return
        name = ask_text(self, "新建预设", "预设名称",
                        placeholder="例如 SSR 预设包", ok_text="创建")
        if not name or not name.strip():
            return
        name = name.strip()
        if name in self.preset_manager.presets:
            show_error("错误", f"预设 '{name}' 已存在")
            return
        version = ask_text(self, "版本号", "版本号（可留空，默认 v1.0.0）",
                           placeholder="v1.0.0", ok_text="确定")
        if version is None:
            return
        version = version.strip() or "v1.0.0"
        if self.preset_manager.create_preset(name, version):
            path = Path(self.preset_manager.presets[name]['path'])
            try:
                open_path(path)
            except Exception:
                pass
            self._update_preset_list()
            self.log_manager.log(
                f"预设「{name}」已创建（{version}），把枪包放进刚打开的文件夹后点刷新",
                'SUCCESS')
            self.toast(f"已创建「{name}」，把枪包放进打开的文件夹", "success")
            self._update_guide()
        else:
            show_error("无法创建预设",
                       "名称不合法（不能含 \\ / : * ? \" < > |、不能以点开头、"
                       "不能是系统保留名），或目录已存在。换个名字试试。")

    def save_version(self):
        if not self.preset_manager or not self.current_selected_preset:
            return
        v = self.version_entry.get().strip() or "v1.0.0"
        if self.preset_manager.update_preset_version(self.current_selected_preset, v):
            self.preset_version_label.configure(text=v)
            self.version_entry.delete(0, END)
            self.version_entry.insert(0, v)
            # 左侧卡片的版本也要立刻变
            self._update_preset_list()
            self.log_manager.log(f"版本号已更新为: {v}", 'SUCCESS')
