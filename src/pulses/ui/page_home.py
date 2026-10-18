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

        # ===== 左列：选整合包 → 选预设 =====
        # 预设列表是这一页的主角，Step1 固定高度，剩下的纵向空间全给它。
        left_panel = ctk.CTkFrame(page, fg_color="transparent")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, PAD_GAP))
        left_panel.grid_columnconfigure(0, weight=1)
        left_panel.grid_rowconfigure(0, weight=0, minsize=px(H_STEP1_MIN))
        left_panel.grid_rowconfigure(1, weight=1, minsize=px(H_STEP2_MIN))

        # ===== 右列：详情条 → 主操作 → 枪包 → 日志 =====
        right_panel = ctk.CTkFrame(page, fg_color="transparent")
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.grid_columnconfigure(0, weight=1)
        right_panel.grid_rowconfigure(0, weight=0)   # 详情条
        right_panel.grid_rowconfigure(1, weight=0)   # 同步（按需出现）
        right_panel.grid_rowconfigure(2, weight=0)   # 一键替换
        right_panel.grid_rowconfigure(3, weight=1)   # 枪包列表
        right_panel.grid_rowconfigure(4, weight=0)   # 日志标题
        right_panel.grid_rowconfigure(5, weight=0)   # 日志正文

        # ---------- Step 1 · 整合包 ----------
        pack_group = ctk.CTkFrame(left_panel, fg_color=C_CARD_BG,
                                    corner_radius=R_CARD, border_width=0)
        pack_group.grid(row=0, column=0, sticky="nsew", pady=(0, PAD_GAP))
        make_section_header(pack_group, 1, "整合包").pack(
            fill=X, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        pack_content = ctk.CTkFrame(pack_group, fg_color="transparent")
        pack_content.pack(fill=X, padx=PAD_CARD_X, pady=(0, PAD_CARD_Y))

        # 大拖入框
        self.pack_drop_area = ctk.CTkFrame(pack_content, fg_color=C_INPUT_BG,
                                             corner_radius=R_CONTROL,
                                             border_width=BORDER_W,
                                             border_color=C_BORDER_SOFT)
        self.pack_drop_area.pack(fill=X, pady=(0, PAD_TIGHT))
        # 拖放目标要有 hover 反馈：鼠标进来描边浮一层强调软色
        attach_hover_glow(self.pack_drop_area, base_color=C_BORDER_SOFT,
                          hover_color=C_ACCENT_SOFT)

        self.pack_drop_label = ctk.CTkLabel(
            self.pack_drop_area,
            text="拖入整合包根目录，或整合包内任意文件（自动定位 tacz）",
            text_color=C_TEXT_SECONDARY, font=(config.FONT_FAMILY, FS_SMALL),
            justify=LEFT, anchor="w", fg_color="transparent")
        self.pack_drop_label.pack(fill=X, padx=PAD_GAP, pady=(PAD_GAP, PAD_XS))

        # 路径显示
        self.pack_path_frame, self.pack_path_label = make_display_box(
            self.pack_drop_area, text="未选择", height=H_CONTROL)
        # 拖入框本身是填充灰，路径条再用同一个灰就"隐形"了；
        # 这里抬高一级用白底 + 发丝线，空状态也有明确边界
        try:
            self.pack_path_frame.configure(fg_color=C_PANEL_BG,
                                            border_width=1,
                                            border_color=C_DIVIDER)
        except Exception:
            pass
        self.pack_path_frame.pack(fill=X, padx=PAD_GAP, pady=(0, PAD_TIGHT))

        # 按钮行：只留一个实心主操作，其余走扁平文字按钮
        self.pack_btn_row = ctk.CTkFrame(self.pack_drop_area,
                                          fg_color="transparent")
        pack_btn_row = self.pack_btn_row
        pack_btn_row.pack(fill=X, padx=PAD_INNER, pady=(0, PAD_INNER))

        self.select_pack_btn = make_button(pack_btn_row, "选择整合包",
                                             command=self.select_pack,
                                             width=104, accent=True)
        self.select_pack_btn.pack(side=LEFT, padx=(0, PAD_TIGHT))
        self.recent_toggle_btn = make_text_button(pack_btn_row, "最近",
                                                    command=self.toggle_recent)
        self.recent_toggle_btn.pack(side=LEFT)
        # 打开目录 / 关闭整合包 / 数据库位置：低频操作收进「⋯」
        # （菜单每次打开时按当前状态现算，所以不再需要「隐形按钮」来持有可用状态）
        self.pack_more_btn = make_menu_button(
            pack_btn_row, as_text=True, items=lambda: [
                ("打开整合包目录", self.open_pack_folder
                 if self.current_pack_path else None),
                ("关闭整合包", self.close_pack if self.current_pack_path else None),
                None,
                ("数据库位置", self.open_preset_manager if self.db_ready else None),
            ])
        # 不 pack：鼠标移进这张卡才浮出来（见 _hover_reveal）

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
        self.recent_wrap = ctk.CTkFrame(self.pack_btn_row,
                                         fg_color="transparent", height=1)
        self.recent_wrap.pack_propagate(False)
        self.recent_frame = ctk.CTkFrame(self.recent_wrap, fg_color=C_PANEL_BG,
                                          corner_radius=R_CONTROL, border_width=0)
        self.recent_listbox = Listbox(self.recent_frame, height=6,
                                       bg=C_PANEL_BG, fg=C_TEXT_MAIN,
                                       selectbackground=C_ACCENT_SOFT,
                                       selectforeground=C_ACCENT,
                                       activestyle="none", borderwidth=0,
                                       selectborderwidth=0,
                                       relief='flat', highlightthickness=0,
                                       # 原生 Listbox：必须用负数字号（像素），
                                       # 正数是磅值，会被 tk scaling 再乘一次
                                       font=tk_font(config.FONT_FAMILY, FS_SMALL))
        self.recent_scroll = make_list_scroll(self.recent_frame,
                                               self.recent_listbox, width=8)
        self.recent_listbox.pack(side=LEFT, fill=BOTH, expand=True,
                                  padx=(PAD_TIGHT, 0), pady=PAD_TIGHT)
        self.recent_scroll.pack(side=RIGHT, fill=Y, padx=(2, PAD_TIGHT),
                                 pady=PAD_TIGHT)
        self.recent_listbox.bind('<Double-Button-1>', self.on_recent_double_click)

        # 状态标签
        self.pack_status_label = make_label(pack_content, text="未加载",
                                             fg=C_TEXT_MUTED, font_size=FS_TINY)
        self.pack_status_label.pack(anchor=W, pady=(PAD_XS, 0))
        self.pack_name_label = make_label(pack_content, text="当前预设：无",
                                           fg=C_ACCENT, font_size=FS_SMALL)
        self.pack_name_label.pack(anchor=W, pady=(PAD_MICRO, 0))

        # ---------- Step 2 · 预设管理 ----------
        preset_group = ctk.CTkFrame(left_panel, fg_color=C_CARD_BG,
                                     corner_radius=R_CARD, border_width=0)
        preset_group.grid(row=1, column=0, sticky="nsew")
        make_section_header(preset_group, 2, "预设管理",
                            subtitle="双击看详情").pack(
            fill=X, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        preset_content = ctk.CTkFrame(preset_group, fg_color="transparent")
        preset_content.pack(fill=BOTH, expand=True, padx=PAD_CARD_X,
                            pady=(0, PAD_CARD_Y))

        # 列表直接铺在白卡片上：卡片自己有描边，不再套一层灰底
        preset_list_wrap = ctk.CTkFrame(preset_content, fg_color=C_CARD_BG,
                                         corner_radius=0, border_width=0)
        preset_list_wrap.pack(fill=BOTH, expand=True, pady=(0, PAD_GAP))
        self.preset_cards = CardList(
            preset_list_wrap,
            on_select=self.on_preset_selected,
            on_action=self.on_preset_action,
            on_menu=self.show_preset_context_menu,
            on_open=self.open_preset_detail,
            empty_text="还没有预设",
            empty_hint="先在上面选一个整合包",
            bg=C_CARD_BG)
        self.preset_cards.pack(fill=BOTH, expand=True)

        preset_btn_frame = ctk.CTkFrame(preset_content, fg_color="transparent")
        preset_btn_frame.pack(fill=X)
        self.create_preset_btn = make_button(preset_btn_frame, "＋ 新建",
                                              command=self.create_preset,
                                              state="disabled", accent=True,
                                              width=84)
        self.create_preset_btn.pack(side=LEFT, padx=(0, PAD_TIGHT))
        # 玩家和开发者都要「从云端添加 / 检查更新」；其余低频操作进「⋯」
        self.add_cloud_btn = make_text_button(preset_btn_frame, "从云端",
                                               command=self.open_add_from_cloud,
                                               state="disabled")
        self.add_cloud_btn.pack(side=LEFT)
        self.preset_more_btn = make_menu_button(
            preset_btn_frame, as_text=True, items=lambda: [
                ("检查全部更新", self._online_check_all if self.db_ready else None),
                ("刷新列表", self.refresh_presets if self.db_ready else None),
                ("打开数据库文件夹", self.open_preset_manager
                 if self.db_ready else None),
            ])
        # 不 pack：hover 才出现
        self.loading_label = make_label(preset_btn_frame, text="", fg=C_ACCENT,
                                        font_size=FS_TINY)
        self.loading_label.pack(side=RIGHT, padx=PAD_TIGHT)

        # 两个卡头的「更多」常态隐藏，hover 才出现；枪包列表那个常驻
        self._hover_reveal(pack_group, self.pack_more_btn)
        self._hover_reveal(preset_group, self.preset_more_btn)

        # ---------- Step 3 · 预设详情（横条，放在右列顶部） ----------
        info_group = ctk.CTkFrame(right_panel, fg_color=C_CARD_BG,
                                   corner_radius=R_CARD, border_width=0)
        info_group.grid(row=0, column=0, sticky="ew", pady=(0, PAD_GAP))
        info_head = ctk.CTkFrame(info_group, fg_color="transparent")
        info_head.pack(fill=X, padx=PAD_CARD_X, pady=(PAD_CARD_Y, 0))
        make_section_header(info_head, 3, "预设详情").pack(side=LEFT)
        # 「打开详情」改成一个明确的实心按钮：改名/改版本/看差异都在里面
        self.detail_btn = make_button(info_head, "打开详情",
                                       command=self._open_current_detail,
                                       accent=True, width=96, height=30,
                                       font_size=FS_SMALL)
        self.detail_btn.pack(side=RIGHT)
        # 开发者常用：换完枪包直接去 tacz 里看结果
        self.tacz_head_btn = make_text_button(
            info_head, "打开 TACZ", command=self.open_tacz_folder,
            state="disabled")
        self.tacz_head_btn.pack(side=RIGHT, padx=(0, PAD_TIGHT))
        if not self.is_developer:
            self.tacz_head_btn.pack_forget()

        info_body = ctk.CTkFrame(info_group, fg_color="transparent")
        info_body.pack(fill=X, padx=PAD_CARD_X, pady=(PAD_TIGHT, PAD_CARD_Y))

        title_row = ctk.CTkFrame(info_body, fg_color="transparent")
        title_row.pack(fill=X)
        self.preset_name_label = make_label(
            title_row, text="未选择", fg=C_TEXT_MAIN, font_size=FS_TITLE, bold=True)
        self.preset_name_label.pack(side=LEFT)
        self.preset_status_label = make_label(
            title_row, text="未应用", fg=C_TEXT_MUTED, font_size=FS_SMALL)
        self.preset_status_label.pack(side=RIGHT)

        meta_row = ctk.CTkFrame(info_body, fg_color="transparent")
        meta_row.pack(fill=X, pady=(PAD_TIGHT, 0))

        ver_box = ctk.CTkFrame(meta_row, fg_color="transparent")
        ver_box.pack(side=LEFT, fill=X, expand=True)
        make_label(ver_box, text="版本", fg=C_TEXT_MUTED,
                   font_size=FS_TINY).pack(side=LEFT)
        self.version_entry = make_entry(ver_box, width=158)
        self.version_entry.pack(side=LEFT, padx=(PAD_TIGHT, 0))
        self.version_entry.bind('<Return>', lambda e: self.save_version())
        # 「保存」只属于这个输入框：做成尾随在框内的文字按钮，
        # 而不是另起一个和「版本」平级的独立按钮
        self.save_version_btn = make_text_button(ver_box, "保存",
                                                  command=self.save_version,
                                                  state="disabled")
        try:
            self.save_version_btn.place(in_=self.version_entry, relx=1.0,
                                        rely=0.5, x=-6, anchor="e")
        except Exception:
            self.save_version_btn.pack(side=LEFT, padx=(PAD_XS, 0))
        # 「当前版本」不单独占一行了：状态行已经说明应用情况，
        # 这里留一个不参与布局的标签，兼容 packs.py 里原有的 configure 调用。
        self.preset_version_label = make_label(
            ver_box, text="", fg=C_TEXT_MUTED, font_size=FS_TINY)

        cloud_box = ctk.CTkFrame(meta_row, fg_color="transparent")
        cloud_box.pack(side=RIGHT)
        make_label(cloud_box, text="云端", fg=C_TEXT_MUTED,
                   font_size=FS_TINY).pack(side=LEFT)
        self.preset_online_label = make_label(
            cloud_box, text="未绑定", fg=C_TEXT_MUTED, font_size=FS_SMALL)
        self.preset_online_label.pack(side=LEFT, padx=(PAD_TIGHT, PAD_XS))
        self.source_btn = make_text_button(cloud_box, "填写链接",
                                            command=self._open_current_source)
        self.source_btn.pack(side=LEFT)

        # ---------- 主操作 ----------
        # 玩家：一键替换。开发者：发布到云端（外加一颗次要的一键替换）。
        # 身份不同动作本来就不同，只换颜色的话一眼看不出自己在哪个身份。
        self.aux_row = ctk.CTkFrame(right_panel, fg_color="transparent")
        self.aux_row.grid(row=1, column=0, sticky="ew", pady=(0, PAD_TIGHT))
        self.aux_row.grid_remove()

        self.sync_btn = make_button(self.aux_row, "同步更新",
                                     command=self._sync_current_preset,
                                     accent=False, height=36,
                                     font_size=FS_SMALL)
        self.sync_btn.pack(side=LEFT, fill=X, expand=True)
        self.sync_btn.pack_forget()

        self.apply_alt_btn = make_button(self.aux_row, "一键替换",
                                          command=self.apply_preset,
                                          state="disabled", accent=False,
                                          height=36, font_size=FS_SMALL)
        self.apply_alt_btn.pack(side=LEFT, fill=X, expand=True,
                                padx=(PAD_TIGHT, 0))
        self.apply_alt_btn.pack_forget()

        # 高度固定：44(按钮) + 24(进度条带) —— 进度出现/消失都不改布局，
        # 否则下面的枪包列表和日志会整体往下跳 31px。
        self.action_row = ctk.CTkFrame(right_panel, fg_color="transparent",
                                        height=44 + 24)
        self.action_row.grid_propagate(False)
        self.action_row.grid(row=2, column=0, sticky="ew", pady=(0, PAD_GAP))

        self.apply_btn = make_button(self.action_row, "一键替换",
                                      command=self.apply_preset,
                                      state="disabled", accent=True,
                                      height=44, font_size=FS_SUBHEAD)
        self.apply_btn.place(relx=0.0, rely=0.0, relwidth=1.0)

        self.publish_btn = make_button(self.action_row, "发布到云端",
                                        command=self._publish_current,
                                        state="disabled", accent=True,
                                        height=44, font_size=FS_SUBHEAD)
        self.publish_btn.place(relx=0.0, rely=0.0, relwidth=1.0)
        self.publish_btn.place_forget()

        # 进度条占的是预留带，不挤任何人
        self.inline_progress = ctk.CTkProgressBar(
            self.action_row, height=6, corner_radius=R_PROGRESS,
            fg_color=C_PANEL_ALT_BG, progress_color=C_ACCENT)
        self.inline_progress.set(0)
        self.inline_label = make_label(self.action_row, text="",
                                        fg=C_TEXT_SECONDARY, font_size=FS_TINY)



        # ---------- 枪包列表 ----------
        gunpack_group = ctk.CTkFrame(right_panel, fg_color=C_CARD_BG,
                                      corner_radius=R_CARD, border_width=0)
        gunpack_group.grid(row=3, column=0, sticky="nsew", pady=(0, PAD_GAP))
        gunpack_head = ctk.CTkFrame(gunpack_group, fg_color="transparent")
        gunpack_head.pack(fill=X, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        make_section_header(gunpack_head, 4, "枪包列表").pack(side=LEFT)
        self.gunpack_count_label = make_label(
            gunpack_head, text="共 0 个", fg=C_TEXT_MUTED, font_size=FS_TINY)
        self.gunpack_count_label.pack(side=LEFT, padx=(PAD_GAP, 0))
        self.gunpack_more_btn = make_menu_button(
            gunpack_head, as_text=True, items=lambda: [
                ("刷新枪包列表", self.refresh_gunpacks
                 if self.current_selected_preset else None),
                ("全部刷新", self.refresh_all),
                None,
                ("打开 TACZ 目录", self.open_tacz_folder
                 if self.tacz_path else None),
            ])
        self.gunpack_more_btn.pack(side=RIGHT)

        gunpack_content = ctk.CTkFrame(gunpack_group, fg_color="transparent")
        gunpack_content.pack(fill=BOTH, expand=True, padx=PAD_CARD_X,
                             pady=(0, PAD_CARD_Y))
        gunpack_list_wrap = ctk.CTkFrame(gunpack_content, fg_color=C_INPUT_BG,
                                          corner_radius=R_CONTROL, border_width=0)
        gunpack_list_wrap.pack(fill=BOTH, expand=True)
        self.gunpack_empty = EmptyState(gunpack_list_wrap, title="还没有枪包",
                                         hint="先选一个整合包，再选一个预设",
                                         bg=C_INPUT_BG)
        self.gunpack_listbox = Listbox(gunpack_list_wrap, height=6,
                                        bg=C_INPUT_BG, fg=C_TEXT_MAIN,
                                        selectbackground=C_ACCENT_SOFT,
                                        selectforeground=C_ACCENT,
                                        activestyle="none", borderwidth=0,
                                        selectborderwidth=0,
                                        relief='flat', highlightthickness=0,
                                        font=tk_font(config.FONT_FAMILY, FS_BODY))
        self.gunpack_listbox.bind('<Double-Button-1>', self.on_gunpack_open)
        self.gunpack_scroll = make_list_scroll(gunpack_list_wrap,
                                                self.gunpack_listbox)
        self.gunpack_listbox.pack(side=LEFT, fill=BOTH, expand=True,
                                   padx=(PAD_INNER, 0), pady=PAD_INNER)
        self.gunpack_scroll.pack(side=RIGHT, fill=Y, padx=(2, PAD_XS),
                                  pady=PAD_INNER)

        # ---------- 日志 ----------
        log_head = ctk.CTkFrame(right_panel, fg_color="transparent")
        log_head.grid(row=4, column=0, sticky="ew")
        make_label(log_head, text="日志", fg=C_TEXT_MUTED,
                   font_size=FS_TINY).pack(side=LEFT, padx=(PAD_XS, 0))
        make_text_button(log_head, "清空", command=self.clear_log).pack(side=RIGHT)
        self.home_log_text = ctk.CTkTextbox(
            right_panel, height=H_HOME_LOG, fg_color=C_PANEL_BG,
            border_color=C_BORDER_SOFT, border_width=BORDER_W,
            corner_radius=R_CONTROL, text_color=C_TEXT_SECONDARY,
            font=(FONT_FAMILY_MONO, FS_SMALL), wrap="word")
        self.home_log_text.grid(row=5, column=0, sticky="ew", pady=(PAD_XS, 0))

        return page

    def _hover_reveal(self, host, button, delay_ms=160):
        """卡头按钮常态隐藏，鼠标进入这张卡才浮出（不参与布局，不会顶动行）。"""
        state = {"job": None}

        def _inside():
            try:
                px, py = host.winfo_pointerxy()
                rx, ry = host.winfo_rootx(), host.winfo_rooty()
                return (rx <= px <= rx + host.winfo_width()
                        and ry <= py <= ry + host.winfo_height())
            except Exception:
                return False

        def _show(_event=None):
            if state["job"] is not None:
                try:
                    self.root.after_cancel(state["job"])
                except Exception:
                    pass
                state["job"] = None
            try:
                button.place(relx=1.0, rely=0.5, anchor="e", x=-6)
            except Exception:
                pass

        def _maybe_hide(_event=None):
            def _hide():
                state["job"] = None
                if not _inside():
                    try:
                        button.place_forget()
                    except Exception:
                        pass
            try:
                state["job"] = self.root.after(delay_ms, _hide)
            except Exception:
                pass

        for seq, fn in (("<Enter>", _show), ("<Leave>", _maybe_hide)):
            try:
                host.bind(seq, fn, add="+")
            except Exception:
                pass

    def _publish_current(self):
        name = getattr(self, "current_selected_preset", None)
        if not name:
            return
        if bool(getattr(self.settings, "online_publish_preview", False)):
            self.open_publish_dialog(name)
        else:
            self._publish_now(name)

    def _apply_role_actions(self):
        """身份决定主操作：玩家「一键替换」，开发者「发布到云端」。"""
        dev = bool(getattr(self, "is_developer", False))
        try:
            try:
                if dev:
                    self.tacz_head_btn.pack(side=RIGHT, padx=(0, PAD_TIGHT),
                                            before=self.detail_btn)
                else:
                    self.tacz_head_btn.pack_forget()
            except Exception:
                pass
            if dev:
                self.apply_btn.place_forget()
                self.publish_btn.place(relx=0.0, rely=0.0, relwidth=1.0)
                self.apply_alt_btn.pack(side=LEFT, fill=X, expand=True,
                                        padx=(PAD_TIGHT, 0))
                self.aux_row.grid()
            else:
                self.publish_btn.place_forget()
                self.apply_btn.place(relx=0.0, rely=0.0, relwidth=1.0)
                self.apply_alt_btn.pack_forget()
                if not self.sync_btn.winfo_ismapped():
                    self.aux_row.grid_remove()
        except Exception:
            pass

    def _sync_current_preset(self):
        name = getattr(self, "current_selected_preset", None)
        if name:
            self._sync_now(name)

    # ==================== 当前预设的两个入口 ====================
    def _open_current_detail(self):
        name = getattr(self, "current_selected_preset", None)
        if name:
            self.open_preset_detail(name)

    def _open_current_source(self):
        name = getattr(self, "current_selected_preset", None)
        if name:
            self.open_source_dialog(name)

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
    RECENT_H = 172   # 展开后的固定高度（列表 6 行 + 内边距）

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
        """展开 / 收起：直接落位。

        原来每帧改 place 高度做补间，浮层里的整个 Listbox 会跟着重绘，
        条目一多就像"卡住"；这里改成一次性设置高度，观感反而更利落。
        """
        try:
            self._recent_height = float(target)
            self.recent_wrap.place_configure(height=max(1, int(target)))
        except Exception:
            pass
        if hide_after:
            try:
                self.recent_frame.pack_forget()
            except Exception:
                pass
        return

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
        # 展开/收起用弹簧：末端轻轻过冲一点再落定，手感更"活"
        tween(self.recent_wrap, "height", 240, frame, done,
              easing=ease_out_spring)

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
