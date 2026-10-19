"""数据库：初始化 / 切换 / 合并 / 迁移"""
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


class DatabaseMixin:
    """数据库：初始化 / 切换 / 合并 / 迁移"""

    # ==================== 数据库初始化 ====================
    def _init_database_flow(self):
        db_path = DatabaseLocator.load_db_path()
        if db_path and DatabaseLocator.is_valid_database(db_path):
            self._use_database(db_path)
            return

        if db_path and LegacyDatabaseMigrator.is_legacy_database(db_path):
            if ask_yes_no("检测到旧版数据库",
                f"检测到旧版 FGC_database:\n{db_path}\n\n"
                f"是否适配为新版数据库？\n"
                f"（可选择迁移后标记或删除原库）"):
                DatabaseLocator.init_database(DEFAULT_DB_DIR)
                self._use_database(DEFAULT_DB_DIR)
                self.root.after(200, lambda p=db_path: self.migrate_legacy_database(p))
            return

        if db_path:
            self.log_manager.log(f"数据库位置失效: {db_path}", 'WARNING')

        # 绿色版：程序旁边就有一个数据库（随包带的空库，或用户拷过来的旧库）
        # ——直接用它，连配置文件都不需要，解压双击即用。
        try:
            if DatabaseLocator.is_valid_database(DEFAULT_DB_DIR):
                self.log_manager.log(
                    f"使用随包数据库：{DEFAULT_DB_DIR}", 'SUCCESS')
                DatabaseLocator.save_db_path(DEFAULT_DB_DIR)
                self._use_database(DEFAULT_DB_DIR)
                return
        except Exception:
            pass

        # 首次启动：直接把默认库建好，不弹「请你选择数据库」——
        # 新用户根本不知道数据库该放哪，问一次只会卡住他。
        # 需要换位置时，主界面「更多 → 数据库位置」里随时能改。
        try:
            if DatabaseLocator.init_database(DEFAULT_DB_DIR):
                DatabaseLocator.save_db_path(DEFAULT_DB_DIR)
                self.log_manager.log(
                    f"已自动创建数据库：{DEFAULT_DB_DIR}", 'SUCCESS')
                self._use_database(DEFAULT_DB_DIR)
                return
        except Exception as exc:
            self.log_manager.log(f"自动创建数据库失败：{exc}", 'WARNING')

        self.log_manager.log("未检测到数据库，请选择定位或新建", 'GUIDE')
        dialog = DatabaseLocatorDialog(self.root)
        result = dialog.show()
        if result:
            DatabaseLocator.save_db_path(result)
            self._use_database(result)
            if getattr(dialog, 'legacy_to_migrate', None):
                self.root.after(200, lambda p=dialog.legacy_to_migrate:
                                 self.migrate_legacy_database(p))
        else:
            self.log_manager.log("未选择数据库，部分功能不可用", 'WARNING')

    def _apply_role_from_settings(self):
        """按当前数据库里的身份，把整套界面刷成一致状态。

        启动、切换数据库都要走这里：设置页是在绑定数据库之前建的，
        不重刷就会出现「身份是开发者、设置页却没有数据库管理」这类错乱。
        """
        try:
            role = getattr(self.settings, "role", "player")
            previous = getattr(config, "UI_ROLE", "player")
            config.UI_ROLE = role
            roots = [self.root]
            roots.extend(p for p in getattr(self, "pages", {}).values()
                         if p is not None)
            try:
                theme_widgets(roots, previous, role)
            except Exception:
                pass
            try:
                self._update_identity_ui()
            except Exception:
                pass
            try:
                self._apply_role_actions()
            except Exception:
                pass
            try:
                self._rebuild_settings_role_dependent()
            except Exception:
                pass
        except Exception:
            pass

    def _use_database(self, db_path: Path):
        self.db_path = Path(db_path)
        self.settings.bind_database(db_path)
        # 数据库里的 role 决定整套界面（配色/徽标/主操作/设置页分区）
        self._apply_role_from_settings()
        self.recent_manager = RecentPacksManager(db_path / ".global.json")
        self.db_ready = True
        self.update_recent_list()
        self.log_manager.log(f"{PROJECT_NAME} v{VERSION} 启动成功，作者: {AUTHOR}", 'SUCCESS')
        self.log_manager.log(f"数据库位置: {db_path}", 'INFO', verbose=True)
        self.log_manager.log(
            "运行模式: " + ("绿色版（数据写在程序目录）" if IS_PORTABLE_MODE
                        else "安装版（数据写在用户目录）"),
            'INFO', verbose=True)
        self.log_manager.log(
            f"存储模式: {'合并' if self.settings.storage_mode == 'merged' else '隔离'}",
            'INFO', verbose=True)
        self.log_manager.log(
            f"用户身份: {'玩家' if self.settings.role == 'player' else '开发者'}",
            'INFO', verbose=True)
        if HAS_WATCHDOG:
            self.log_manager.log("watchdog 已就绪，可实时监控 TACZ 文件变化",
                                 'INFO', verbose=True)
        else:
            self.log_manager.log("watchdog 未安装，文件变更需手动刷新 (pip install watchdog)", 'WARNING')
        if IS_WINDOWS:
            self.log_manager.log("已启用 Windows 原生回收站删除", 'INFO',
                                 verbose=True)
        self.log_manager.log("Step 1 · 拖入整合包根目录（或整合包内任意文件）", 'GUIDE')
        self._update_guide()

    # ==================== 数据库管理 ====================
    def switch_database(self):
        if self.is_applying:
            show_warning("操作进行中", "请等待当前操作完成")
            return
        if self.settings.storage_mode != "merged":
            # 独立模式下每个整合包都用自己的 PulsesSwap_database：
            # 切了位置，重新打开整合包又会切回去，等于白切。
            show_warning(
                "当前是独立数据库模式",
                "每个整合包都用自己的 PulsesSwap_database。\n\n"
                "要固定使用一个数据库，请先在设置里把存储方式改成"
                "「合并数据库」，再切换位置。")
            return
        if self.loading_presets or self.is_applying:
            show_warning("操作进行中", "等当前操作完成后再切换数据库。")
            return
        folder = filedialog.askdirectory(title="选择新的数据库文件夹",
                                          initialdir=str(PROGRAM_DIR))
        if not folder:
            return
        path = Path(folder)
        if LegacyDatabaseMigrator.is_legacy_database(path):
            if ask_yes_no("检测到旧版数据库",
                "该文件夹是旧版 FGC_database。\n\n"
                "是否先适配为新版数据库？"):
                self.migrate_legacy_database(path)
            return
        if (path / LEGACY_MIGRATED_MARKER).exists():
            show_info("提示",
                "该文件夹是已迁移的旧版数据库。\n\n"
                "如需重新适配，请删除旧库根目录下的\n"
                f"{LEGACY_MIGRATED_MARKER} 文件后再试。")
            return
        if not DatabaseLocator.is_valid_database(path):
            if ask_yes_no("新建数据库",
                "该文件夹不是有效数据库，是否初始化为新数据库？"):
                DatabaseLocator.init_database(path)
            else:
                return
        DatabaseLocator.save_db_path(path)
        self.settings.bind_database(path)
        # 新库自带的 .settings.json 默认是 isolated：绑定后会把刚才选的
        # 「合并模式」冲掉，重新打开整合包又回到各自的库。这里按用户的
        # 选择把模式写回新库。
        if self.settings.storage_mode != "merged":
            self.settings.storage_mode = "merged"
            try:
                self.settings.save()
            except Exception:
                pass
        # 当前会话也要立刻用新库，否则界面还指着旧路径
        self.db_path = path
        self.db_ready = True
        if self.recent_manager:
            self.recent_manager = RecentPacksManager(path / ".global.json")
        self.log_manager.log(f"数据库已切换: {path}", 'SUCCESS')
        show_info("完成", "数据库已切换，请重新打开整合包。")
        self.close_pack()
        # 新库可能是玩家身份：徽标/主题/按钮/设置页要一起换过来
        self._apply_role_from_settings()

    def merge_database(self):
        if not self.db_ready:
            show_warning("提示", "数据库未初始化")
            return
        folder = filedialog.askdirectory(title="选择要合并的数据库文件夹",
                                          initialdir=str(PROGRAM_DIR))
        if not folder:
            return
        src = Path(folder)
        dst = self.settings._settings_file.parent if self.settings._settings_file else None
        if not dst:
            return
        if src == dst:
            show_warning("提示", "不能合并到自身")
            return

        src_presets = [p.name for p in src.iterdir()
                       if p.is_dir() and not p.name.startswith('.')]
        conflicts = [n for n in src_presets if (dst / n).exists()]
        msg = f"将把 {len(src_presets)} 个预设合并到当前数据库。"
        if conflicts:
            msg += f"\n\n其中 {len(conflicts)} 个同名预设冲突:\n" + \
                   "\n".join(conflicts[:10])
            if len(conflicts) > 10:
                msg += f"\n... 还有 {len(conflicts)-10} 个"
        msg += "\n\n冲突预设如何处理？"
        choice = self._ask_conflict_mode(msg)
        if not choice:
            return
        stats = LegacyDatabaseMigrator.migrate_legacy_to_new(
            src, dst, self.log_manager, conflict_mode=choice)
        self.log_manager.log(
            f"合并完成: 迁移 {stats['migrated']}, 重命名 {stats['renamed']}, "
            f"跳过 {stats['skipped']}, 错误 {len(stats['errors'])}", 'SUCCESS')
        if stats['errors']:
            show_warning("部分失败", "\n".join(stats['errors'][:10]))
        else:
            show_info("完成", "数据库合并完成。")
        self.refresh_presets()

    def migrate_legacy_database(self, legacy_path: Path = None):
        if not legacy_path:
            folder = filedialog.askdirectory(title="选择旧版 FGC_database 文件夹",
                                              initialdir=str(PROGRAM_DIR))
            if not folder:
                return
            legacy_path = Path(folder)

        if not LegacyDatabaseMigrator.is_legacy_database(legacy_path):
            if (legacy_path / LEGACY_MIGRATED_MARKER).exists():
                if not ask_yes_no("已迁移过",
                    f"该数据库已被标记为「已迁移」:\n{legacy_path}\n\n"
                    f"是否仍要再次适配？（可能产生重复预设）"):
                    return
            else:
                show_error("错误", "所选文件夹不是旧版数据库")
                return

        dst = (self.settings._settings_file.parent
               if self.settings._settings_file else DEFAULT_DB_DIR)

        if self.settings.storage_mode == 'isolated':
            if ask_yes_no("选择目标数据库",
                f"当前为隔离存储模式。\n\n"
                f"是否将旧库适配到全局默认数据库？\n"
                f"{DEFAULT_DB_DIR}\n\n"
                f"选“否”可手动选择目标数据库。"):
                dst = DEFAULT_DB_DIR
            else:
                folder = filedialog.askdirectory(title="选择目标数据库文件夹",
                                                  initialdir=str(PROGRAM_DIR))
                if not folder:
                    return
                dst = Path(folder)
                if not DatabaseLocator.is_valid_database(dst):
                    if ask_yes_no("新建数据库",
                        "目标不是有效数据库，是否初始化为新数据库？"):
                        DatabaseLocator.init_database(dst)
                    else:
                        return

        if not ask_yes_no("确认适配",
            f"将把旧版数据库:\n{legacy_path}\n\n"
            f"适配并合并到:\n{dst}\n\n"
            f"是否继续？"):
            return

        after_mode = self._ask_after_migrate()
        if not after_mode:
            return

        self.progress_bar.pack(fill=X, pady=(0, 4))
        self.progress_label.pack(fill=X, pady=(0, 4))
        self.progress_bar.set(0)
        self.progress_label.configure(text="准备适配...")
        self._disable_buttons(True)
        self.select_pack_btn.configure(state="disabled")

        def progress_cb(c, t, m):
            if t > 0:
                pct = c / t
                ui_call(self.root, lambda p=pct: self.progress_bar.set(p))
                ui_call(self.root, lambda m=m, c=c, t=t: self.progress_label.configure(
                    text=f"{m} ({c}/{t})"))
            # 只处理重绘空闲任务：原来用 update() 会连带处理用户事件，
            # 拖拽窗口大小时每个进度回调都会重入一次完整事件循环，明显卡顿
            ui_call(self.root, lambda: self.root.update_idletasks())

        def worker():
            try:
                stats = LegacyDatabaseMigrator.migrate_legacy_to_new(
                    legacy_path, dst, self.log_manager,
                    conflict_mode='rename',
                    progress_callback=progress_cb,
                    after_migrate=after_mode)
                ui_call(self.root, self._on_migrate_finished, stats, after_mode)
            except Exception as e:
                self.log_manager.log(f"适配旧库出错: {e}", 'ERROR')
                ui_call(self.root, self._on_migrate_finished,
                                {'migrated': 0, 'renamed': 0, 'skipped': 0,
                                 'errors': [str(e)], 'disposed': 'none'},
                                after_mode)

        threading.Thread(target=worker, daemon=True).start()

    def _on_migrate_finished(self, stats: dict, after_mode: str):
        self.progress_bar.pack_forget()
        self.progress_label.pack_forget()
        self._disable_buttons(False)
        self.select_pack_btn.configure(state="normal")

        disposed = stats.get('disposed', 'none')
        disposed_text = {
            'marked': "原库已标记为「已迁移」，下次不再提示",
            'recycled': "原库已移入回收站，可随时恢复",
            'deleted': "原库已删除（无法移入回收站）",
            'none': "原库保持原样",
        }.get(disposed, "原库保持原样")

        if stats['errors']:
            self.log_manager.log(
                f"适配完成，但有 {len(stats['errors'])} 个错误", 'WARNING')
            err_text = "\n".join(stats['errors'][:10])
            if len(stats['errors']) > 10:
                err_text += f"\n... 还有 {len(stats['errors'])-10} 个"
            show_warning("部分失败",
                f"旧版数据库适配完成，部分预设失败:\n\n{err_text}")
        else:
            self.log_manager.log(
                f"旧版数据库适配完成: 迁移 {stats['migrated']}, "
                f"重命名 {stats['renamed']}, 跳过 {stats['skipped']}",
                'SUCCESS')
            show_info("完成",
                f"旧版数据库适配完成。\n\n"
                f"迁移预设: {stats['migrated']}\n"
                f"重命名: {stats['renamed']}\n"
                f"跳过: {stats['skipped']}\n\n"
                f"{disposed_text}")

        self.refresh_presets()
        self._update_guide()

    def _ask_after_migrate(self) -> str | None:
        dlg_w = DLG_CHOICE[0]
        card = make_card(get_overlay_host(), self.root, width=dlg_w,
                          escape_value=None, title="迁移后处理")
        frame = card.body

        make_label(frame, text="迁移完成后，如何处理旧版数据库？",
                    fg=C_TEXT_MAIN, font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, pady=(0, PAD_INNER))
        desc = make_label(frame,
            text="建议选择「标记为已迁移」，保留原库作为备份。",
            fg=C_TEXT_SECONDARY, font_size=FS_SMALL)
        desc.configure(wraplength=dlg_w - 2 * PAD_DIALOG, justify=LEFT, anchor=W)
        desc.pack(anchor=W, fill=X, pady=(0, PAD_GAP))

        mode_var = StringVar(value=self.last_after_migrate_mode)
        for text, val, tip in [
            ("标记为已迁移（推荐）", "mark",
             "  在旧库写入标记文件，下次不再提示，原数据保留"),
            ("移入回收站", "delete",
             "  迁移成功后把旧库整目录移入回收站，可随时恢复"),
            ("保留原库（不标记）", "keep",
             "  不做任何处理，下次启动仍会提示适配"),
        ]:
            radio = ctk.CTkRadioButton(frame, text=text, variable=mode_var, value=val,
                                        text_color=C_TEXT_MAIN,
                                        font=(config.FONT_FAMILY, FS_SMALL),
                                        fg_color=C_ACCENT,
                                        hover_color=C_ACCENT_HOVER,
                                        border_color=C_BORDER)
            radio.pack(anchor=W, pady=(PAD_MICRO, 0))
            card.register_focusable(radio)
            make_label(frame, text=tip, fg=C_TEXT_MUTED, font_size=FS_TINY).pack(
                anchor=W, padx=PAD_INDENT, pady=(0, PAD_XS))

        def on_ok():
            self.last_after_migrate_mode = mode_var.get()
            card.close(mode_var.get())

        def on_cancel():
            card.close(None)

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill=X, side=BOTTOM, pady=(PAD_GAP, 0))
        ok_btn = make_button(btn_frame, "确定", command=on_ok, accent=True)
        ok_btn.pack(side=RIGHT, padx=PAD_XS)
        cancel_btn = make_button(btn_frame, "取消", command=on_cancel)
        cancel_btn.pack(side=RIGHT)
        card.register_focusable(ok_btn)
        card.register_focusable(cancel_btn)
        return card.wait()

    def _ask_conflict_mode(self, message: str) -> str | None:
        dlg_w = DLG_CHOICE[0]
        card = make_card(get_overlay_host(), self.root, width=dlg_w,
                          escape_value=None, title="冲突处理")
        frame = card.body
        lbl = make_label(frame, text=message, fg=C_TEXT_MAIN, font_size=FS_BODY)
        lbl.configure(wraplength=dlg_w - 2 * PAD_DIALOG, justify=LEFT, anchor=W)
        lbl.pack(anchor=W, fill=X, pady=(0, PAD_GAP))

        mode_var = StringVar(value="rename")
        for text, val in [
            ("重命名冲突预设（推荐，不丢数据）", "rename"),
            ("跳过冲突预设（保留现有）", "skip"),
            ("覆盖冲突预设（危险，会删除现有）", "overwrite"),
        ]:
            radio = ctk.CTkRadioButton(frame, text=text, variable=mode_var, value=val,
                                        text_color=C_TEXT_MAIN,
                                        font=(config.FONT_FAMILY, FS_SMALL),
                                        fg_color=C_ACCENT,
                                        hover_color=C_ACCENT_HOVER,
                                        border_color=C_BORDER)
            radio.pack(anchor=W, pady=PAD_MICRO)
            card.register_focusable(radio)

        def on_ok():
            card.close(mode_var.get())

        def on_cancel():
            card.close(None)

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill=X, side=BOTTOM, pady=(PAD_GAP, 0))
        ok_btn = make_button(btn_frame, "确定", command=on_ok, accent=True)
        ok_btn.pack(side=RIGHT, padx=PAD_XS)
        cancel_btn = make_button(btn_frame, "取消", command=on_cancel)
        cancel_btn.pack(side=RIGHT)
        card.register_focusable(ok_btn)
        card.register_focusable(cancel_btn)
        return card.wait()

    def force_update_validation(self):
        if not self.preset_manager:
            show_warning("提示", "请先加载整合包")
            return
        if not self.current_selected_preset:
            show_warning("提示", "请先选择一个预设")
            return
        if not ask_yes_no("危险操作警告",
            "强制更新校验数据是危险操作！\n\n"
            "确定要继续吗？", icon='warning'):
            return
        name = self.current_selected_preset
        info = self.preset_manager.presets.get(name)
        if not info:
            return
        from_tacz = info.get('applied', False)
        if self.preset_manager.update_preset_index(name, from_tacz=from_tacz):
            self.refresh_gunpacks(use_cache=False)
            self.log_manager.log(f"已强制更新预设 '{name}' 的校验数据", 'WARNING')
            show_info("完成", f"预设 '{name}' 的校验数据已强制更新。")
        else:
            show_error("错误", "强制更新失败，请查看日志")
