"""主界面：Step1/2/3 + 右列 + 拖入 + 最近面板 + 导入"""
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


class HomePageMixin:
    """主界面：Step1/2/3 + 右列 + 拖入 + 最近面板 + 导入"""

    # ==================== 主界面（Step 1/2/3 + 枪包列表） ====================
    def _build_home_page(self):
        page = ctk.CTkFrame(self.stack.canvas, fg_color=C_WINDOW_BG)
        page.grid_rowconfigure(0, weight=1)
        page.grid_columnconfigure(0, weight=0, minsize=px(LEFT_COL_W))
        page.grid_columnconfigure(1, weight=1)

        left_panel = ctk.CTkFrame(page, fg_color="transparent")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, PAD_GAP))
        # 纵向预算：Step1/Step3 固定高度，剩余空间全部给 Step2 的预设列表，
        # 这样窗口变小/DPI 放大时先压缩列表，Step3 卡片不会被裁（见 H_STEP*_MIN）
        left_panel.grid_columnconfigure(0, weight=1)
        left_panel.grid_rowconfigure(0, weight=0, minsize=px(H_STEP1_MIN))
        left_panel.grid_rowconfigure(1, weight=1, minsize=px(H_STEP2_MIN))
        left_panel.grid_rowconfigure(2, weight=0, minsize=px(H_STEP3_MIN))

        right_panel = ctk.CTkFrame(page, fg_color="transparent")
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.grid_columnconfigure(0, weight=1)
        right_panel.grid_rowconfigure(0, weight=1)
        right_panel.grid_rowconfigure(1, weight=0)

        # ===== 整合包分组（大拖入框） =====
        pack_group = ctk.CTkFrame(left_panel, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                    border_width=BORDER_W, border_color=C_BORDER_SOFT)
        pack_group.grid(row=0, column=0, sticky="nsew", pady=(0, PAD_GAP))
        attach_hover_glow(pack_group)
        make_label(pack_group, text="Step 1 · 整合包", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        pack_content = ctk.CTkFrame(pack_group, fg_color="transparent")
        pack_content.pack(fill=X, padx=PAD_CARD_X, pady=(0, PAD_CARD_Y))

        # 大拖入框
        self.pack_drop_area = ctk.CTkFrame(pack_content, fg_color=C_PANEL_ALT_BG,
                                             corner_radius=R_CARD, border_width=BORDER_W,
                                             border_color=C_BORDER_SOFT)
        self.pack_drop_area.pack(fill=X, pady=(0, PAD_TIGHT))

        self.pack_drop_label = ctk.CTkLabel(
            self.pack_drop_area,
            text="Step 1 · 拖入整合包根目录\n"
                 "或整合包内任意文件（自动定位 tacz）",
            text_color=C_TEXT_SECONDARY, font=(config.FONT_FAMILY, FS_BODY),
            justify=LEFT, anchor="w", fg_color="transparent")
        self.pack_drop_label.pack(fill=X, padx=PAD_GAP, pady=(PAD_GAP, PAD_XS))

        # 路径显示
        self.pack_path_frame, self.pack_path_label = make_display_box(
            self.pack_drop_area, text="未选择", height=H_CONTROL)
        self.pack_path_frame.pack(fill=X, padx=PAD_GAP, pady=(0, PAD_TIGHT))

        # 按钮行
        self.pack_btn_row = ctk.CTkFrame(self.pack_drop_area,
                                          fg_color="transparent")
        pack_btn_row = self.pack_btn_row
        pack_btn_row.pack(fill=X, padx=PAD_INNER, pady=(0, PAD_GAP))

        self.select_pack_btn = make_button(pack_btn_row, "选择",
                                             command=self.select_pack,
                                             width=60, accent=True)
        self.select_pack_btn.pack(side=LEFT, padx=(0, PAD_XS))
        self.open_pack_btn = make_button(pack_btn_row, "目录",
                                           command=self.open_pack_folder,
                                           width=52, state="disabled")
        self.open_pack_btn.pack(side=LEFT, padx=(0, PAD_XS))
        self.close_pack_btn = make_button(pack_btn_row, "关闭",
                                            command=self.close_pack,
                                            width=56)
        self.close_pack_btn.pack(side=LEFT, padx=(0, PAD_XS))
        self.recent_toggle_btn = make_button(pack_btn_row, "▼ 最近",
                                               command=self.toggle_recent,
                                               width=70)
        self.recent_toggle_btn.pack(side=LEFT)

        # 绑定 DND 到拖入框和提示文字
        if HAS_DND:
            for w in (self.pack_drop_area, self.pack_drop_label):
                try:
                    w.drop_target_register(DND_FILES)
                    w.dnd_bind('<<Drop>>', self.on_pack_drop)
                except Exception:
                    pass

        # 最近打开：做成「不参与布局」的下拉浮层。
        # 挂在按钮行下面、用 place 定位 —— place 不影响 pack/grid 的排版，
        # 所以展开/收起时整页不会重新布局。
        # （之前是 pack + 高度补间：每帧改高度都要重排整页，Windows 上就是
        #   又慢又闪白，用户指着这个按钮反馈的。）
        self.recent_wrap = ctk.CTkFrame(self.pack_btn_row,
                                         fg_color="transparent", height=1)
        self.recent_wrap.pack_propagate(False)
        self.recent_frame = ctk.CTkFrame(self.recent_wrap, fg_color=C_PANEL_ALT_BG,
                                          corner_radius=R_CONTROL, border_width=BORDER_W,
                                          border_color=C_BORDER_SOFT)
        self.recent_listbox = Listbox(self.recent_frame, height=4,
                                       bg=C_PANEL_ALT_BG, fg=C_TEXT_MAIN,
                                       selectbackground=C_ACCENT_SOFT,
                                       selectforeground=C_ACCENT,
                                       relief='flat', highlightthickness=0,
                                       font=(config.FONT_FAMILY,
                                             max(1, int(FS_SMALL * config.UI_SCALE))))
        self.recent_scroll = make_list_scroll(self.recent_frame,
                                               self.recent_listbox, width=8)
        self.recent_listbox.pack(side=LEFT, fill=BOTH, expand=True,
                                  padx=(PAD_TIGHT, 0), pady=PAD_TIGHT)
        self.recent_scroll.pack(side=RIGHT, fill=Y, padx=(2, PAD_TIGHT),
                                 pady=PAD_TIGHT)
        self.recent_listbox.bind('<Double-Button-1>', self.on_recent_double_click)

        # 状态标签
        self.pack_status_label = make_label(pack_content, text="状态: 未加载",
                                             fg=C_ERROR, font_size=FS_SMALL)
        self.pack_status_label.pack(anchor=W, pady=(PAD_XS, 0))
        self.pack_name_label = make_label(pack_content, text="当前预设: 无",
                                           fg=C_ACCENT, font_size=FS_SMALL)
        self.pack_name_label.pack(anchor=W, pady=(PAD_MICRO, 0))

        # ===== 预设管理 =====
        preset_group = ctk.CTkFrame(left_panel, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                     border_width=BORDER_W, border_color=C_BORDER_SOFT)
        preset_group.grid(row=1, column=0, sticky="nsew", pady=(0, PAD_GAP))
        attach_hover_glow(preset_group)
        make_label(preset_group, text="Step 2 · 预设管理", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        preset_content = ctk.CTkFrame(preset_group, fg_color="transparent")
        preset_content.pack(fill=BOTH, expand=True, padx=PAD_CARD_X,
                            pady=(0, PAD_CARD_Y))

        preset_list_wrap = ctk.CTkFrame(preset_content, fg_color=C_CARD_BG,
                                         corner_radius=R_CONTROL, border_width=BORDER_W,
                                         border_color=C_BORDER_SOFT)
        preset_list_wrap.pack(fill=BOTH, expand=True, pady=(0, PAD_GAP))
        attach_hover_glow(preset_list_wrap)
        self.preset_listbox = Listbox(preset_list_wrap, height=4,
                                       bg=C_CARD_BG, fg=C_TEXT_MAIN,
                                       selectbackground=C_ACCENT_SOFT,
                                       selectforeground=C_ACCENT,
                                       relief='flat', highlightthickness=0,
                                       font=(config.FONT_FAMILY,
                                             max(1, int(FS_BODY * config.UI_SCALE))))
        self.preset_scroll = make_list_scroll(preset_list_wrap,
                                               self.preset_listbox)
        self.preset_listbox.pack(side=LEFT, fill=BOTH, expand=True,
                                  padx=(PAD_XS, 0), pady=PAD_XS)
        self.preset_scroll.pack(side=RIGHT, fill=Y, padx=(2, PAD_XS),
                                 pady=PAD_XS)
        self.preset_listbox.bind('<<ListboxSelect>>', self.on_preset_selected)
        self.preset_listbox.bind('<Button-3>', self.show_preset_context_menu)

        # 拖入框：预设/更新包
        self.drop_area = ctk.CTkFrame(preset_content, fg_color=C_PANEL_ALT_BG,
                                       corner_radius=R_CARD, border_width=BORDER_W,
                                       border_color=C_BORDER_SOFT, height=H_DROP_AREA)
        self.drop_area.pack(fill=X, pady=(0, PAD_GAP))
        self.drop_area.pack_propagate(False)
        attach_hover_glow(self.drop_area)
        self.drop_label = ctk.CTkLabel(
            self.drop_area,
            text="Step 2 · 导入预设包 / 更新包\n"
                 "拖入 .fgcpack / .fgcupdate，或点击此处选择",
            text_color=C_TEXT_SECONDARY, font=(config.FONT_FAMILY, FS_TINY),
            justify=LEFT, anchor="w", fg_color="transparent")
        self.drop_label.pack(fill=BOTH, expand=True, padx=PAD_INNER, pady=PAD_INNER)
        self.drop_label.bind('<Button-1>', lambda e: self.select_import_file())
        self.drop_area.bind('<Button-1>', lambda e: self.select_import_file())
        if HAS_DND:
            try:
                self.drop_area.drop_target_register(DND_FILES)
                self.drop_area.dnd_bind('<<Drop>>', self.on_drop_file)
                self.drop_label.drop_target_register(DND_FILES)
                self.drop_label.dnd_bind('<<Drop>>', self.on_drop_file)
            except Exception:
                pass

        preset_btn_frame = ctk.CTkFrame(preset_content, fg_color="transparent")
        preset_btn_frame.pack(fill=X)
        self.create_preset_btn = make_button(preset_btn_frame, "＋ 创建",
                                              command=self.create_preset,
                                              state="disabled", width=68)
        self.create_preset_btn.pack(side=LEFT, padx=(0, PAD_XS))
        self.export_preset_btn = make_button(preset_btn_frame, "导出",
                                              command=self.export_preset,
                                              state="disabled", width=56)
        self.export_preset_btn.pack(side=LEFT, padx=PAD_XS)
        self.export_incremental_btn = make_button(preset_btn_frame, "更新",
                                                   command=self.export_incremental,
                                                   state="disabled", width=56)
        self.export_incremental_btn.pack(side=LEFT, padx=PAD_XS)
        self.refresh_preset_btn = make_button(preset_btn_frame, "刷新",
                                               command=self.refresh_presets,
                                               state="disabled", width=52)
        self.refresh_preset_btn.pack(side=LEFT, padx=PAD_XS)
        self.open_db_btn = make_button(preset_btn_frame, "数据库",
                                        command=self.open_preset_manager,
                                        state="disabled", width=64)
        self.open_db_btn.pack(side=LEFT, padx=PAD_XS)
        self.loading_label = make_label(preset_btn_frame, text="", fg=C_ACCENT,
                                        font_size=FS_TINY)
        self.loading_label.pack(side=LEFT, padx=PAD_TIGHT)

        # ===== 预设详情 =====
        info_group = ctk.CTkFrame(left_panel, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                   border_width=BORDER_W, border_color=C_BORDER_SOFT)
        info_group.grid(row=2, column=0, sticky="ew")
        attach_hover_glow(info_group)
        make_label(info_group, text="Step 3 · 预设详情", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        info_content = ctk.CTkFrame(info_group, fg_color="transparent")
        info_content.pack(fill=X, padx=PAD_CARD_X, pady=(0, PAD_CARD_Y))

        self.preset_name_label = make_label(info_content, text="预设: 未选择",
                                             fg=C_ACCENT, font_size=FS_SUBHEAD,
                                             bold=True)
        self.preset_name_label.pack(anchor=W)
        self.preset_version_label = make_label(info_content, text="版本号: 无",
                                                fg=C_TEXT_SECONDARY, font_size=FS_SMALL)
        self.preset_version_label.pack(anchor=W, pady=(PAD_MICRO, 0))
        self.preset_status_label = make_label(info_content, text="状态: 未应用",
                                               fg=C_TEXT_SECONDARY, font_size=FS_SMALL)
        self.preset_status_label.pack(anchor=W, pady=(PAD_MICRO, 0))

        version_edit_frame = ctk.CTkFrame(info_content, fg_color="transparent")
        version_edit_frame.pack(fill=X, pady=(PAD_INNER, 0))
        make_label(version_edit_frame, text="Step 3 · 版本号:", fg=C_TEXT_MAIN,
                    font_size=FS_SMALL).pack(side=LEFT)
        self.version_entry = make_entry(version_edit_frame, width=120)
        self.version_entry.pack(side=LEFT, fill=X, expand=True,
                                padx=(PAD_TIGHT, PAD_TIGHT))
        self.version_entry.bind('<Return>', lambda e: self.save_version())
        self.save_version_btn = make_button(version_edit_frame, "保存",
                                             command=self.save_version,
                                             state="disabled", width=60)
        self.save_version_btn.pack(side=RIGHT)

        # ===== 枪包列表 =====
        gunpack_group = ctk.CTkFrame(right_panel, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                      border_width=BORDER_W, border_color=C_BORDER_SOFT)
        gunpack_group.grid(row=0, column=0, sticky="nsew", pady=(0, PAD_GAP))
        attach_hover_glow(gunpack_group)
        make_label(gunpack_group, text="枪包列表", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        gunpack_content = ctk.CTkFrame(gunpack_group, fg_color="transparent")
        gunpack_content.pack(fill=BOTH, expand=True, padx=PAD_CARD_X,
                             pady=(0, PAD_CARD_Y))

        toolbar_frame = ctk.CTkFrame(gunpack_content, fg_color="transparent")
        toolbar_frame.pack(fill=X, pady=(0, PAD_TIGHT))
        self.gunpack_count_label = make_label(toolbar_frame, text="共 0 个枪包",
                                               fg=C_TEXT_MAIN, font_size=FS_SMALL)
        self.gunpack_count_label.pack(side=LEFT)

        self.refresh_gunpack_btn = make_button(toolbar_frame, "刷新",
                                                command=self.refresh_gunpacks,
                                                state="disabled", width=56)
        self.refresh_gunpack_btn.pack(side=RIGHT)

        self.open_tacz_btn = make_button(toolbar_frame, "打开TACZ",
                                          command=self.open_tacz_folder,
                                          state="disabled", width=84)
        self.open_tacz_btn.pack(side=RIGHT, padx=(0, PAD_XS))

        self.refresh_all_btn = make_button(toolbar_frame, "全部刷新",
                                            command=self.refresh_all, width=76)
        self.refresh_all_btn.pack(side=RIGHT, padx=(0, PAD_XS))

        gunpack_list_wrap = ctk.CTkFrame(gunpack_content, fg_color=C_CARD_BG,
                                          corner_radius=R_CONTROL, border_width=BORDER_W,
                                          border_color=C_BORDER_SOFT)
        gunpack_list_wrap.pack(fill=BOTH, expand=True)
        attach_hover_glow(gunpack_list_wrap)
        self.gunpack_listbox = Listbox(gunpack_list_wrap, height=6,
                                        bg=C_CARD_BG, fg=C_TEXT_MAIN,
                                        selectbackground=C_ACCENT_SOFT,
                                        selectforeground=C_ACCENT,
                                        relief='flat', highlightthickness=0,
                                        font=(config.FONT_FAMILY,
                                              max(1, int(FS_BODY * config.UI_SCALE))))
        self.gunpack_listbox.bind('<Double-Button-1>', self.on_gunpack_open)
        self.gunpack_scroll = make_list_scroll(gunpack_list_wrap,
                                                self.gunpack_listbox)
        self.gunpack_listbox.pack(side=LEFT, fill=BOTH, expand=True,
                                   padx=(PAD_XS, 0), pady=PAD_XS)
        self.gunpack_scroll.pack(side=RIGHT, fill=Y, padx=(2, PAD_XS),
                                  pady=PAD_XS)

        self.apply_btn = make_button(right_panel, "Step 4 · 一键替换",
                                      command=self.apply_preset,
                                      state="disabled", accent=True)
        self.apply_btn.grid(row=1, column=0, sticky="ew")

        # ===== 分割线 + 日志栏 =====
        # 需求：分割线上面是「一键替换 + 工具条按钮 + 枪包列表」，下面放日志
        divider = ctk.CTkFrame(right_panel, fg_color=C_BORDER_SOFT, height=1)
        divider.grid(row=2, column=0, sticky="ew", pady=(PAD_GAP, PAD_GAP))

        home_log_group = ctk.CTkFrame(right_panel, fg_color=C_CARD_BG,
                                       corner_radius=R_CARD, border_width=BORDER_W,
                                       border_color=C_BORDER_SOFT)
        home_log_group.grid(row=3, column=0, sticky="ew")
        attach_hover_glow(home_log_group)
        log_head = ctk.CTkFrame(home_log_group, fg_color="transparent")
        log_head.pack(fill=X, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        make_label(log_head, text="日志", fg=C_TEXT_MUTED,
                    font_size=FS_TINY).pack(side=LEFT)
        make_button(log_head, "清空", command=self.clear_log,
                     width=48).pack(side=RIGHT)
        self.home_log_text = ctk.CTkTextbox(
            home_log_group, height=H_HOME_LOG, fg_color=C_INPUT_BG,
            border_color=C_BORDER_SOFT, border_width=BORDER_W,
            corner_radius=R_CONTROL, text_color=C_TEXT_MAIN,
            font=(FONT_FAMILY_MONO, FS_SMALL), wrap="word")
        self.home_log_text.pack(fill=X, padx=PAD_CARD_X, pady=(0, PAD_CARD_Y))

        return page

    # ==================== 整合包拖入 ====================
    def on_pack_drop(self, event):
        """拖入整合包根目录，或整合包内任意文件/文件夹，自动向上定位 tacz"""
        if self.is_applying or self.loading_presets:
            return
        if not self.db_ready:
            show_warning("提示", "数据库未初始化")
            return
        try:
            files = self.root.tk.splitlist(event.data)
        except Exception:
            files = [event.data]
        if not files:
            return
        raw = files[0].strip()
        # 去掉可能的尾部斜杠和引号
        raw = raw.strip('"').strip("'").rstrip('\\/')
        if not raw:
            return
        try:
            drop_path = Path(raw)
        except Exception:
            return

        tacz_path = locate_tacz_by_path(drop_path)
        if not tacz_path:
            show_error("未找到 tacz",
                f"从该路径未能定位到 tacz 文件夹：\n{drop_path}\n\n"
                f"请拖入整合包根目录，或整合包内的任意文件/文件夹。")
            return
        pack_root = tacz_path.parent
        self.log_manager.log(
            f"从拖入路径定位到整合包: {pack_root}", 'INFO')
        self.load_pack(pack_root)

    # ==================== 打开文件夹 ====================
    def open_pack_folder(self):
        if not self.current_pack_path:
            show_warning("提示", "请先选择一个整合包")
            return
        try:
            if self.current_pack_path.exists():
                open_path(self.current_pack_path)
                self.log_manager.log(f"已打开整合包路径: {self.current_pack_path}",
                                      'INFO', verbose=True)
            else:
                show_error("错误", f"路径不存在: {self.current_pack_path}")
        except Exception as e:
            self.log_manager.log(f"打开整合包路径失败: {e}", 'ERROR')
            show_error("错误", f"打开失败: {e}")

    def on_gunpack_open(self, event=None):
        """双击枪包：在文件管理器里定位它（已应用 → tacz 目录，否则预设目录）。"""
        try:
            sel = self.gunpack_listbox.curselection()
            if not sel:
                return
            name = self.gunpack_listbox.get(sel[0])
            candidates = []
            if self.tacz_path:
                candidates.append(self.tacz_path / name)
            preset_dir = self._current_preset_dir()
            if preset_dir:
                candidates.append(preset_dir / name)
            for path in candidates:
                if path.exists():
                    if open_path(path):
                        self.log_manager.log(f"已打开枪包位置: {path}", 'INFO',
                                              verbose=True)
                    return
            show_warning("提示", f"找不到枪包位置: {name}")
        except Exception as exc:
            self.log_manager.log(f"打开枪包位置失败: {exc}", 'ERROR')

    def _current_preset_dir(self):
        try:
            if not self.preset_manager or not self.current_selected_preset:
                return None
            info = self.preset_manager.presets.get(self.current_selected_preset)
            return Path(info["path"]) if info else None
        except Exception:
            return None

    def open_tacz_folder(self):
        if not self.tacz_path:
            show_warning("提示", "请先选择一个整合包")
            return
        if not self.tacz_path.exists():
            show_error("错误", f"TACZ 路径不存在: {self.tacz_path}")
            return
        try:
            open_path(self.tacz_path)
            self.log_manager.log(f"已打开 TACZ 文件夹: {self.tacz_path}", 'INFO',
                                      verbose=True)
        except Exception as e:
            self.log_manager.log(f"打开 TACZ 文件夹失败: {e}", 'ERROR')
            show_error("错误", f"打开失败: {e}")

    # ==================== 最近打开 ====================
    RECENT_H = 118   # 展开后的固定高度（列表 5 行 + 内边距）

    def toggle_recent(self):
        if self.recent_visible:
            self.recent_visible = False
            self.recent_toggle_btn.configure(text="▼ 最近")
            self._animate_recent(1, hide_after=True)
        else:
            self.recent_visible = True
            self.update_recent_list()
            self.recent_toggle_btn.configure(text="▲ 最近")
            self.recent_frame.pack(fill=BOTH, expand=True)
            try:
                self.recent_wrap.place(relx=0.0, rely=1.0, relwidth=1.0,
                                        height=1)
                self.recent_wrap.lift()
            except Exception:
                pass
            self._animate_recent(self.RECENT_H)

    def _animate_recent(self, target, hide_after=False):
        """折叠面板的高度补间：0 -> 118 展开，118 -> 0 收起。"""
        start = float(getattr(self, "_recent_height", 1.0))
        if start == target:
            try:
                self.recent_wrap.configure(height=max(1, int(target)))
            except Exception:
                pass
            if hide_after:
                self.recent_frame.pack_forget()
            return

        def frame(e, raw):
            self._recent_height = lerp(start, float(target), e)
            try:
                # 只改浮层自己的高度：兄弟控件不动，页面不重排
                self.recent_wrap.place_configure(height=max(1, int(self._recent_height)))
            except Exception:
                pass

        def done():
            self._recent_height = float(target)
            try:
                self.recent_wrap.place_configure(height=max(1, int(target)))
            except Exception:
                pass
            if hide_after:
                try:
                    self.recent_frame.pack_forget()
                except Exception:
                    pass
                try:
                    self.recent_wrap.place_forget()   # 完全撤下，不占位
                except Exception:
                    pass

        frame(0.0, 0.0)
        tween(self.recent_wrap, "height", 190, frame, done, easing=ease_out_cubic)

    def update_recent_list(self):
        if not hasattr(self, 'recent_listbox'):
            return
        self.recent_listbox.delete(0, END)
        if not self.recent_manager:
            self.recent_listbox.insert(END, "(数据库未初始化)")
            self.recent_listbox.itemconfig(0, fg=C_TEXT_MUTED)
            return
        for item in self.recent_manager.get_all():
            name = item.get('name', '未知')
            path = item.get('path', '')
            self.recent_listbox.insert(END, f"{name}  ({path})")
        if self.recent_listbox.size() == 0:
            self.recent_listbox.insert(END, "(暂无最近打开)")
            self.recent_listbox.itemconfig(0, fg=C_TEXT_MUTED)

    def on_recent_double_click(self, event):
        sel = self.recent_listbox.curselection()
        if not sel or not self.recent_manager:
            return
        idx = sel[0]
        recent = self.recent_manager.get_all()
        if idx >= len(recent):
            return
        path = recent[idx].get('path', '')
        if not Path(path).exists():
            show_error("错误", f"路径不存在: {path}")
            return
        self.load_pack(Path(path))

    # ==================== 拖放（预设/更新包） ====================
    def on_drop_file(self, event):
        if self.is_applying or self.loading_presets:
            return
        try:
            files = self.root.tk.splitlist(event.data)
        except Exception:
            files = [event.data]
        if not files:
            return
        raw = files[0].strip('"').strip("'")
        if not raw:
            return
        self.handle_import_file(Path(raw))

    def select_import_file(self):
        if self.is_applying or self.loading_presets:
            return
        if not self.preset_manager:
            show_warning("提示", "请先选择整合包")
            return
        p = filedialog.askopenfilename(
            title="选择预设包或增量更新包",
            filetypes=[("Pulses Swap 包", "*.fgcpack *.fgcupdate"),
                       ("完整预设包", "*.fgcpack"),
                       ("增量更新包", "*.fgcupdate"),
                       ("所有文件", "*.*")])
        if p:
            self.handle_import_file(Path(p))

    def handle_import_file(self, file_path: Path):
        if not self.preset_manager:
            show_warning("提示", "请先选择整合包")
            return
        if self.is_applying:
            show_warning("操作进行中", "请等待当前操作完成")
            return
        if not file_path.exists():
            show_error("错误", f"文件不存在: {file_path}")
            return
        suffix = file_path.suffix.lower()
        if suffix == '.fgcupdate':
            self.do_import_incremental(file_path)
        elif suffix == '.fgcpack':
            self.do_import_preset(file_path)
        else:
            try:
                with zipfile.ZipFile(file_path, 'r') as zf:
                    if '_increment.json' in zf.namelist():
                        self.do_import_incremental(file_path)
                    else:
                        self.do_import_preset(file_path)
            except Exception as e:
                show_error("错误", f"无法识别文件: {e}")
