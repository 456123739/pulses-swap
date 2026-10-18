"""
主窗口与程序入口
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
from .utils import *
from .animation import *
from .widget import *
from .dialogs import *
from .managers import *
from .pages import *



# ==================== 主窗口 ====================
class PulsesSwapApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{PROJECT_NAME} v{VERSION}")
        # 高分屏下窗口会被 window_scaling 放大，启动尺寸要按屏幕收口，
        # 否则 125%/150% 时窗口可能比屏幕还高。
        try:
            scr_w = int(self.root.winfo_screenwidth() or WINDOW_W)
            scr_h = int(self.root.winfo_screenheight() or WINDOW_H)
        except Exception:
            scr_w, scr_h = WINDOW_W, WINDOW_H
        scale = config.UI_SCALE if config.UI_SCALE > 0 else 1.0
        win_w = int(min(WINDOW_W, max(WINDOW_MIN_W, scr_w / scale - 40)))
        win_h = int(min(WINDOW_H, max(WINDOW_MIN_H, scr_h / scale - 90)))
        self.root.geometry(f"{win_w}x{win_h}")
        self.root.minsize(WINDOW_MIN_W, WINDOW_MIN_H)

        # ==================== Win11 透明修复 ====================
        try:
            self.root.attributes('-alpha', 1.0)
        except Exception:
            pass
        try:
            self.root.wm_attributes('-alpha', 1.0)
        except Exception:
            pass
        try:
            self.root.attributes('-transparentcolor', '')
        except Exception:
            pass
        try:
            self.root.configure(fg_color=C_WINDOW_BG)
        except Exception:
            try:
                self.root.configure(bg=C_WINDOW_BG)
            except Exception:
                pass

        self._disable_win11_transparency()
        # ========================================================

        self.current_pack_path: Path | None = None
        self.tacz_path: Path | None = None
        self.preset_manager: PresetManager | None = None
        self.log_manager: LogManager | None = None
        self.settings = AppSettings()
        self.recent_manager: RecentPacksManager | None = None
        self.tacz_watcher: TaczWatcher | None = None

        self.is_applying = False
        self.current_selected_preset: str | None = None
        self.show_full_log = False
        self.loading_presets = False
        self.recent_visible = False
        self.dont_remind_this_session = False
        self.db_ready = False
        self.last_after_migrate_mode = "mark"

        self.guide: GuideManager | None = None

        # worker 线程 → 主线程的投递队列，越早启动越好
        start_ui_pump(self.root)
        self.setup_ui()
        self.setup_menu()

        self._install_opacity_guard()
        self.root.after(150, self._init_database_flow)

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

    def _use_database(self, db_path: Path):
        self.settings.bind_database(db_path)
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

        make_label(sidebar, text=PROJECT_NAME, fg=C_ACCENT, font_size=FS_SUBHEAD,
                    bold=True).pack(anchor=W, padx=PAD_CARD_X,
                                    pady=(PAD_CARD_Y, 0))
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
            active_text_color=C_ACCENT, font_size=FS_BODY, bold_active=True,
            text_anchor="w", text_pad=14, duration_ms=240, height=nav_height)
        self.nav.pack(fill=X, padx=PAD_XS)

        # ===== 侧边栏底部状态卡 =====
        # 侧边栏有 800+px 高，只有品牌 + 三个导航项会显得空；
        # 底部钉一张状态卡（整合包 / 状态 / 当前预设），既补留白又是真信息。
        status_card = ctk.CTkFrame(sidebar, fg_color=C_PANEL_ALT_BG,
                                    corner_radius=R_CONTROL,
                                    border_width=BORDER_W,
                                    border_color=C_BORDER_SOFT)
        status_card.pack(side=BOTTOM, fill=X, padx=PAD_XS,
                          pady=(PAD_GAP, PAD_CARD_Y))
        attach_hover_glow(status_card)
        make_label(status_card, text="当前整合包", fg=C_TEXT_MUTED,
                    font_size=FS_TINY).pack(anchor=W, padx=PAD_CARD_X,
                                             pady=(PAD_CARD_Y, PAD_MICRO))
        self.sb_pack_label = make_label(status_card, text="未选择",
                                         fg=C_TEXT_MAIN, font_size=FS_SMALL,
                                         bold=True)
        self.sb_pack_label.pack(anchor=W, padx=PAD_CARD_X)
        self.sb_status_label = make_label(status_card, text="状态: 未加载",
                                           fg=C_ERROR, font_size=FS_TINY)
        self.sb_status_label.pack(anchor=W, padx=PAD_CARD_X, pady=(PAD_TIGHT, 0))
        self.sb_preset_label = make_label(status_card, text="当前预设: 无",
                                           fg=C_ACCENT, font_size=FS_TINY)
        self.sb_preset_label.pack(anchor=W, padx=PAD_CARD_X,
                                   pady=(PAD_MICRO, PAD_CARD_Y))

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
            desc="Step 1 · 拖入整合包根目录，或点击「选择」定位")
        self.guide.register(
            "step2_create_preset", [self.create_preset_btn],
            desc="Step 2 · 点击「+ 创建」新建预设，放入枪包")
        self.guide.register(
            "step3_apply", [self.apply_btn],
            desc="Step 4 · 点击「一键替换」启用预设")

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

    # ==================== 日志页 ====================
    def _build_log_page(self):
        page = ctk.CTkFrame(self.stack.canvas, fg_color=C_WINDOW_BG)
        log_group = ctk.CTkFrame(page, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                  border_width=BORDER_W, border_color=C_BORDER_SOFT)
        log_group.pack(fill=BOTH, expand=True)
        attach_hover_glow(log_group)
        make_label(log_group, text="运行日志", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        log_content = ctk.CTkFrame(log_group, fg_color="transparent")
        log_content.pack(fill=BOTH, expand=True, padx=PAD_CARD_X,
                         pady=(0, PAD_CARD_Y))
        log_toolbar = ctk.CTkFrame(log_content, fg_color="transparent")
        log_toolbar.pack(fill=X, pady=(0, PAD_TIGHT))
        self.log_toggle_btn = make_button(log_toolbar, "显示完整日志",
                                           command=self.toggle_log_mode)
        self.log_toggle_btn.pack(side=LEFT)
        self.log_clear_btn = make_button(log_toolbar, "清空", command=self.clear_log)
        self.log_clear_btn.pack(side=LEFT, padx=(PAD_TIGHT, 0))
        self.log_text = ctk.CTkTextbox(log_content, height=H_LOG_BOX,
                                        fg_color=C_INPUT_BG,
                                        border_color=C_BORDER_SOFT, border_width=BORDER_W,
                                        corner_radius=R_CONTROL, text_color=C_TEXT_MAIN,
                                        font=(FONT_FAMILY_MONO, FS_BODY), wrap="word")
        self.log_text.pack(fill=BOTH, expand=True)

        self.log_manager = LogManager(self.log_text, self.root)
        return page

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
        """界面内的退出入口（与窗口关闭按钮同一套语义）。"""
        if self.is_applying:
            if not ask_yes_no("操作进行中",
                    "正在操作中，确定要退出吗？\n\n程序将在任务完成后自动退出。"):
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

    # ==================== 数据库管理 ====================
    def switch_database(self):
        if self.is_applying:
            show_warning("操作进行中", "请等待当前操作完成")
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
        if self.recent_manager:
            self.recent_manager = RecentPacksManager(path / ".global.json")
        self.log_manager.log(f"数据库已切换: {path}", 'SUCCESS')
        show_info("完成", "数据库已切换，请重新打开整合包。")
        self.close_pack()

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
        if self.current_pack_path:
            self.open_pack_btn.configure(state="normal")
            self.open_tacz_btn.configure(state="normal")

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

    # ==================== 身份提示 ====================
    def _show_role_dialog(self, title, message) -> str:
        dlg_w = DLG_CHOICE[0]
        card = make_card(get_overlay_host(), self.root, width=dlg_w,
                          escape_value='ok', title=title)
        frame = card.body
        msg_label = make_label(frame, text=message, fg=C_TEXT_MAIN, font_size=FS_BODY)
        msg_label.configure(wraplength=dlg_w - 2 * PAD_DIALOG, justify=LEFT, anchor=W)
        msg_label.pack(anchor=W, fill=X, pady=(0, PAD_GAP))

        dont_remind_var = BooleanVar(value=False)
        check = ctk.CTkCheckBox(frame, text="本次启动不再提醒",
                                variable=dont_remind_var,
                                text_color=C_TEXT_MAIN, font=(config.FONT_FAMILY, FS_SMALL),
                                fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER,
                                border_color=C_BORDER)
        check.pack(anchor=W, pady=(PAD_XS, PAD_GAP))
        card.register_focusable(check)

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill=X, side=BOTTOM, pady=(PAD_GAP, 0))

        def on_ok():
            card.close('ok')

        def on_export():
            card.close('export')

        if self.settings.role == "developer":
            export_btn = make_button(btn_frame, "导出增量更新", command=on_export,
                                      accent=True)
            export_btn.pack(side=RIGHT, padx=PAD_XS)
            card.register_focusable(export_btn)
        ok_btn = make_button(btn_frame, "确定", command=on_ok)
        ok_btn.pack(side=RIGHT)
        card.register_focusable(ok_btn)
        result = card.wait()
        # 关键：不管用户是点「确定」、按 ESC、还是点窗口的 ✕ 关掉，
        # 只要勾了「本次启动不再提醒」就得生效 —— 之前只在 on_ok 里读，
        # 用 ESC/✕ 关掉就白勾了。
        try:
            if dont_remind_var.get():
                self.dont_remind_this_session = True
        except Exception:
            pass
        return result

    def _check_applied_changes(self, preset_name):
        try:
            if not self.preset_manager.has_changes(preset_name):
                return
            changes = self.preset_manager.detect_changes(preset_name)
            self.log_manager.log(f"检测到已应用预设 '{preset_name}' 有未同步的变更:", 'WARNING')
            if changes['added']:
                self.log_manager.log(f"  新增: {', '.join(changes['added'][:5])}"
                                      + (" ..." if len(changes['added']) > 5 else ""), 'INFO')
            if changes['removed']:
                self.log_manager.log(f"  移除: {', '.join(changes['removed'][:5])}"
                                      + (" ..." if len(changes['removed']) > 5 else ""), 'ERROR')
            if changes['modified']:
                self.log_manager.log(f"  修改: {', '.join(changes['modified'][:5])}"
                                      + (" ..." if len(changes['modified']) > 5 else ""), 'PROCESS')
            if self.dont_remind_this_session:
                return
            if self.settings.role == "developer":
                msg = (f"检测到已应用预设 '{preset_name}' 有以下变更:\n\n"
                       f"  • 新增: {len(changes['added'])} 个\n"
                       f"  • 移除: {len(changes['removed'])} 个\n"
                       f"  • 修改: {len(changes['modified'])} 个\n\n"
                       f"作为开发者，建议您立即导出增量更新以便分享给其他人。\n\n"
                       f"是否立即导出？")
                if self._show_role_dialog("检测到枪包变更", msg) == 'export':
                    self.export_incremental()
            else:
                msg = (f"检测到已应用预设 '{preset_name}' 有以下变更:\n\n"
                       f"  • 新增: {len(changes['added'])} 个\n"
                       f"  • 移除: {len(changes['removed'])} 个\n"
                       f"  • 修改: {len(changes['modified'])} 个\n\n"
                       f"请检查枪包是否符合预期。\n\n"
                       f"如变更非预期，请按照报错条目修改枪包文件。\n"
                       f"如变更符合预期，可忽略此提示。")
                self._show_role_dialog("检测到枪包变更", msg)
        except Exception as e:
            self.log_manager.log(f"检查变更时出错: {e}", 'WARNING')

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

    # ==================== 整合包管理 ====================
    def select_pack(self):
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

        pack_db_path = self.settings.get_db_path(pack_path)
        pack_db_path.mkdir(parents=True, exist_ok=True)

        self.pack_path_label.configure(text=str(pack_path), text_color=C_SUCCESS)
        self.pack_status_label.configure(text="状态: 已加载 ✓", text_color=C_SUCCESS)
        self._update_sidebar_status()
        self.pack_name_label.configure(text="当前预设: 无", text_color=C_ACCENT)
        self.open_pack_btn.configure(state="normal")
        self.open_tacz_btn.configure(state="normal")

        self.preset_manager = PresetManager(pack_db_path, self.log_manager,
                                             tacz_path, pack_name=pack_path.name)
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
        self.preset_listbox.delete(0, END)
        self.preset_listbox.insert(END, "正在加载预设列表，请稍候...")
        self.preset_listbox.itemconfig(0, fg=C_TEXT_MUTED)
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
                for i in range(self.preset_listbox.size()):
                    if preset_name_of(self.preset_listbox.get(i)) == first:
                        self.preset_listbox.selection_set(i)
                        self.on_preset_selected(None)
                        break
        self._update_guide()

    def _disable_buttons(self, disabled: bool):
        state = "disabled" if disabled else "normal"
        try:
            self.create_preset_btn.configure(state=state)
            self.export_preset_btn.configure(state=state)
            self.export_incremental_btn.configure(state=state)
            self.refresh_preset_btn.configure(state=state)
            self.refresh_gunpack_btn.configure(state=state)
            self.open_tacz_btn.configure(state=state)
            self.save_version_btn.configure(state=state)
            self.apply_btn.configure(state=state)
            self.select_pack_btn.configure(state=state)
            self.open_db_btn.configure(state=state)
        except Exception:
            pass

    def _set_pack_dependent_buttons(self, enabled: bool) -> None:
        """只开关「依赖已加载整合包」的按钮。

        与「选择整合包 / 打开数据库」区分开：后两者任何时候都要可用，
        否则关掉一个包就再也选不了下一个。
        """
        state = "normal" if enabled else "disabled"
        for name in ("open_pack_btn", "close_pack_btn", "open_tacz_btn",
                     "apply_btn", "create_preset_btn", "export_preset_btn",
                     "export_incremental_btn", "refresh_preset_btn",
                     "refresh_gunpack_btn", "save_version_btn"):
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
            self.pack_name_label.configure(text="当前预设: default")
            self.log_manager.log("默认预设创建成功", 'SUCCESS')

    def close_pack(self):
        if self.is_applying:
            show_warning("操作进行中", "请等待当前操作完成")
            return
        if self.loading_presets:
            show_info("加载中", "预设列表正在加载，请稍候...")
            return
        self._stop_watcher()
        self.current_pack_path = None
        self.tacz_path = None
        self.preset_manager = None
        self.current_selected_preset = None
        self.pack_path_label.configure(text="未选择", text_color=C_TEXT_SECONDARY)
        self.pack_status_label.configure(text="状态: 未加载", text_color=C_ERROR)
        self.pack_name_label.configure(text="当前预设: 无", text_color=C_ACCENT)
        self.preset_listbox.delete(0, END)
        self.gunpack_listbox.delete(0, END)
        self.preset_name_label.configure(text="预设: 未选择")
        self.preset_version_label.configure(text="版本号: 无")
        self.preset_status_label.configure(text="状态: 未应用")
        self.gunpack_count_label.configure(text="共 0 个枪包")
        self.version_entry.delete(0, END)
        # 关闭后只有「整合包相关」的按钮该灰掉；「选择整合包 / 数据库」必须
        # 保持可用 —— 之前这里调了 _disable_buttons(True) 把包括「选择」在内
        # 的所有按钮全禁掉，之后没有任何地方再解开，关掉一个包就再也选不了
        # 下一个（用户反馈「选择是灰的」）。
        self._disable_buttons(False)
        self._set_pack_dependent_buttons(False)
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
        for src, dst in ((self.pack_status_label, self.sb_status_label),
                         (self.pack_name_label, self.sb_preset_label)):
            try:
                dst.configure(text=src.cget("text"),
                              text_color=src.cget("text_color"))
            except Exception:
                pass

    def _update_preset_list(self):
        if not self.preset_manager:
            return
        self.preset_listbox.delete(0, END)
        for name, info in self.preset_manager.presets.items():
            # 「已应用」用文字前缀标注，不用底色 —— 底色是选中态的专属视觉，
            # 两者都用浅绿会出现「两个都被点亮」的错觉（用户截图反馈过）。
            applied = bool(info.get('applied', False))
            self.preset_listbox.insert(
                END, (PRESET_MARK_APPLIED + name) if applied else name)
            if applied:
                idx = self.preset_listbox.size() - 1
                self.preset_listbox.itemconfig(idx, fg=C_SUCCESS)
        if self.preset_manager.current_preset:
            self.pack_name_label.configure(text=f"当前预设: {self.preset_manager.current_preset}")
        else:
            self.pack_name_label.configure(text="当前预设: 无")
        if self.current_selected_preset:
            for i in range(self.preset_listbox.size()):
                if (preset_name_of(self.preset_listbox.get(i))
                        == self.current_selected_preset):
                    self.preset_listbox.selection_set(i)
                    break
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
            self._update_preset_list()
            self.log_manager.log("预设列表刷新完成", 'INFO', verbose=True)
            self._update_guide()
        except Exception as exc:
            safe_print("预设刷新回调出错:", traceback.format_exc())
            self.log_manager.log(f"预设刷新回调出错: {exc}", 'ERROR')

    def on_preset_selected(self, event):
        if not self.preset_manager or self.loading_presets:
            return
        sel = self.preset_listbox.curselection()
        if not sel:
            return
        name = preset_name_of(self.preset_listbox.get(sel[0]))
        self.current_selected_preset = name
        info = self.preset_manager.presets.get(name)
        if not info:
            return
        self.preset_name_label.configure(text=f"预设: {name}")
        self._animate_label_color(self.preset_name_label, C_TEXT_MUTED, C_ACCENT)
        version = info.get('version', 'v1.0.0')
        self.preset_version_label.configure(text=f"版本号: {version}")
        status = "已应用 ✓" if info.get('applied', False) else "未应用"
        self.preset_status_label.configure(text=f"状态: {status}")
        self._animate_label_color(
            self.preset_status_label, C_TEXT_MUTED,
            C_SUCCESS if info.get('applied') else C_WARNING)
        self.version_entry.delete(0, END)
        self.version_entry.insert(0, version)
        if info.get('applied', False):
            self.apply_btn.configure(state="disabled", text="已应用 ✓")
            self.export_incremental_btn.configure(state="normal")
        else:
            self.apply_btn.configure(state="normal", text="Step 4 · 一键替换")
            self.export_incremental_btn.configure(state="disabled")
        self.export_preset_btn.configure(state="normal")
        self.refresh_gunpacks(use_cache=False)
        self.log_manager.log(f"选择预设: {name}", 'INFO', verbose=True)
        self._update_sidebar_status()
        self._update_guide()

    def show_preset_context_menu(self, event):
        if not self.preset_manager or self.loading_presets:
            return
        idx = self.preset_listbox.nearest(event.y)
        if idx < 0:
            return
        name = preset_name_of(self.preset_listbox.get(idx))
        info = self.preset_manager.presets.get(name)
        if not info:
            return
        self.preset_listbox.selection_clear(0, END)
        self.preset_listbox.selection_set(idx)
        self.on_preset_selected(None)
        menu = Menu(self.root, tearoff=0, bg=C_PANEL_BG, fg=C_TEXT_MAIN,
                    activebackground=C_ACCENT_SOFT, activeforeground=C_ACCENT,
                    font=(config.FONT_FAMILY, FS_SMALL))
        menu.add_command(label="迁移预设…",
                          command=lambda: self.migrate_preset(name))
        menu.add_separator()
        menu.add_command(label="重命名", command=lambda: self.rename_preset(name))
        menu.add_separator()
        if name != "default":
            if info.get('applied', False):
                menu.add_command(label="删除预设 (已应用，请先切换)", state=DISABLED)
            else:
                menu.add_command(label="删除预设",
                                  command=lambda: self.delete_preset(name))
        menu.post(event.x_root, event.y_root)

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
        if self.current_pack_path:
            self.open_pack_btn.configure(state="normal")
            self.open_tacz_btn.configure(state="normal")

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
        from tkinter import simpledialog
        new_name = simpledialog.askstring("重命名预设",
                                            f"请输入新的预设名称 (当前: {preset_name}):",
                                            initialvalue=preset_name)
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
                self._update_preset_list()
                for i in range(self.preset_listbox.size()):
                    if preset_name_of(self.preset_listbox.get(i)) == new_name:
                        self.preset_listbox.selection_set(i)
                        self.on_preset_selected(None)
                        break
                show_info("成功", f"预设已重命名为: {new_name}")
            else:
                show_error("错误", "预设重命名失败")
        finally:
            self.root.config(cursor="")

    def delete_preset(self, preset_name):
        if not self.preset_manager or self.loading_presets:
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
                if self.current_selected_preset == preset_name:
                    self.current_selected_preset = None
                    self.preset_name_label.configure(text="预设: 未选择")
                    self.preset_version_label.configure(text="版本号: 无")
                    self.preset_status_label.configure(text="状态: 未应用")
                    self.version_entry.delete(0, END)
                    self.apply_btn.configure(state="disabled", text="Step 4 · 一键替换")
                    self.export_preset_btn.configure(state="disabled")
                    self.export_incremental_btn.configure(state="disabled")
                    self.gunpack_listbox.delete(0, END)
                    self.gunpack_count_label.configure(text="共 0 个枪包")
                self._update_preset_list()
                show_info("成功", f"预设 '{preset_name}' 已删除")
                self._update_guide()
            else:
                show_error("错误", "删除预设失败")
        except Exception as e:
            show_error("错误", f"删除失败: {e}")

    def create_preset(self):
        if not self.preset_manager or self.loading_presets:
            return
        from tkinter import simpledialog
        name = simpledialog.askstring("创建预设", "请输入预设名称:")
        if not name or not name.strip():
            return
        name = name.strip()
        if name in self.preset_manager.presets:
            show_error("错误", f"预设 '{name}' 已存在")
            return
        version = simpledialog.askstring("版本号", "请输入版本号 (可选，默认 v1.0.0):")
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
            show_info("创建成功",
                f"预设 '{name}' 创建成功！\n\n"
                f"版本号: {version}\n\n"
                f"请在打开的文件夹中放入枪包文件(ZIP和文件夹)\n"
                f"然后点击「刷新」按钮更新索引。")
            self._update_guide()

    def save_version(self):
        if not self.preset_manager or not self.current_selected_preset:
            return
        v = self.version_entry.get().strip() or "v1.0.0"
        if self.preset_manager.update_preset_version(self.current_selected_preset, v):
            self.preset_version_label.configure(text=f"版本号: {v}")
            self.log_manager.log(f"版本号已更新为: {v}", 'SUCCESS')

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

    # ==================== 通用功能 ====================
    def toggle_log_mode(self):
        if self.log_manager:
            self.show_full_log = not self.show_full_log
            self.log_manager.set_show_full(self.show_full_log)
            self.log_toggle_btn.configure(
                text="显示单条日志" if self.show_full_log else "显示完整日志")

    def clear_log(self):
        if self.log_manager:
            self.log_manager.clear()

    def refresh_all(self):
        if self.loading_presets:
            show_info("加载中", "预设列表正在加载，请稍候...")
            return
        self.refresh_presets()
        if self.current_selected_preset:
            self.refresh_gunpacks(use_cache=False)
        self.log_manager.log("所有数据已刷新", 'INFO')

    def open_preset_manager(self):
        if not self.preset_manager:
            show_warning("提示", "请先加载整合包")
            return
        try:
            open_path(self.preset_manager.database_path)
        except Exception as e:
            self.log_manager.log(f"打开文件夹失败: {e}", 'ERROR')

    def show_tutorial(self):
        show_info("使用教程",
            f"{PROJECT_NAME} v{VERSION}\n作者: {AUTHOR}\n\n"
            "【基础使用】\n"
            "Step 1 · 拖入整合包根目录（或整合包内任意文件）\n"
            "Step 2 · 创建预设并放入枪包，或拖入现成 .fgcpack\n"
            "Step 3 · 填写版本号，点保存\n"
            "Step 4 · 选择预设，点「一键替换」切换\n\n"
            "【拖入整合包】\n"
            "可直接拖入整合包根目录，也可拖入整合包内任意文件，\n"
            "程序会自动向上查找 tacz 文件夹。\n\n"
            "【拖入预设包/更新包】\n"
            "拖入 .fgcpack 或 .fgcupdate 即可自动导入。\n"
            "遇到同名预设会询问是否替换。\n\n"
            "【数据库】\n"
            "默认隔离存储：每个整合包独立预设库\n"
            "可在设置切换为合并存储（共用预设）\n\n"
            "【迁移预设】\n"
            "右键预设 → 迁移预设…\n\n"
            "【旧版数据库适配】\n"
            "设置 → 数据库管理 → 适配旧版数据库\n\n"
            "【打开TACZ】\n"
            "枪包列表右上角「打开TACZ」按钮")

    def show_about(self):
        # 「关于」已并入设置页的选项卡，不再弹独立信息框
        self.show_page("settings")
        if self.settings_page is not None:
            self.settings_page.show_about_tab()

    def show_about_detail(self):
        db_str = "未初始化"
        if self.settings._settings_file:
            db_str = str(self.settings._settings_file.parent)
        show_info("关于",
            f"{PROJECT_NAME} v{VERSION}\n\n"
            f"作者: {AUTHOR}\n"
            "描述: Minecraft Tacz 模组枪包快速切换工具\n\n"
            "功能特点:\n"
            "  - 快速切换枪包预设\n"
            "  - 拖入整合包内任意文件自动定位 tacz\n"
            "  - 拖入预设包/更新包自动导入，重名询问\n"
            "  - 默认隔离存储，避免文件重名\n"
            "  - 右键预设可迁移到其他整合包/数据库\n"
            "  - 旧版 FGC v2 数据库适配\n"
            "  - 数据库管理（切换/合并/适配）\n"
            "  - 增量更新（含原始校验数据校验）\n"
            "  - watchdog 实时文件监控\n"
            "  - 枪包列表状态着色\n"
            "  - Windows 原生回收站删除\n"
            "  - 一键打开整合包路径 / TACZ 文件夹\n"
            "  - 新手引导（Step1/2/3/4）\n"
            "  - Win11 透明修复（打包版可用）\n\n"
            f"数据库位置: {db_str}\n"
            f"当前模式: {'合并存储' if self.settings.storage_mode == 'merged' else '隔离存储'}\n\n"
            "UI: Pulses 水墨淡色主题")

# ==================== 程序入口 ====================
def apply_window_icon(window) -> None:
    """设置窗口/任务栏/Alt-Tab 图标。任一方式失败都不影响启动。"""
    # 1) Windows：iconbitmap(default=...) 最稳，同时作用于后续所有 toplevel
    try:
        ico = resource_path("icon.ico")
        if IS_WINDOWS and ico.exists():
            window.iconbitmap(default=str(ico))
    except Exception:
        pass
    # 2) 跨平台：iconphoto。PhotoImage 必须挂在对象上保留引用，
    #    否则被 GC 回收后图标会消失。
    try:
        png = resource_path("icon.png")
        if png.exists():
            img = PhotoImage(file=str(png))
            window.iconphoto(True, img)
            window._pulses_icon_ref = img
    except Exception:
        pass


# Windows 任务栏按钮的图标不取窗口图标，而是取进程 AppUserModelID 对应的图标
# （快捷方式图标 / exe 内嵌图标）。不显式设置时任务栏会退回 Tk 默认羽毛图标。
# 取值与 installer.iss 的 publisher 命名保持一致。
APP_USER_MODEL_ID = "Pulses0Studio.PulsesSwap"


def make_window_opaque(window) -> bool:
    """把窗口设成完全不透明（禁用 Win11 的 Mica / Acrylic 背景材质）。

    必须能反复调用：窗口失焦、弹出子窗口、切换主题时 DWM 会**重新评估**
    窗口材质，Mica 会自己回来 —— 这正是「一有弹窗在前面，主窗口就变
    半透明」的成因。所以除了启动时，还要在焦点/映射变化时补一次。
    """
    if not IS_WINDOWS:
        return False
    try:
        window.attributes("-alpha", 1.0)
    except Exception:
        pass
    try:
        window.attributes("-transparentcolor", "")
    except Exception:
        pass
    try:
        hwnd = (ctypes.windll.user32.GetParent(window.winfo_id())
                or window.winfo_id())
        _apply_opaque_window(hwnd)
        return True
    except Exception:
        return False


def refresh_window_opacity(root) -> int:
    """给主窗口与所有子窗口重新上一次「不透明」，返回处理了几个窗口。"""
    if not IS_WINDOWS:
        return 0
    count = 0
    if make_window_opaque(root):
        count += 1
    try:
        for child in root.winfo_children():
            try:
                if child.winfo_class() == "Toplevel":
                    if make_window_opaque(child):
                        count += 1
            except Exception:
                pass
    except Exception:
        pass
    return count


def _apply_opaque_window(hwnd) -> None:
    """把 Win11 窗口设成完全不透明（禁用 Mica / Acrylic 背景材质）。

    关键在 DWMWA_SYSTEMBACKDROP_TYPE(38)：值 0 是「自动」，系统会自己挑
    Mica/Acrylic —— 那就是壁纸透进来的原因；必须显式设成 1(DWMSBT_NONE)。
    """
    if not IS_WINDOWS:
        return
    try:
        none_backdrop = ctypes.c_int(1)      # DWMSBT_NONE
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 38, ctypes.byref(none_backdrop), ctypes.sizeof(none_backdrop))
    except Exception:
        pass
    try:
        # Win11 早期版本用未公开的 DWMWA_MICA_EFFECT(1029)，关掉它兜底
        mica_off = ctypes.c_int(0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 1029, ctypes.byref(mica_off), ctypes.sizeof(mica_off))
    except Exception:
        pass
    try:
        light_titlebar = ctypes.c_int(0)     # 浅色标题栏（与主题一致）
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(light_titlebar),
            ctypes.sizeof(light_titlebar))
    except Exception:
        pass
    try:
        # 33 = DWMWA_WINDOW_CORNER_PREFERENCE：按设计令牌给窗口圆角
        corner = ctypes.c_int(DWM_CORNER_PREF)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner))
    except Exception:
        pass


def _set_app_user_model_id() -> None:
    """设置进程 AppUserModelID。必须在任何 Tk 窗口创建之前调用，否则不生效。"""
    if not IS_WINDOWS:
        # ctypes.windll 只在 Windows 上存在，非 Windows 直接短路，避免 AttributeError
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID)
    except Exception:
        pass


def main():
    # 第一件事：任务栏图标归属必须在任何窗口存在之前定好
    _set_app_user_model_id()
    # 第二件：DPI 感知也要在窗口创建之前声明，否则 Windows 会拉伸位图（字糊）
    detected_scale = enable_dpi_awareness()
    # 第三件：把 Windows 定时器精度提到 1ms，否则补间只有 ~30fps（一卡一卡）
    enable_high_resolution_timer()
    if HAS_DND:
        try:
            root = TkinterDnD.Tk()
            root.configure(bg=C_WINDOW_BG)
        except Exception:
            root = ctk.CTk()
    else:
        root = ctk.CTk()

    # 窗口图标：源码运行取 packaging/，打包运行取 sys._MEIPASS
    apply_window_icon(root)

    # 字体回退链：root 就绪后解析一次，供所有控件工厂使用
    apply_font_fallbacks()
    # 自绘控件（Canvas / grid minsize）要按同一系数放大，别和 CTk 控件错位
    scale = sync_ui_scale(root)
    safe_print(f"DPI 检测: {detected_scale:.2f} · UI 缩放: {scale:.2f}")

    # ==================== Win11 透明修复（第一道） ====================
    try:
        root.attributes('-alpha', 1.0)
    except Exception:
        pass
    try:
        root.wm_attributes('-alpha', 1.0)
    except Exception:
        pass
    try:
        root.attributes('-transparentcolor', '')
    except Exception:
        pass
    try:
        root.configure(fg_color=C_WINDOW_BG)
    except Exception:
        try:
            root.configure(bg=C_WINDOW_BG)
        except Exception:
            pass

    def _disable_dwm(hwnd_root):
        if not IS_WINDOWS:
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(hwnd_root.winfo_id())
            if not hwnd:
                hwnd = hwnd_root.winfo_id()
            _apply_opaque_window(hwnd)
        except Exception:
            pass

    try:
        root.update_idletasks()
        _disable_dwm(root)
    except Exception:
        pass
    # ================================================================

    app = PulsesSwapApp(root)

    try:
        root.after(80, lambda: _disable_dwm(root))
    except Exception:
        pass

    def on_closing():
        # 退出语义与界面内的「退出程序」完全一致（见 request_exit）
        app.request_exit()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
