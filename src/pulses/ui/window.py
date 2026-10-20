"""窗口骨架：透明度防护 / 界面装配 / 页面切换 / 菜单退出"""
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
from ..dialogs import _OVERLAY_STACK
from ..managers import *
from ..pages import *



# ==================== 主窗口 ====================


class WindowMixin:
    """窗口骨架：透明度防护 / 界面装配 / 页面切换 / 菜单退出"""

    def _center_window(self):
        """把主窗口放在当前屏幕正中间（启动后调用一次）。"""
        try:
            self.root.update_idletasks()
            w = max(1, self.root.winfo_width())
            h = max(1, self.root.winfo_height())
            sw = max(w, self.root.winfo_screenwidth())
            sh = max(h, self.root.winfo_screenheight())
            x = max(0, (sw - w) // 2)
            y = max(0, (sh - h) // 2 - px(12))
            self.root.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    def _disable_win11_transparency(self):
        """兼容旧调用：立刻把主窗口与所有子窗口刷成不透明。"""
        if not IS_WINDOWS:
            return
        refresh_window_opacity(self.root)

    def _install_opacity_guard(self):
        """Win11 半透明防护：事件驱动 + 兜底轮询。

        只在启动时关一次是不够的 —— 窗口失焦（有弹窗在前面）、重新映射、
        切换主题时，DWM 会重新评估窗口材质，Mica 会自己回来。这里：
          · 焦点/映射/可见性/尺寸变化时补一次（250ms 节流，避免频繁调用）
          · 另外每 2 秒兜一次底，保证任何触发路径都盖得住
        """
        if not IS_WINDOWS:
            return
        self._opacity_last = 0.0
        for seq in ("<Map>", "<FocusIn>", "<Visibility>", "<Configure>"):
            try:
                self.root.bind(seq, self._on_opacity_event, add="+")
            except Exception:
                pass
        self._opacity_tick()
        self._opacity_guard_logged = False

    def _on_opacity_event(self, _event=None):
        now = time.perf_counter()
        if now - getattr(self, "_opacity_last", 0.0) < 0.25:
            return
        self._opacity_last = now
        n = refresh_window_opacity(self.root)
        if not getattr(self, "_opacity_guard_logged", False):
            self._opacity_guard_logged = True
            try:
                self.log_manager.log(
                    f"Win11 窗口材质已设为不透明（覆盖 {n} 个窗口）",
                    'INFO', verbose=True)
            except Exception:
                pass

    def _opacity_tick(self):
        refresh_window_opacity(self.root)
        try:
            self.root.after(8000, self._opacity_tick)
        except Exception:
            pass

    # ==================== UI 构建 ====================
    def setup_ui(self):
        # ===== 骨架：左侧可折叠栏（悬浮层）+ 右侧页面区 =====
        main_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        main_frame.pack(fill=BOTH, expand=True, padx=PAD_WINDOW, pady=PAD_WINDOW)

        # 覆盖层宿主：所有窗口内弹窗都 place 在这个 frame 上（连侧边栏一起盖住，保证模态）
        self.overlay_host = main_frame
        self.active_page = None
        set_overlay_host(self)

        # 折叠态只占 60px；展开是 place 在内容上层的浮层，不参与 grid 排版。
        # 所以展开/收起时右侧工作区不会跳、不会重新计算宽度。
        self.sidebar_rail_w = px(60)
        self.sidebar_open_w = px(292)
        self._sidebar_expanded = False
        self._sidebar_jobs = {}
        self._sidebar_sections = []
        self._show_account_box = bool(getattr(self, "is_developer", False))

        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=0,
                                        minsize=self.sidebar_rail_w)
        main_frame.grid_columnconfigure(1, weight=1)

        self.content_col = ctk.CTkFrame(main_frame, fg_color="transparent")
        self.content_col.grid(row=0, column=1, sticky="nsew")
        self.content_col.grid_columnconfigure(0, weight=1)
        self.content_col.grid_rowconfigure(0, weight=1)
        self.content_col.grid_rowconfigure(1, weight=0)

        # ===== 侧边栏本体 =====
        # 外层用原生 Frame 当“裁剪窗口”：CTk 的 place 不接受 width/height，
        # 而原生 Frame 可以逐帧改宽度；里面的 CTkFrame 负责圆角/配色。
        self.sidebar_shell = Frame(main_frame, bg=C_WINDOW_BG,
                                      bd=0, highlightthickness=0)
        self.sidebar_shell.place(x=0, y=0, width=self.sidebar_rail_w,
                                 relheight=1.0)
        sidebar = ctk.CTkFrame(self.sidebar_shell, fg_color=C_CARD_BG,
                                corner_radius=R_CARD,
                                border_width=BORDER_W,
                                border_color=C_BORDER_SOFT)
        sidebar.pack(fill=BOTH, expand=True)
        self.sidebar = sidebar

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.pack(fill=X, padx=PAD_XS, pady=(PAD_GAP, PAD_TIGHT))
        self.sidebar_logo = ctk.CTkFrame(
            brand, fg_color=C_ACCENT, width=px(34), height=px(34),
            corner_radius=px(10))
        self.sidebar_logo.pack(side=LEFT)
        self.sidebar_logo.pack_propagate(False)
        make_label(self.sidebar_logo, text="P", fg=C_TEXT_INVERSE,
                   font_size=FS_SUBHEAD, bold=True).pack(expand=True)
        self.sidebar_brand_text = ctk.CTkFrame(brand, fg_color="transparent")
        # 不 pack：折叠时不存在，展开时由 _set_sidebar_sections 放出来
        make_label(self.sidebar_brand_text, text=PROJECT_NAME, fg=C_TEXT_MAIN,
                   font_size=FS_SMALL, bold=True).pack(anchor=W)
        make_label(self.sidebar_brand_text, text=f"v{VERSION}", fg=C_TEXT_MUTED,
                   font_size=FS_TINY).pack(anchor=W)
        self.identity_badge = make_label(
            self.sidebar_brand_text, text="玩家", fg=C_TEXT_SECONDARY,
            font_size=FS_TINY, bold=True)
        self.identity_badge.pack(anchor=W, pady=(PAD_MICRO, 0))

        # 导航：折叠态图标，展开态图标 + 文字
        self.nav = SidebarNav(
            sidebar,
            [("home", "主界面"), ("manage", "管理"),
             ("settings", "设置"), ("log", "日志")],
            command=self._on_nav_select, expanded=False,
            bg_color=C_CARD_BG, pill_color=C_ACCENT_SOFT,
            hover_color=C_ACCENT_SOFT, text_color=C_TEXT_MAIN,
            active_text_color=C_ACCENT, collapsed_width=60)
        self.nav.pack(fill=X, padx=PAD_XS)

        # 当前整合包 / 预设：保留旧属性名，侧边栏收起时整块隐藏
        session_card = ctk.CTkFrame(sidebar, fg_color=C_CARD_BG,
                                     corner_radius=R_CONTROL,
                                     border_width=0)
        session_card.pack(fill=X, padx=PAD_XS, pady=(PAD_GAP, PAD_TIGHT))
        self.session_card = session_card
        make_label(session_card, text="当前整合包", fg=C_TEXT_MUTED,
                   font_size=FS_TINY).pack(anchor=W, padx=PAD_GAP,
                                           pady=(PAD_TIGHT, PAD_MICRO))
        self.sb_pack_label = make_label(session_card, text="未选择",
                                         fg=C_TEXT_MAIN, font_size=FS_SMALL,
                                         bold=True)
        self.sb_pack_label.pack(anchor=W, padx=PAD_GAP)
        self.sb_status_label = make_label(session_card, text="未加载",
                                           fg=C_ERROR, font_size=FS_TINY)
        self.sb_status_label.pack(anchor=W, padx=PAD_GAP, pady=(PAD_MICRO, 0))
        self.sb_preset_label = make_label(session_card, text="预设 · 无",
                                           fg=C_ACCENT, font_size=FS_TINY)
        self.sb_preset_label.pack(anchor=W, padx=PAD_GAP,
                                   pady=(PAD_MICRO, PAD_TIGHT))
        self._sidebar_sections.append((session_card, dict(
            fill=X, padx=PAD_XS, pady=(PAD_GAP, PAD_TIGHT))))

        # 蓝奏云账号：登录信息 / 退登 / 上传额度
        account_box = ctk.CTkFrame(sidebar, fg_color=C_PANEL_ALT_BG,
                                    corner_radius=R_CONTROL)
        account_box.pack(fill=X, padx=PAD_XS)
        self.account_box = account_box
        head = ctk.CTkFrame(account_box, fg_color="transparent")
        head.pack(fill=X, padx=PAD_GAP, pady=(PAD_TIGHT, PAD_MICRO))
        make_label(head, text="蓝奏云", fg=C_TEXT_SECONDARY,
                   font_size=FS_TINY, bold=True).pack(side=LEFT)
        self.sb_conn_label = make_label(head, text="未登录", fg=C_TEXT_MUTED,
                                        font_size=FS_TINY)
        self.sb_conn_label.pack(side=RIGHT)
        self.identity_account = make_label(account_box, text="",
                                            fg=C_TEXT_MAIN,
                                            font_size=FS_SMALL, bold=True)
        self.identity_account.pack(anchor=W, padx=PAD_GAP)
        self.sb_quota_label = make_label(account_box, text="容量 --",
                                          fg=C_TEXT_MUTED, font_size=FS_TINY)
        self.sb_quota_label.pack(anchor=W, padx=PAD_GAP, pady=(PAD_MICRO, 0))
        acct_btns = ctk.CTkFrame(account_box, fg_color="transparent")
        acct_btns.pack(fill=X, padx=PAD_GAP, pady=(PAD_TIGHT, PAD_TIGHT))
        self.sb_login_btn = make_text_button(acct_btns, "登录",
                                              command=self.open_identity_dialog)
        self.sb_login_btn.pack(side=LEFT)
        self.identity_btn = make_text_button(acct_btns, "账号",
                                              command=self.open_identity_dialog)
        self.identity_btn.pack(side=LEFT, padx=(PAD_TIGHT, 0))
        self.sb_logout_btn = make_text_button(acct_btns, "退出",
                                               command=self._sidebar_logout)
        self.sb_logout_btn.pack(side=RIGHT)
        self._sidebar_sections.append((account_box, dict(
            fill=X, padx=PAD_XS, pady=(0, PAD_TIGHT))))

        # 云端预设列表：可选中，显示名称 / 状态 / 大小 / 日期
        cloud_box = ctk.CTkFrame(sidebar, fg_color="transparent")
        cloud_box.pack(fill=BOTH, expand=True, padx=PAD_XS)
        self.sb_cloud_box = cloud_box
        cloud_head = ctk.CTkFrame(cloud_box, fg_color="transparent")
        cloud_head.pack(fill=X, pady=(0, PAD_XS))
        make_label(cloud_head, text="云端预设", fg=C_TEXT_SECONDARY,
                   font_size=FS_TINY, bold=True).pack(side=LEFT)
        self.sb_cloud_count = make_label(cloud_head, text="0 个",
                                          fg=C_TEXT_MUTED, font_size=FS_TINY)
        self.sb_cloud_count.pack(side=RIGHT)
        # 先把底部「全部更新」占住，再让列表 expand；反过来的话列表
        # 会把按钮顶到窗口外面（pack 的经典顺序坑）。
        self.sb_cloud_all_btn = make_text_button(
            cloud_box, "全部更新", command=self._sidebar_update_all)
        self.sb_cloud_all_btn.pack(side=BOTTOM, anchor=W, pady=(PAD_XS, 0))
        self.sb_cloud_scroll = ctk.CTkScrollableFrame(
            cloud_box, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=C_BORDER_SOFT,
            scrollbar_button_hover_color=C_BORDER)
        self.sb_cloud_scroll.pack(fill=BOTH, expand=True)
        # 空态不贴在列表顶部：居中放一张“下一步”卡，留白才不会显得空。
        self.sb_cloud_empty = ctk.CTkFrame(cloud_box, fg_color="transparent")
        make_label(self.sb_cloud_empty, text="还没有云端预设",
                   fg=C_TEXT_SECONDARY, font_size=FS_SMALL,
                   bold=True).pack(anchor="center")
        self.sb_cloud_empty_hint = make_label(
            self.sb_cloud_empty, text="从分享链接添加，或去管理里发布",
            fg=C_TEXT_MUTED, font_size=FS_TINY, justify="center")
        self.sb_cloud_empty_hint.pack(anchor="center", pady=(PAD_MICRO, PAD_TIGHT))
        self.sb_cloud_empty_btn = make_text_button(
            self.sb_cloud_empty, "从云端添加",
            command=self.open_add_from_cloud)
        self.sb_cloud_empty_btn.pack(anchor="center")
        self.sb_cloud_empty.place(relx=0.5, rely=0.42, anchor="center")
        self._sidebar_sections.append((cloud_box, dict(
            fill=BOTH, expand=True, padx=PAD_XS)))

        # 身份滑动开关
        role_box = ctk.CTkFrame(sidebar, fg_color="transparent",
                                 height=px(92))
        role_box.pack_propagate(False)
        role_box.pack(fill=X, padx=PAD_GAP, pady=(PAD_TIGHT, PAD_GAP))
        self.role_box = role_box
        make_label(role_box, text="身份", fg=C_TEXT_MUTED,
                   font_size=FS_TINY).pack(anchor=W)
        self.role_switch = RoleSwitch(
            role_box, command=self._on_role_switch,
            role=getattr(self.settings, "role", "player"),
            bg_color=C_CARD_BG)
        self.role_switch.pack(fill=X, pady=(PAD_MICRO, 0))
        self.sb_role_hint = make_label(
            role_box, text="玩家下载 · 开发者上传", fg=C_TEXT_MUTED,
            font_size=FS_TINY)
        self.sb_role_hint.pack(anchor=W)
        self._sidebar_sections.append((role_box, dict(
            side=BOTTOM, fill=X, padx=PAD_GAP, pady=(PAD_TIGHT, PAD_GAP))))
        # 身份开关是页脚：必须排在云端列表之前 pack(side=BOTTOM)，
        # 否则 expand=True 的列表会把它顶出窗口底部。
        try:
            cloud_item = next(item for item in self._sidebar_sections
                              if item[0] is cloud_box)
            role_item = next(item for item in self._sidebar_sections
                             if item[0] is role_box)
            self._sidebar_sections.remove(cloud_item)
            self._sidebar_sections.remove(role_item)
            self._sidebar_sections.append(role_item)
            self._sidebar_sections.append(cloud_item)
        except Exception:
            pass

        # 折叠态底部的身份小圆钮：点一下展开
        self.sidebar_rail_role = ctk.CTkButton(
            sidebar, text="玩", width=px(36), height=px(36),
            corner_radius=px(18), fg_color=C_ACCENT_SOFT,
            hover_color=C_ACCENT_SOFT, text_color=C_ACCENT,
            font=(config.FONT_FAMILY, FS_SMALL, "bold"),
            command=lambda: self._sidebar_expand("rail"))
        self.sidebar_rail_role.pack(side=BOTTOM, pady=(0, PAD_GAP))

        # 展开态的遮罩：独立 Toplevel + alpha，不参与 Tk 布局，能真正“压暗”工作区
        self._sidebar_dim = None
        self._sidebar_dim_alpha = 0.0
        self._dim_token = 0

        # ===== 右侧内容 =====
        self.page_host = ctk.CTkFrame(self.content_col, fg_color="transparent")
        self.page_host.grid(row=0, column=0, sticky="nsew")
        self.stack = SlideStack(self.page_host, bg_color=C_WINDOW_BG,
                                 duration_ms=260)
        self.page_canvas = self.stack.canvas

        # 全局状态条：固定高度，永远只显示一行；进度条出现/消失不改变布局
        self.status_bar = ctk.CTkFrame(self.content_col,
                                        fg_color=C_CARD_BG,
                                        corner_radius=R_CONTROL,
                                        border_width=BORDER_W,
                                        border_color=C_BORDER_SOFT,
                                        height=28)
        self.status_bar.grid(row=1, column=0, sticky="ew", pady=(PAD_TIGHT, 0))
        self.status_bar.grid_propagate(False)
        self.status_dot = make_label(self.status_bar, text="●",
                                      fg=C_TEXT_MUTED, font_size=FS_TINY)
        self.status_dot.pack(side=LEFT, padx=(PAD_GAP, PAD_XS))
        self.progress_label = make_label(
            self.status_bar, text="", fg=C_TEXT_SECONDARY,
            font_size=FS_TINY)
        self.progress_label.pack(side=LEFT, fill=X, expand=True)
        self.progress_bar = ctk.CTkProgressBar(
            self.status_bar, height=5, corner_radius=R_PROGRESS,
            fg_color=C_PANEL_ALT_BG, progress_color=C_ACCENT, width=px(140))
        # 不 pack：show_progress 时临时出现，状态条高度不变
        self._status_job = None
        self._status_text = ""
        self._status_kind = "info"
        self._status_seq = 0

        # ===== 页面 =====
        self.settings_page = None
        self.pages = {}
        self.pages["home"] = self._build_home_page()
        self.pages["log"] = self._build_log_page()
        # 主界面右下角的日志栏与「日志」页共用同一份日志流
        if getattr(self, "home_log_text", None) is not None:
            self.log_manager.attach(self.home_log_text)
        self.pages["manage"] = self._build_manage_page()
        # 架构要求：底部是完整日志；单行状态由全局状态条负责，二者不打架。
        self.show_full_log = True
        try:
            self.log_manager.set_show_full(True)
            if getattr(self, "log_toggle_btn", None) is not None:
                self.log_toggle_btn.configure(text="显示单条日志")
            if getattr(self, "home_log_toggle_btn", None) is not None:
                self.home_log_toggle_btn.configure(text="显示单条")
        except Exception:
            pass
        self.settings_page = SettingsPage(
            self.stack.canvas, self,
            on_save_callback=self._on_settings_saved,
            on_db_action=self._on_db_action)
        self.pages["settings"] = self.settings_page.frame
        for key in ("home", "manage", "settings", "log"):
            self.stack.add(key, self.pages[key])
        # 四页先各自布局一次（这笔开销只付一次，别落在切换动画的第一帧上）
        self.stack.current = "home"
        self.stack.prewarm()

        # ===== 新手引导注册 =====
        self.guide = GuideManager(self.root)
        self.guide.register(
            "step1_select_pack", [self.pack_drop_area],
            desc="Step 1 · 拖入整合包根目录，或点「选择整合包」")
        self.guide.register(
            "step2_create_preset", [self.create_preset_btn],
            desc="Step 2 · 点「＋ 新建」建预设，再把枪包拖进去")
        self.guide.register(
            "step3_apply", [self.apply_btn],
            desc="点击「一键替换」启用这个预设")

        self._bind_sidebar_events()
        # 启动就是折叠态：账号/云端列表/身份滑块先收起来，只留图标栏
        self._set_sidebar_sections(False)
        self._update_nav_state(None, animate=False)
        self.show_page("home", animate=False)
        self._play_entrance()
        # 启动后 1.2 秒内用户通常还在看窗口，不需要悬浮展开
        try:
            self.root.after(900, self._sidebar_arm_hover)
        except Exception:
            self._sidebar_hover_armed = True

    def _on_nav_select(self, key):
        """点导航后先切页，再收起浮层，避免展开的侧边栏挡住新页面。"""
        self.show_page(key)
        self._sidebar_collapse()

    # ==================== 侧边栏：折叠 / 展开 ====================
    def _bind_sidebar_events(self):
        self._sidebar_hover_armed = False

        def on_enter(_event=None):
            if not getattr(self, "_sidebar_hover_armed", False):
                return
            if _OVERLAY_STACK:
                return
            self._sidebar_cancel("expand")
            self._sidebar_jobs["expand"] = self.root.after(
                90, lambda: self._sidebar_maybe_expand())

        def on_leave(_event=None):
            if not self._sidebar_expanded:
                return
            self._sidebar_cancel("collapse")
            self._sidebar_jobs["collapse"] = self.root.after(
                360, self._sidebar_maybe_collapse)

        for widget in (self.sidebar,):
            widget.bind("<Enter>", on_enter, add="+")
            widget.bind("<Leave>", on_leave, add="+")
        self.sidebar.bind("<Button-1>", self._sidebar_click_focus, add="+")
        # 子控件不会把 Enter/Leave 冒泡给侧边栏：用 root 的 Motion 做
        # 指针位置判定，图标/账号/列表上悬停也能展开，移出子控件也能收起。
        self._sidebar_motion_last = 0.0
        try:
            self.root.bind("<Motion>", self._sidebar_on_motion, add="+")
            self.root.bind("<Leave>", self._sidebar_on_root_leave, add="+")
        except Exception:
            pass
        try:
            self.root.bind("<Escape>", lambda e: self._sidebar_collapse(),
                           add="+")
        except Exception:
            pass
        try:
            self.root.bind("<Configure>", self._sidebar_on_root_resize,
                           add="+")
        except Exception:
            pass

    def _sidebar_on_motion(self, _event=None):
        if not getattr(self, "_sidebar_hover_armed", False):
            return
        if _OVERLAY_STACK:
            return
        # 不做 35ms 节流：单次合成 Motion 会被吞掉，表现为“第一次进入
        # 侧栏不展开”。这里只做指针判定和 after 排期，本身很便宜。
        inside = self._pointer_in_sidebar()
        if inside:
            self._sidebar_cancel("collapse")
            if not self._sidebar_expanded and "expand" not in self._sidebar_jobs:
                self._sidebar_jobs["expand"] = self.root.after(
                    80, self._sidebar_maybe_expand)
        else:
            self._sidebar_cancel("expand")
            if self._sidebar_expanded and "collapse" not in self._sidebar_jobs:
                self._sidebar_jobs["collapse"] = self.root.after(
                    300, self._sidebar_maybe_collapse)

    def _sidebar_on_root_leave(self, _event=None):
        if not self._sidebar_expanded or _OVERLAY_STACK:
            return
        self._sidebar_cancel("expand")
        self._sidebar_jobs["collapse"] = self.root.after(
            220, self._sidebar_maybe_collapse)

    def _sidebar_arm_hover(self):
        self._sidebar_hover_armed = True

    def _sidebar_cancel(self, key):
        job = self._sidebar_jobs.pop(key, None)
        if job:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass

    def _sidebar_click_focus(self, event=None):
        # 点侧边栏内部（包括空白处）不应触发收起
        self._sidebar_cancel("collapse")

    def _pointer_in_sidebar(self):
        try:
            x, y = self.sidebar.winfo_pointerxy()
            rx, ry = self.sidebar.winfo_rootx(), self.sidebar.winfo_rooty()
            return (rx <= x <= rx + self.sidebar.winfo_width()
                    and ry <= y <= ry + self.sidebar.winfo_height())
        except Exception:
            return False

    def _sidebar_maybe_expand(self):
        self._sidebar_jobs.pop("expand", None)
        if self._sidebar_expanded or _OVERLAY_STACK:
            return
        if not self._pointer_in_sidebar():
            return
        self._sidebar_expand("hover")

    def _sidebar_maybe_collapse(self):
        self._sidebar_jobs.pop("collapse", None)
        if not self._sidebar_expanded:
            return
        if self._pointer_in_sidebar():
            return
        # 键盘焦点还在侧边栏里（例如用 Tab 操作登录框）时先别收
        try:
            focus = self.root.focus_get()
            node = focus
            while node is not None:
                if node is self.sidebar:
                    return
                node = getattr(node, "master", None)
        except Exception:
            pass
        self._sidebar_collapse()

    def _set_sidebar_sections(self, visible):
        if visible:
            if self.sidebar_brand_text.winfo_manager() == "":
                self.sidebar_brand_text.pack(side=LEFT, padx=(PAD_TIGHT, 0))
            # 必须按列表顺序重排：身份页脚要先 pack(side=BOTTOM)，
            # 云端列表再 expand，否则列表会把页脚顶出窗口。
            for widget, _opts in self._sidebar_sections:
                if widget.winfo_manager():
                    widget.pack_forget()
            for widget, opts in self._sidebar_sections:
                if (widget is getattr(self, "account_box", None)
                        and not self._show_account_box):
                    continue
                widget.pack(**opts)
            if self.sidebar_rail_role.winfo_manager():
                self.sidebar_rail_role.pack_forget()
        else:
            if self.sidebar_brand_text.winfo_manager():
                self.sidebar_brand_text.pack_forget()
            for widget, _opts in self._sidebar_sections:
                if widget.winfo_manager():
                    widget.pack_forget()
            if not self.sidebar_rail_role.winfo_manager():
                self.sidebar_rail_role.pack(side=BOTTOM, pady=(0, PAD_GAP))
            # 预布局阶段可能已经把收起前的文字画到画布上；pack_forget 只
            # unmap，不会主动重绘父级背景，X11 下会留下“残影文字”。
            try:
                self.sidebar.update_idletasks()
                self.sidebar.configure(fg_color=C_CARD_BG)
                self.sidebar.update_idletasks()
            except Exception:
                pass
        self.nav.set_expanded(visible)

    def _sidebar_expand(self, reason="hover"):
        target = self._sidebar_open_width()
        width_now = self.sidebar_shell.winfo_width() or self.sidebar_rail_w
        # 标志位可能因为上一次动画被打断而停在 True、宽度却还是 60：
        # 不能只看标志，否则会永久卡在半展开态。
        if self._sidebar_expanded and width_now >= target - 2:
            return
        self._sidebar_expanded = True
        self._sidebar_cancel("collapse")
        self._set_sidebar_sections(True)
        self._show_dim(True)
        start = width_now

        def frame(e, raw):
            width = int(round(lerp(start, target, e)))
            try:
                self.sidebar_shell.place_configure(width=width)
            except Exception:
                pass

        def done():
            try:
                self.sidebar_shell.place_configure(width=target)
            except Exception:
                pass

        tween(self.sidebar_shell, "sidebar_width", 190, frame,
              easing=ease_out_cubic, fps=FPS_MOVE, on_done=done)
        self.sidebar.lift()
        self._dim_token = int(getattr(self, "_dim_token", 0)) + 1
        token = self._dim_token
        try:
            self.root.after(
                210, lambda: (self._dim_content(True)
                              if token == self._dim_token
                              and self._sidebar_expanded else None))
        except Exception:
            pass

    def _sidebar_collapse(self, *args):
        width_now = self.sidebar_shell.winfo_width() or self.sidebar_open_w
        if not self._sidebar_expanded and width_now <= self.sidebar_rail_w + 2:
            return
        self._sidebar_expanded = False
        self._sidebar_cancel("expand")
        self._show_dim(False)
        start = width_now
        target = self.sidebar_rail_w

        def frame(e, raw):
            width = int(round(lerp(start, target, e)))
            try:
                self.sidebar_shell.place_configure(width=width)
            except Exception:
                pass

        def done():
            try:
                self.sidebar_shell.place_configure(width=target)
            except Exception:
                pass
            self._set_sidebar_sections(False)

        tween(self.sidebar_shell, "sidebar_width", 170, frame,
              easing=ease_out_cubic, fps=FPS_MOVE, on_done=done)
        # 文字先收，避免宽度变窄时文字被裁成半截
        self._set_sidebar_sections(False)
        self._dim_token = int(getattr(self, "_dim_token", 0)) + 1
        token = self._dim_token
        try:
            self.root.after(
                190, lambda: (self._dim_content(False)
                              if token == self._dim_token
                              and not self._sidebar_expanded else None))
        except Exception:
            pass

    # 非 Windows 没有可靠的 Toplevel alpha：用“把工作区底色压深一档”
    # 代替黑色遮罩。这样不会盖住内容，也能看出侧边栏是浮在上层的。
    _DIM_COLORS = {
        C_WINDOW_BG.lower(): "#DEE0E4",
        C_CARD_BG.lower(): "#E9EAED",
        C_PANEL_BG.lower(): "#E9EAED",
        C_INPUT_BG.lower(): "#DFE2E5",
        C_PANEL_ALT_BG.lower(): "#D7DADE",
    }

    def _dim_content(self, on):
        if IS_WINDOWS:
            return
        if on:
            if getattr(self, "_dim_saved", None):
                return
            saved = []
            # 只压暗当前可见页；遍历全部页面会把展开动画卡在半路
            page = getattr(self, "pages", {}).get(
                getattr(self, "active_page", None))
            stack = [page] if page is not None else []
            while stack:
                node = stack.pop()
                try:
                    stack.extend(node.winfo_children())
                except Exception:
                    pass
                # AnimatedButton 的颜色不在 cget("fg_color") 里，单独处理
                for attr in ("_base_color", "_hover_target", "_press_color",
                             "_current"):
                    try:
                        value = getattr(node, attr, None)
                    except Exception:
                        continue
                    if isinstance(value, str) and value.lower() in self._DIM_COLORS:
                        saved.append((node, attr, value))
                        try:
                            setattr(node, attr,
                                    self._DIM_COLORS[value.lower()])
                        except Exception:
                            pass
                for prop in ("fg_color", "hover_color", "bg"):
                    try:
                        value = node.cget(prop)
                    except Exception:
                        continue
                    if not isinstance(value, str):
                        continue
                    new = self._DIM_COLORS.get(value.lower())
                    if new is None:
                        continue
                    saved.append((node, prop, value))
                    try:
                        node.configure(**{prop: new})
                    except Exception:
                        pass
            self._dim_saved = saved
        else:
            saved = getattr(self, "_dim_saved", None)
            self._dim_saved = None
            for node, prop, value in reversed(saved or []):
                try:
                    if prop.startswith("_"):
                        setattr(node, prop, value)
                    else:
                        node.configure(**{prop: value})
                except Exception:
                    pass

    def _show_dim(self, show):
        # Tk 的 Toplevel 在 X11/无合成器环境下 -alpha 可能被忽略，直接变一块
        # 全黑遮罩。主平台是 Windows，那里 DWM 合成稳定；其它平台宁可不压暗，
        # 也不能把工作区盖死。
        if not IS_WINDOWS:
            return
        try:
            if self._sidebar_dim is None:
                top = Toplevel(self.root)
                top.overrideredirect(True)
                top.configure(bg="black")
                top.withdraw()
                try:
                    top.attributes("-alpha", 0.0)
                    got = float(top.attributes("-alpha"))
                except Exception:
                    got = 1.0
                if got > 0.6:
                    top.destroy()
                    return
                top.bind("<Button-1>", lambda e: self._sidebar_collapse())
                top.bind("<Enter>", lambda e: self._sidebar_collapse())
                top.bind("<Motion>", lambda e: self._sidebar_collapse())
                self._sidebar_dim = top
            top = self._sidebar_dim
            if show:
                self._position_dim()
                top.deiconify()
                top.lift()
                self._dim_to(0.14, 160)
            else:
                self._dim_to(0.0, 140, hide=True)
        except Exception:
            pass

    def _position_dim(self):
        top = getattr(self, "_sidebar_dim", None)
        if top is None:
            return
        try:
            # 只压暗「侧边栏右侧」的工作区：展开后的侧边栏本身要保持在
            # 遮罩之上，否则用户点不到登录/导航。
            overlap = max(0, self._sidebar_open_width() - self.sidebar_rail_w)
            x = self.content_col.winfo_rootx() + overlap
            y = self.content_col.winfo_rooty()
            w = max(1, self.content_col.winfo_width() - overlap)
            h = max(1, self.content_col.winfo_height())
            top.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    def _sidebar_open_width(self):
        return min(self.sidebar_open_w,
                   max(self.sidebar_rail_w,
                       self.root.winfo_width() - px(120)))

    def _dim_to(self, target, duration, hide=False):
        top = getattr(self, "_sidebar_dim", None)
        if top is None:
            return
        start = float(getattr(self, "_sidebar_dim_alpha", 0.0))
        steps = max(1, int(duration / 30))
        interval = max(16, int(duration / steps))
        state = {"i": 0}

        def tick():
            state["i"] += 1
            alpha = lerp(start, target, state["i"] / steps)
            self._sidebar_dim_alpha = alpha
            try:
                top.attributes("-alpha", max(0.0, min(1.0, alpha)))
            except Exception:
                pass
            if state["i"] < steps:
                try:
                    top.after(interval, tick)
                except Exception:
                    pass
            elif hide:
                try:
                    top.withdraw()
                except Exception:
                    pass

        tick()

    def _sidebar_on_root_resize(self, event=None):
        if event is not None and getattr(event, "widget", None) is not self.root:
            return
        if self._sidebar_expanded:
            self._position_dim()

    def _sidebar_logout(self):
        if getattr(self, "_sidebar_expanded", False):
            self._sidebar_collapse()
        if self.online is None:
            return
        if not ask_yes_no(
                self.root, "退出蓝奏云",
                "退出后会删除本机保存的账号和密码。\n"
                "云端文件不会受影响，下次发布需要重新登录。"):
            return
        try:
            self.online.logout(forget=True)
        except Exception:
            pass
        self._set_role("player")
        self.toast("已退出蓝奏云", "info")
        self._update_identity_ui()


    # ==================== 入场动画 ====================
    def _play_entrance(self):
        """启动入场：当前页从右侧轻轻滑入，侧边栏滑块同步淡入。"""
        # 入场只做滑块淡入：搬页面窗口项（整棵控件树）每帧要重排子窗口，
        # 是这里最贵的一类操作，放在启动第一帧最容易看出卡顿。
        self._update_nav_state(self.active_page, animate=True)

    # ==================== 页面切换 ====================
    PAGE_ORDER = ("home", "manage", "settings", "log")

    def show_page(self, name, animate=True):
        """切换右侧页面：整页在 Canvas 里推入/推出，侧边栏滑块同步滑动。

        方向按需求走「点哪边内容就往哪边走」：
          点下面/右面的选项 → 内容往下/右走（新页从下/右方进来）
          点上面/左面的选项 → 内容往上/左走（新页从上/左方进来）
        侧边栏是竖排，所以页面竖着滑（axis="y"）。
        """
        if name not in self.pages or name == self.active_page:
            return
        if getattr(self, "recent_visible", False):
            try:
                self.hide_recent()
            except Exception:
                pass
        cancel_tween(self.stack.canvas, "entrance")
        previous = self.active_page
        direction = 1
        if previous is not None:
            try:
                # 点下面/右面的选项 → 内容往下/右走 → 新页从上方/左方进来
                # （SlideStack 里 direction=+1 表示新页起点在 -span）
                direction = (1 if self.PAGE_ORDER.index(name)
                             > self.PAGE_ORDER.index(previous) else -1)
            except ValueError:
                direction = 1
        self.active_page = name
        self._update_nav_state(name, animate=animate)
        self.stack.show(name, animate=animate, direction=direction, axis="y")
        if animate:
            # 切页动画结束后记一次实测帧率（完整日志可见）：
            # 卡不卡用数字说话，不靠感觉。
            def _log_fps():
                interval, frames = take_frame_stats()
                if frames > 3:
                    self.log_manager.log(
                        f"动画实测: {frames} 帧 · 平均帧间隔 {interval:.1f}ms "
                        f"(≈{1000 / max(interval, 0.01):.0f}fps)",
                        'INFO', verbose=True)
            ui_call(self.root, lambda: self.root.after(340, _log_fps))
        if name == "settings" and self.settings_page is not None:
            self.settings_page.reload()
        if name == "manage":
            try:
                self._update_manage_role()
            except Exception:
                pass

    def _update_nav_state(self, name=None, animate=True):
        target = name or self.active_page
        nav = getattr(self, "nav", None)
        if nav is None or not target:
            return
        if nav.current() == target:
            return
        nav.select(target, animate=animate)

    # ==================== 全局状态（单行防闪烁） ====================
    def set_status(self, text, kind="info", progress=None):
        """主界面唯一的运行状态行。

        网络/文件任务会高频回调阶段文字，直接 configure 会闪。这里只记住
        最后一次，60ms 合并一次；同一时间状态条只存在这一行。
        progress=None 表示不显示进度条，0..1 显示。
        """
        text = str(text or "").strip()
        if text == getattr(self, "_status_text", None) and \
                kind == getattr(self, "_status_kind", None):
            # 文字没变只更新进度，避免重复重绘
            if progress is not None:
                self._set_status_progress(progress)
            return
        self._status_text = text
        self._status_kind = kind
        self._status_seq = int(getattr(self, "_status_seq", 0)) + 1
        seq = self._status_seq
        if progress is not None:
            self._set_status_progress(progress)
        job = getattr(self, "_status_job", None)
        if job:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        self._status_job = self.root.after(
            55, lambda: self._apply_status(seq, text, kind, progress))

    def _apply_status(self, seq, text, kind, progress):
        self._status_job = None
        if seq != getattr(self, "_status_seq", 0):
            return
        colors = {"info": C_INFO, "success": C_SUCCESS,
                  "warning": C_WARNING, "error": C_ERROR,
                  "busy": C_ACCENT, "muted": C_TEXT_MUTED}
        try:
            self.progress_label.configure(
                text=text, text_color=(C_TEXT_SECONDARY if kind == "muted"
                                       else C_TEXT_MAIN))
            self.status_dot.configure(
                text=("●" if text else ""),
                text_color=colors.get(kind, C_INFO))
        except Exception:
            pass
        if progress is None:
            try:
                if self.progress_bar.winfo_manager():
                    self.progress_bar.pack_forget()
            except Exception:
                pass

    def _set_status_progress(self, value):
        try:
            value = max(0.0, min(1.0, float(value)))
            if not self.progress_bar.winfo_manager():
                self.progress_bar.pack(side=RIGHT, padx=(PAD_TIGHT, PAD_GAP))
            self.progress_bar.set(value)
        except Exception:
            pass

    def _clear_status(self):
        self.set_status("", "muted", progress=None)

    def toast(self, text, kind="success", duration_ms=1700):
        """右上角浮出提示（曲线滑入 + 自动淡出），同一时刻只留一条。"""
        previous = getattr(self, "_toast", None)
        if previous is not None:
            try:
                previous.close()
            except Exception:
                pass
        try:
            self._toast = Toast(self, text, kind=kind, duration_ms=duration_ms)
        except Exception:
            self._toast = None

    def open_log_page(self):
        self.show_page("log")
        self.toggle_log_mode()

    # ==================== 顶栏菜单（已移除） ====================
    def setup_menu(self):
        """原生菜单栏已去掉：它会在窗口顶部多出一条系统级横条，与设计稿不符。

        原菜单项全部迁到界面内：
          打开整合包 / 打开路径 / 关闭整合包 -> Step 1 的「选择 / 目录 / 关闭」
          程序设置 / 日志显示设置           -> 侧边栏「设置 / 日志」
          预设管理（打开数据库目录）        -> Step 2 的「数据库」
          刷新所有                          -> 枪包列表工具条的「⟳ 全部刷新」
          使用教程 / 关于 / 强制更新校验数据 -> 设置页「关于 / 数据库」选项卡
          退出                              -> 窗口关闭按钮 + 设置页「退出程序」
        """
        try:
            self.root.config(menu="")
        except Exception:
            pass

    def request_exit(self):
        """界面内的退出入口（与窗口关闭按钮同一套语义）。

        正在更新 / 替换时**直接拒绝退出**：写到一半被 kill 会留下半成品，
        下次打开还得修。忙时不弹确认框，只提示，避免用户手快点了「是」。
        """
        if self.is_applying or getattr(self, "online_busy", False):
            try:
                self.toast("正在同步/发布，完成后再退出", "warning")
            except Exception:
                pass
            return
        self._stop_watcher()
        try:
            self.root.quit()
        except Exception:
            pass

    # ==================== 新手引导更新 ====================
    def _update_guide(self):
        if not self.guide:
            return
        if not self.db_ready:
            self.guide.hide()
            return
        if not self.current_pack_path:
            self.guide.show("step1_select_pack")
            return
        if not self.preset_manager or not self.preset_manager.presets:
            self.guide.show("step2_create_preset")
            return
        if not self.current_selected_preset:
            self.guide.hide()
            return
        info = self.preset_manager.presets.get(self.current_selected_preset)
        if info and not info.get('applied', False):
            self.guide.show("step3_apply")
            return
        self.guide.hide()

    # ==================== 设置 ====================
    def open_settings(self):
        if not self.db_ready:
            show_warning("提示", "数据库未初始化，请重启程序")
            return
        # 设置已从弹窗改为侧边栏页面（页面内用选项卡分类）
        self.show_page("settings")

    def _on_settings_saved(self):
        """自动保存回调：日志 + 提示；身份/存储若变了要把界面一起切过去。"""
        # 「已切换到 xx 存储」这类回显属于细节：只在完整日志模式下保留
        self.log_manager.log(
            f"设置已保存: 存储模式={self.settings.storage_mode}, 身份={self.settings.role}",
            'SUCCESS', verbose=True)
        # 设置页的「用户身份」单选是直接写 settings 的，不经过 _set_role；
        # 这里补上界面切换，否则要重启才生效。
        try:
            if getattr(config, "UI_ROLE", "player") != self.settings.role:
                self._apply_role_from_settings()
                self.online_states = {}
                self._online_recheck.clear()
                self.online_pending.clear()
                self._preset_size_cache.clear()
                self._update_preset_list()
        except Exception:
            pass
        self.toast("设置已自动保存", "success")

    def _on_db_action(self, action: str):
        # 数据库动作（切换/合并/适配）都属于主流程，先回到主界面再执行
        self.show_page("home")
        if action == 'switch':
            self.switch_database()
        elif action == 'merge':
            self.merge_database()
        elif action == 'migrate_legacy':
            self.migrate_legacy_database()
