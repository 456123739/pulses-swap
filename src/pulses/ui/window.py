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
from ..managers import *
from ..pages import *



# ==================== 主窗口 ====================


class WindowMixin:
    """窗口骨架：透明度防护 / 界面装配 / 页面切换 / 菜单退出"""

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
            self.root.after(2000, self._opacity_tick)
        except Exception:
            pass

    # ==================== UI 构建 ====================
    def setup_ui(self):
        # ===== 骨架：左侧导航栏 + 右侧页面区（替代原来的「左栏 + 右栏」两列） =====
        main_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        main_frame.pack(fill=BOTH, expand=True, padx=PAD_WINDOW, pady=PAD_WINDOW)

        # 覆盖层宿主：所有窗口内弹窗都 place 在这个 frame 上（连侧边栏一起盖住，保证模态）
        self.overlay_host = main_frame
        self.active_page = None
        set_overlay_host(self)

        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=0, minsize=px(SIDEBAR_W))
        main_frame.grid_columnconfigure(1, weight=1)

        # ===== 侧边导航栏：只有品牌 + 导航项，不放任何提示文案 =====
        sidebar = ctk.CTkFrame(main_frame, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                border_width=BORDER_W, border_color=C_BORDER_SOFT,
                                width=SIDEBAR_W)
        # 注意 sticky 必须带 e：只写 "nsw" 时 Tk 只把控件贴西边、不横向拉伸，
        # 侧边栏会被压到内容的自然宽度（124px），看起来又窄又挤。
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, PAD_GAP))
        sidebar.grid_propagate(False)
        self.sidebar = sidebar

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.pack(fill=X, padx=PAD_CARD_X, pady=(PAD_CARD_Y, 0))
        # 一枚 4x16 的强调色竖条：品牌区有了视觉锚点，不是一行光秃秃的字
        ctk.CTkFrame(brand, fg_color=C_ACCENT, width=4, height=16,
                     corner_radius=2).pack(side=LEFT, padx=(0, PAD_TIGHT))
        make_label(brand, text=PROJECT_NAME, fg=C_TEXT_MAIN,
                    font_size=FS_SUBHEAD, bold=True).pack(side=LEFT)
        make_label(sidebar, text=f"v{VERSION} · {AUTHOR}", fg=C_TEXT_MUTED,
                    font_size=FS_TINY).pack(anchor=W, padx=PAD_CARD_X,
                                            pady=(PAD_MICRO, PAD_GAP))

        # 导航项：纯文字（需求：去掉图标与动画），选中态是一块静态圆角药丸
        nav_items = (("home", "主界面"),
                     ("settings", "设置"),
                     ("log", "日志"))
        nav_height = px(len(nav_items) * (H_NAV + PAD_XS) + 2 * PAD_XS)
        self.nav = CanvasSegmented(
            sidebar, nav_items, command=self.show_page,
            orientation="vertical", item_height=H_NAV, pad=4, gap=PAD_XS,
            radius=R_CONTROL, bg_color=C_CARD_BG, pill_color=C_ACCENT_SOFT,
            hover_color=C_ACCENT_SOFT, text_color=C_TEXT_MAIN,
            # 侧边栏是主要导航，比正文大一档（16px）更稳，也不会撑爆 38px 行高
            active_text_color=C_ACCENT, font_size=FS_SUBHEAD, bold_active=True,
            text_anchor="w", text_pad=14, duration_ms=240, height=nav_height)
        self.nav.pack(fill=X, padx=PAD_XS)

        # ===== 侧边栏底部：会话卡（整合包信息 + 身份，合成一块）=====
        # 原来这里是两块：一块灰底状态卡 + 一块白底身份卡。白栏上放灰卡
        # 读起来像 disabled；合成一块白底 + 发丝线，少一个盒子也更整。
        session_card = ctk.CTkFrame(sidebar, fg_color=C_CARD_BG,
                                     corner_radius=R_CONTROL,
                                     border_width=1,
                                     border_color=C_DIVIDER)
        session_card.pack(side=BOTTOM, fill=X, padx=PAD_XS,
                           pady=(PAD_GAP, PAD_CARD_Y))

        make_label(session_card, text="当前整合包", fg=C_TEXT_MUTED,
                    font_size=FS_TINY).pack(anchor=W, padx=PAD_CARD_X,
                                             pady=(PAD_CARD_Y, PAD_MICRO))
        self.sb_pack_label = make_label(session_card, text="未选择",
                                         fg=C_TEXT_MAIN, font_size=FS_SMALL,
                                         bold=True)
        self.sb_pack_label.pack(anchor=W, padx=PAD_CARD_X)
        self.sb_status_label = make_label(session_card, text="未加载",
                                           fg=C_ERROR, font_size=FS_TINY)
        self.sb_status_label.pack(anchor=W, padx=PAD_CARD_X, pady=(PAD_TIGHT, 0))
        self.sb_preset_label = make_label(session_card, text="无",
                                           fg=C_ACCENT, font_size=FS_TINY)
        self.sb_preset_label.pack(anchor=W, padx=PAD_CARD_X,
                                   pady=(PAD_MICRO, PAD_GAP))

        # 分隔线：上面是「这个包」的信息，下面是「你是谁」
        ctk.CTkFrame(session_card, fg_color=C_DIVIDER,
                      height=1).pack(fill=X, padx=PAD_CARD_X)

        identity_row = ctk.CTkFrame(session_card, fg_color="transparent")
        identity_row.pack(fill=X, padx=PAD_TIGHT, pady=PAD_TIGHT)
        self.identity_badge = make_label(identity_row, text="玩家",
                                          fg=C_TEXT_SECONDARY,
                                          font_size=FS_SMALL, bold=True)
        self.identity_badge.pack(side=LEFT, padx=(PAD_XS, 0))
        self.identity_btn = make_text_button(identity_row, "切换",
                                              command=self.open_identity_dialog)
        self.identity_btn.pack(side=RIGHT)

        # ===== 右侧内容列：页面区 + 全局状态条（进度条） =====
        content_col = ctk.CTkFrame(main_frame, fg_color="transparent")
        content_col.grid(row=0, column=1, sticky="nsew")
        content_col.grid_columnconfigure(0, weight=1)
        content_col.grid_rowconfigure(0, weight=1)
        content_col.grid_rowconfigure(1, weight=0)

        self.page_host = ctk.CTkFrame(content_col, fg_color="transparent")
        self.page_host.grid(row=0, column=0, sticky="nsew")
        # 页面放在 Canvas 里：Canvas 会裁剪子窗口，推入/推出的过程不会溢到侧边栏
        self.stack = SlideStack(self.page_host, bg_color=C_WINDOW_BG,
                                 duration_ms=260)
        self.page_canvas = self.stack.canvas

        # 进度条移到全局状态条：原来在右栏里，show_progress/hide_progress 的
        # pack/pack_forget 语义不变，只是父容器换成了这里
        self.status_bar = ctk.CTkFrame(content_col, fg_color="transparent",
                                        height=1)
        self.status_bar.grid(row=1, column=0, sticky="ew")
        self.progress_bar = ctk.CTkProgressBar(self.status_bar, height=H_PROGRESS,
                                                 corner_radius=R_PROGRESS,
                                                 fg_color=C_PANEL_ALT_BG,
                                                 progress_color=C_ACCENT)
        self.progress_bar.pack(fill=X, pady=(0, PAD_XS))
        self.progress_bar.pack_forget()
        self.progress_label = make_label(self.status_bar, text="",
                                          fg=C_TEXT_SECONDARY, font_size=FS_TINY)
        self.progress_label.pack(fill=X, pady=(0, PAD_XS))
        self.progress_label.pack_forget()

        # ===== 页面 =====
        self.settings_page = None
        self.pages = {}
        self.pages["home"] = self._build_home_page()
        self.pages["log"] = self._build_log_page()
        # 主界面右下角的日志栏与「日志」页共用同一份日志流
        if getattr(self, "home_log_text", None) is not None:
            self.log_manager.attach(self.home_log_text)
        self.settings_page = SettingsPage(
            self.stack.canvas, self,
            on_save_callback=self._on_settings_saved,
            on_db_action=self._on_db_action)
        self.pages["settings"] = self.settings_page.frame
        for key in ("home", "settings", "log"):
            self.stack.add(key, self.pages[key])
        # 三页先各自布局一次（这笔开销只付一次，别落在切换动画的第一帧上）
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

        self.show_page("home", animate=False)
        self._play_entrance()

    # ==================== 入场动画 ====================
    def _play_entrance(self):
        """启动入场：当前页从右侧轻轻滑入，侧边栏滑块同步淡入。"""
        # 入场只做滑块淡入：搬页面窗口项（整棵控件树）每帧要重排子窗口，
        # 是这里最贵的一类操作，放在启动第一帧最容易看出卡顿。
        self._update_nav_state(self.active_page, animate=True)

    # ==================== 页面切换 ====================
    PAGE_ORDER = ("home", "settings", "log")

    def show_page(self, name, animate=True):
        """切换右侧页面：整页在 Canvas 里推入/推出，侧边栏滑块同步滑动。

        方向按需求走「点哪边内容就往哪边走」：
          点下面/右面的选项 → 内容往下/右走（新页从下/右方进来）
          点上面/左面的选项 → 内容往上/左走（新页从上/左方进来）
        侧边栏是竖排，所以页面竖着滑（axis="y"）。
        """
        if name not in self.pages or name == self.active_page:
            return
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

    def _update_nav_state(self, name=None, animate=True):
        target = name or self.active_page
        nav = getattr(self, "nav", None)
        if nav is None or not target:
            return
        if nav.current() == target:
            return
        nav.select(target, animate=animate)

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
        if self.is_applying:
            try:
                self.toast("正在处理，完成后再退出", "warning")
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
        """自动保存回调：只写日志 + 右上角浮一条提示，不再弹模态框打断操作。"""
        # 「已切换到 xx 存储」这类回显属于细节：只在完整日志模式下保留
        self.log_manager.log(
            f"设置已保存: 存储模式={self.settings.storage_mode}, 身份={self.settings.role}",
            'SUCCESS', verbose=True)
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
