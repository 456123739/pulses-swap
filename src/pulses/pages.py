"""
设置页
（由单文件按分区拆分而来，逻辑未改动）
"""
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

from . import config
from .config import *
from .utils import *
from . import config
from .widget import *
from .dialogs import *
from .managers import *



# ==================== 设置对话框 ====================
class SettingsPage:
    """
    设置页面（侧边栏「设置」页）：
    · 选项卡改成自绘的 CanvasSegmented，选中滑块带曲线滑动动画；
    · 选项卡内容用 SlideStack 做同款推入/推出切换；
    · 所有选项改完立即自动保存（写数据库目录下的 .settings.json），
      底部按钮条只保留「恢复默认」和自动保存状态回显。
    """

    def __init__(self, parent_frame, app, on_save_callback=None,
                 on_db_action=None):
        self.parent_frame = parent_frame
        self.app = app
        self.root = app.root
        self.settings: AppSettings = app.settings
        self.on_save_callback = on_save_callback
        self.on_db_action = on_db_action
        self._loading = False

        self.frame = ctk.CTkFrame(parent_frame, fg_color=C_WINDOW_BG)

        # ===== 选项卡头部：自绘分段控件（滑块带动画） =====
        head = ctk.CTkFrame(self.frame, fg_color=C_CARD_BG,
                             corner_radius=R_CARD, border_width=BORDER_W,
                             border_color=C_BORDER_SOFT, height=H_TAB_HEAD)
        head.pack(fill=X)
        head.pack_propagate(False)
        self.tab_bar = CanvasSegmented(
            head, [("general", "常规"), ("database", "数据库"), ("about", "关于")],
            command=self._on_tab_selected, orientation="horizontal",
            item_height=H_CONTROL, pad=8, gap=6, radius=R_CONTROL,
            bg_color=C_CARD_BG, pill_color=C_ACCENT, hover_color=C_ACCENT_SOFT,
            text_color=C_TEXT_SECONDARY, active_text_color=C_TEXT_INVERSE,
            font_size=FS_BODY, bold_active=True, text_anchor="center",
            duration_ms=240)
        self.tab_bar.pack(fill=BOTH, expand=True, padx=PAD_XS, pady=PAD_XS)

        # ===== 选项卡内容：Canvas 承载，切换时整块推入/推出 =====
        self.stack = SlideStack(self.frame, bg_color=C_WINDOW_BG, duration_ms=260)
        self.stack.canvas.pack_configure(pady=(PAD_GAP, 0))

        self.storage_var = StringVar(value=self.settings.storage_mode)
        self.role_var = StringVar(value=self.settings.role)

        self.tabs = {}
        for key in ("general", "database", "about"):
            tab = ctk.CTkFrame(self.stack.canvas, fg_color=C_WINDOW_BG)
            self.tabs[key] = tab
            self.stack.add(key, tab)

        self._build_general(self.tabs["general"])
        self._build_database(self.tabs["database"])
        self._build_about(self.tabs["about"])

        # ===== 底部按钮条：自动保存状态 + 恢复默认 =====
        self.btn_bar = ctk.CTkFrame(self.frame, fg_color=C_CARD_BG,
                                     corner_radius=R_CARD, height=H_BTN_BAR,
                                     border_width=0)
        self.btn_bar.pack(fill=X, pady=(PAD_GAP, 0))
        self.btn_bar.pack_propagate(False)
        make_button(self.btn_bar, "恢复默认", command=self._reset_defaults,
                     width=100).pack(side=RIGHT, padx=(PAD_TIGHT, PAD_DIALOG),
                                     pady=(H_BTN_BAR - H_CONTROL) // 2)
        self.saved_label = make_label(self.btn_bar, text=self._saved_hint(),
                                       fg=C_TEXT_MUTED, font_size=FS_TINY)
        self.saved_label.pack(side=LEFT, padx=PAD_DIALOG)

        self.reload()
        # 预热：每个选项卡都先布局一次，避免第一次切换时卡一帧
        try:
            for key in ("general", "database", "about"):
                self.stack.items[key]
                self.stack.canvas.itemconfigure(self.stack.items[key],
                                                 state="normal")
            self.stack.canvas.update_idletasks()
            for key in ("general", "database", "about"):
                self.stack.canvas.itemconfigure(self.stack.items[key],
                                                 state="hidden")
        except Exception:
            pass
        self.show_tab("general", animate=False)

    def _saved_hint(self):
        # 需求：设置项简洁 —— 常态只留四个字，改动时短暂回显「已自动保存」
        return "自动保存"

    # ==================== 选项卡切换 ====================
    def _on_tab_selected(self, key):
        self.show_tab(key)

    def show_tab(self, key, animate=True):
        if key not in self.tabs:
            return
        # 注意：不能用 tab_bar.current() 当「上一个」——点击进来时
        # CanvasSegmented 已经先把选中态切到新项了，那样永远算不出方向，
        # 表现就是「不管点哪边都往同一个方向滑」。这里自己记上一个选项卡。
        previous = getattr(self, "_active_tab", None) or self.stack.current
        direction = 1
        if previous is not None and previous != key:
            old_index = self.tab_bar.index_of(previous)
            new_index = self.tab_bar.index_of(key)
            # 点左面的选项卡内容往左走（新页从右侧进来），点右面的往右走
            if old_index >= 0 and new_index >= 0:
                direction = 1 if new_index > old_index else -1
        self._active_tab = key
        self.tab_bar.select(key, animate=animate, notify=False)
        self.stack.show(key, animate=animate, direction=direction, axis="x")

    # ==================== 选项卡：常规 ====================
    def _build_general(self, tab):
        # 需求：设置项要简洁 —— 不留解释性小字，选项本身就是完整说明；
        # 选中态用带动画的分段控件（滑块逐帧滑动），切换即可见。
        make_label(tab, text="存储模式", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, pady=(PAD_TIGHT, PAD_TIGHT))
        mode_card = ctk.CTkFrame(tab, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                  border_width=0)
        mode_card.pack(fill=X, pady=(0, PAD_DIALOG))
        attach_hover_glow(mode_card)
        self.mode_seg = CanvasSegmented(
            mode_card, [("isolated", "隔离存储"), ("merged", "合并存储")],
            command=self._on_mode_selected, orientation="vertical",
            item_height=H_NAV, pad=6, gap=PAD_XS, radius=R_CONTROL,
            bg_color=C_CARD_BG, pill_color=C_ACCENT_SOFT,
            hover_color=C_ACCENT_SOFT, text_color=C_TEXT_MAIN,
            active_text_color=C_ACCENT, font_size=FS_BODY, bold_active=True,
            text_anchor="w", text_pad=16, duration_ms=240,
            height=px(2 * (H_NAV + PAD_XS) + 12))
        self.mode_seg.pack(fill=X, padx=PAD_TIGHT, pady=PAD_TIGHT)

        make_label(tab, text="动画", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, pady=(0, PAD_TIGHT))
        anim_card = ctk.CTkFrame(tab, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                  border_width=0)
        anim_card.pack(fill=X, pady=(0, PAD_DIALOG))
        attach_hover_glow(anim_card)
        self.anim_seg = CanvasSegmented(
            anim_card, [("on", "流畅"), ("off", "关闭")],
            command=self._on_anim_selected, orientation="vertical",
            item_height=H_NAV, pad=6, gap=PAD_XS, radius=R_CONTROL,
            bg_color=C_CARD_BG, pill_color=C_ACCENT_SOFT,
            hover_color=C_ACCENT_SOFT, text_color=C_TEXT_MAIN,
            active_text_color=C_ACCENT, font_size=FS_BODY, bold_active=True,
            text_anchor="w", text_pad=16, duration_ms=240,
            height=px(2 * (H_NAV + PAD_XS) + 12))
        self.anim_seg.pack(fill=X, padx=PAD_TIGHT, pady=PAD_TIGHT)

        make_label(tab, text="用户身份", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, pady=(0, PAD_TIGHT))
        role_card = ctk.CTkFrame(tab, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                  border_width=0)
        role_card.pack(fill=X, pady=(0, PAD_DIALOG))
        attach_hover_glow(role_card)
        self.role_seg = CanvasSegmented(
            role_card, [("player", "玩家"), ("developer", "开发者")],
            command=self._on_role_selected, orientation="vertical",
            item_height=H_NAV, pad=6, gap=PAD_XS, radius=R_CONTROL,
            bg_color=C_CARD_BG, pill_color=C_ACCENT_SOFT,
            hover_color=C_ACCENT_SOFT, text_color=C_TEXT_MAIN,
            active_text_color=C_ACCENT, font_size=FS_BODY, bold_active=True,
            text_anchor="w", text_pad=16, duration_ms=380,
            height=px(2 * (H_NAV + PAD_XS) + 12))
        self.role_seg.pack(fill=X, padx=PAD_TIGHT, pady=PAD_TIGHT)

        # ===== 在线同步 =====
        make_label(tab, text="在线同步", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, pady=(0, PAD_TIGHT))
        online_card = ctk.CTkFrame(tab, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                    border_width=0)
        online_card.pack(fill=X, pady=(0, PAD_DIALOG))
        attach_hover_glow(online_card)
        self.online_auto_seg = CanvasSegmented(
            online_card, [("on", "启动时检查更新"), ("off", "不自动检查")],
            command=self._on_online_auto_selected, orientation="vertical",
            item_height=H_NAV, pad=6, gap=PAD_XS, radius=R_CONTROL,
            bg_color=C_CARD_BG, pill_color=C_ACCENT_SOFT,
            hover_color=C_ACCENT_SOFT, text_color=C_TEXT_MAIN,
            active_text_color=C_ACCENT, font_size=FS_BODY, bold_active=True,
            text_anchor="w", text_pad=16, duration_ms=240,
            height=px(2 * (H_NAV + PAD_XS) + 12))
        self.online_auto_seg.pack(fill=X, padx=PAD_TIGHT, pady=(PAD_TIGHT, PAD_XS))

        # 「更新时要不要顺手删掉本地多余枪包」——以前这是在同步弹窗里逐个勾的，
        # 现在同步一键完成，取舍放这里一次性定好。
        self.online_clean_seg = CanvasSegmented(
            online_card, [("off", "多余枪包：保留"), ("on", "多余枪包：同步时删除")],
            command=self._on_online_clean_selected, orientation="vertical",
            item_height=H_NAV, pad=6, gap=PAD_XS, radius=R_CONTROL,
            bg_color=C_CARD_BG, pill_color=C_ACCENT_SOFT,
            hover_color=C_ACCENT_SOFT, text_color=C_TEXT_MAIN,
            active_text_color=C_ACCENT, font_size=FS_BODY, bold_active=True,
            text_anchor="w", text_pad=16, duration_ms=240,
            height=px(2 * (H_NAV + PAD_XS) + 12))
        self.online_clean_seg.pack(fill=X, padx=PAD_TIGHT, pady=(0, PAD_TIGHT))

        cache_row = ctk.CTkFrame(online_card, fg_color="transparent")
        cache_row.pack(fill=X, padx=PAD_TIGHT, pady=(0, PAD_TIGHT))
        make_button(cache_row, "清理缓存", command=self._clean_online_cache,
                    width=88).pack(side=LEFT)
        self.online_cache_label = make_label(
            cache_row, text="", fg=C_TEXT_MUTED, font_size=FS_TINY)
        self.online_cache_label.pack(side=LEFT, padx=PAD_TIGHT)

    def _on_online_clean_selected(self, key):
        self.app.settings.online_sync_clean = (key == "on")
        try:
            self.app.settings.save()
        except Exception:
            pass

    def _on_online_auto_selected(self, key):
        self.app.settings.online_auto_check = (key == "on")
        try:
            self.app.settings.save()
        except Exception:
            pass

    def _refresh_online_cache_label(self):
        label = getattr(self, "online_cache_label", None)
        if label is None:
            return
        service = getattr(self.app, "online", None)
        if service is None:
            label.configure(text="在线模块未启用")
            return
        size = service.cache_size()
        label.configure(text=f"当前缓存 {format_size(size)}")

    def _clean_online_cache(self):
        service = getattr(self.app, "online", None)
        if service is None:
            return
        freed = service.clear_caches()
        self.app.toast(f"已清理 {format_size(freed)}", "success")
        self._refresh_online_cache_label()

    def _on_anim_selected(self, key):
        """动画开关：关掉后所有补间一帧到位（逻辑不变，只是不逐帧画）。"""
        enabled = (key != "off")
        apply_animations_setting(enabled)
        try:
            self.app.settings.animations = enabled
            self.app.settings.save()
        except Exception:
            pass
        self.app.toast("动画已关闭" if not enabled else "动画已开启",
                       kind="info")

    def _on_mode_selected(self, key):
        self.storage_var.set(key)
        self._on_auto_save()

    def _on_role_selected(self, key):
        self.role_var.set(key)
        self._on_auto_save()

    # ==================== 选项卡：数据库 ====================
    def _build_database(self, tab):
        make_label(tab, text="数据库位置", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, pady=(PAD_TIGHT, PAD_TIGHT))
        db_card = ctk.CTkFrame(tab, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                border_width=0)
        db_card.pack(fill=X, pady=(0, PAD_DIALOG))
        self.db_path_label = make_label(db_card, text="", fg=C_TEXT_MAIN,
                                        font_size=FS_SMALL)
        self.db_path_label.configure(wraplength=620, justify=LEFT, anchor=W)
        self.db_path_label.pack(anchor=W, padx=PAD_CARD_X, pady=PAD_CARD_Y)

        # 数据库管理只给开发者：玩家不需要合并库、适配旧版、强制校验这些概念
        developer = bool(getattr(self.app, "is_developer", False))
        if developer:
            make_label(tab, text="数据库管理", fg=C_ACCENT,
                        font_size=FS_SUBHEAD, bold=True).pack(
                            anchor=W, pady=(0, PAD_TIGHT))
        db_mgr_card = ctk.CTkFrame(tab, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                    border_width=0)
        db_mgr_card.pack(fill=X, pady=(0, PAD_DIALOG))

        btn_row2 = ctk.CTkFrame(db_mgr_card, fg_color="transparent")
        btn_row2.pack(fill=X, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        make_button(btn_row2, "打开数据库文件夹", command=self.on_open_db).pack(
            side=LEFT, padx=(0, PAD_TIGHT))
        if developer:
            make_button(btn_row2, "强制更新校验数据",
                         command=self.app.force_update_validation).pack(
                side=LEFT, padx=PAD_TIGHT)

        if developer:
            btn_row1 = ctk.CTkFrame(db_mgr_card, fg_color="transparent")
            btn_row1.pack(fill=X, padx=PAD_CARD_X, pady=(0, PAD_TIGHT))
            make_button(btn_row1, "切换数据库", command=self.on_switch_db).pack(
                side=LEFT, padx=(0, PAD_TIGHT))
            make_button(btn_row1, "合并数据库", command=self.on_merge_db).pack(
                side=LEFT, padx=PAD_TIGHT)
            make_button(btn_row1, "适配旧版数据库",
                         command=self.on_migrate_legacy).pack(
                side=LEFT, padx=PAD_TIGHT)
        make_label(db_mgr_card, text="", font_size=FS_TINY).pack(
                anchor=W, padx=PAD_CARD_X, pady=(0, PAD_TIGHT))

    # ==================== 选项卡：关于 ====================
    def _build_about(self, tab):
        make_label(tab, text=f"{PROJECT_NAME} v{VERSION}", fg=C_ACCENT,
                    font_size=FS_TITLE, bold=True).pack(
                        anchor=W, pady=(PAD_TIGHT, PAD_MICRO))
        make_label(tab, text=f"作者: {AUTHOR} · Minecraft Tacz 模组枪包快速切换工具",
                    fg=C_TEXT_SECONDARY, font_size=FS_SMALL).pack(
                        anchor=W, pady=(0, PAD_DIALOG))

        info_card = ctk.CTkFrame(tab, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                  border_width=0)
        info_card.pack(fill=X, pady=(0, PAD_DIALOG))
        attach_hover_glow(info_card)
        self.about_db_label = make_label(info_card, text="", fg=C_TEXT_MAIN,
                                         font_size=FS_SMALL)
        self.about_db_label.configure(wraplength=620, justify=LEFT, anchor=W)
        self.about_db_label.pack(anchor=W, padx=PAD_CARD_X,
                                  pady=(PAD_CARD_Y, PAD_TIGHT))
        self.about_mode_label = make_label(info_card, text="", fg=C_TEXT_SECONDARY,
                                           font_size=FS_SMALL)
        self.about_mode_label.pack(anchor=W, padx=PAD_CARD_X, pady=(0, PAD_CARD_Y))

        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.pack(fill=X)
        make_button(btn_row, "使用教程",
                     command=self.app.show_tutorial).pack(
                        side=LEFT, padx=(0, PAD_TIGHT))
        make_button(btn_row, "功能列表",
                     command=self.app.show_about_detail).pack(
                        side=LEFT, padx=PAD_TIGHT)
        make_button(btn_row, "退出程序",
                     command=self.app.request_exit).pack(
                        side=LEFT, padx=PAD_TIGHT)

    # ==================== 状态同步 ====================
    def reload(self):
        """把当前设置重新读进控件（进入页面时调用）。不触发自动保存。"""
        self._loading = True
        try:
            self.storage_var.set(self.settings.storage_mode)
            self.role_var.set(self.settings.role)
            for seg, key in ((getattr(self, "mode_seg", None),
                              self.settings.storage_mode),
                             (getattr(self, "role_seg", None),
                              self.settings.role),
                             (getattr(self, "anim_seg", None),
                              "on" if config.ANIMATIONS_ENABLED else "off"),
                             (getattr(self, "online_auto_seg", None),
                              "on" if getattr(self.settings,
                                              "online_auto_check", True)
                              else "off"),
                             (getattr(self, "online_clean_seg", None),
                              "on" if getattr(self.settings,
                                              "online_sync_clean", False)
                              else "off")):
                if seg is not None and seg.current() != key:
                    seg.select(key, animate=False)
        except Exception:
            pass
        self._update_db_labels()
        self._refresh_online_cache_label()
        self._loading = False

    def _update_db_labels(self):
        db_str = (str(self.settings._settings_file.parent)
                  if self.settings._settings_file else "未绑定")
        mode = "合并存储" if self.settings.storage_mode == "merged" else "隔离存储"
        role = "玩家" if self.settings.role == "player" else "开发者"
        for widget, text in ((self.db_path_label, db_str),
                             (self.about_db_label, f"数据库位置: {db_str}"),
                             (self.about_mode_label,
                              f"当前模式: {mode} · 用户身份: {role}")):
            try:
                widget.configure(text=text)
            except Exception:
                pass

    def show_about_tab(self):
        self.show_tab("about")

    # ==================== 行为（语义与原 SettingsDialog 一致） ====================
    def on_switch_db(self):
        show_info("切换数据库",
            "切换数据库后需要重新打开整合包。\n\n"
            "原数据库不会被删除，可随时切回。", parent=self.root)
        if self.on_db_action:
            self.on_db_action('switch')

    def on_merge_db(self):
        if self.on_db_action:
            self.on_db_action('merge')

    def on_migrate_legacy(self):
        if self.on_db_action:
            self.on_db_action('migrate_legacy')

    def on_open_db(self):
        db = self.settings._settings_file.parent if self.settings._settings_file else None
        if db and db.exists():
            try:
                open_path(db)
            except Exception:
                pass

    # ==================== 自动保存 ====================
    def _can_persist(self):
        """没有数据库就没有落盘位置：只提示，不弹模态打断。"""
        if self.settings._settings_file is None:
            if hasattr(self.app, "toast"):
                self.app.toast("数据库未初始化，设置无法保存", "warning")
            return False
        return True

    def _on_auto_save(self):
        """单选项一改就落盘：不再需要「保存设置」按钮。"""
        if self._loading:
            return
        changed = (self.storage_var.get() != self.settings.storage_mode
                   or self.role_var.get() != self.settings.role)
        if not changed:
            return          # 重复点同一个单选项不算改动，不刷提示
        if not self._can_persist():
            self.reload()   # 回退控件，保持界面与真实设置一致
            return
        self.save(notify=True)

    def save(self, notify=True):
        """把控件当前值写进 settings 并落盘；返回是否成功。"""
        old_mode = self.settings.storage_mode
        self.settings.storage_mode = self.storage_var.get()
        self.settings.role = self.role_var.get()
        if not self.settings.save():
            show_error("错误",
                "保存设置失败。\n\n"
                "数据库可能尚未初始化，或数据库目录不可写。",
                parent=self.root)
            return False
        self._update_db_labels()
        if notify:
            self._flash_saved()
        if old_mode != self.settings.storage_mode:
            if self.settings.storage_mode == "merged":
                show_warning("提示",
                    "已切换到合并存储。\n\n"
                    "所有整合包将共用同一套预设。\n"
                    "不同整合包的同名枪包可能互相覆盖。\n\n"
                    "重新打开整合包后生效。",
                    parent=self.root)
            else:
                show_info("提示",
                    "已切换到隔离存储。\n\n"
                    "每个整合包使用独立数据库。\n"
                    "重新打开整合包后生效。",
                    parent=self.root)
        if self.on_save_callback:
            self.on_save_callback()
        return True

    def _reset_defaults(self):
        if not self._can_persist():
            return
        self._loading = True
        try:
            self.storage_var.set("isolated")
            self.role_var.set("player")
        finally:
            self._loading = False
        if self.save(notify=True) and hasattr(self.app, "toast"):
            self.app.toast("已恢复默认设置", "info")

    def _flash_saved(self):
        """自动保存回显：先亮一下，再曲线淡回提示色。"""
        try:
            self.saved_label.configure(text="已自动保存",
                                        text_color=C_SUCCESS)
        except Exception:
            return

        def fade():
            def frame(e, raw):
                try:
                    self.saved_label.configure(
                        text_color=lerp_color(C_SUCCESS, C_TEXT_MUTED, e))
                except Exception:
                    pass

            tween(self.saved_label, "saved", 320, frame,
                  on_done=self._reset_saved_text, easing=ease_in_out_cubic,
                  fps=FPS_COLOR)

        try:
            self.root.after(760, fade)
        except Exception:
            fade()

    def _reset_saved_text(self):
        try:
            self.saved_label.configure(text=self._saved_hint(),
                                        text_color=C_TEXT_MUTED)
        except Exception:
            pass
