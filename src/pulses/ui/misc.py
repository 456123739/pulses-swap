"""身份提示 / 通用功能（日志开关、教程、关于）"""
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


class MiscMixin:
    """身份提示 / 通用功能（日志开关、教程、关于）"""

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
        check = make_checkbox(frame, "本次启动不再提醒", dont_remind_var)
        check.pack(anchor=W, pady=(PAD_XS, PAD_GAP))
        card.register_focusable(check)

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill=X, side=BOTTOM, pady=(PAD_GAP, 0))

        def on_ok():
            card.close('ok')

        ok_btn = make_button(btn_frame, "知道了", command=on_ok, accent=True)
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
                       f"作为开发者，可以右键这个预设 → 发布到云端，\n"
                       f"让其他玩家同步到这次改动。")
                self._show_role_dialog("检测到枪包变更", msg)
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
            "【三步就能用】\n"
            "1. 选整合包：拖入整合包根目录（或包内任意文件）\n"
            "2. 选预设：点左侧列表里的预设\n"
            "3. 一键替换：右侧蓝色按钮，把枪包换进 tacz\n\n"
            "【从云端添加预设】\n"
            "「＋ 从云端」→ 粘贴发布者给的分享链接和密码。\n"
            "加进来后会自动检查一次云端内容。\n\n"
            "【绑定 / 更换链接】\n"
            "双击预设打开「预设详情」→「来源」页，\n"
            "链接和密码都能直接在那里改，改完点保存。\n\n"
            "【检查更新与同步】\n"
            "绑过链接的预设会自动检查；\n"
            "卡片上出现「更新」时点它即可同步到最新。\n"
            "右键预设也有「检查更新 / 同步」两项。\n\n"
            "【开发者 · 发布预设】\n"
            "1. 身份切到开发者（侧边栏底部 → 切换）\n"
            "2. 双击预设 →「来源」页，填【云端路径】——\n"
            "   这是网盘里的文件夹路径，比如 test，\n"
            "   或 /PulsesSwap/你的预设名；不存在会自动建。\n"
            "   （分享链接/密码是玩家用的，开发者留空即可，\n"
            "     发布成功后程序会自己填上去）\n"
            "3. 点「发布到云端」，等进度条走完\n"
            "4. 把生成的分享链接和密码发给玩家\n\n"
            "【数据库】\n"
            "默认隔离存储：每个整合包一个独立预设库；\n"
            "设置 → 常规 可切换为合并存储（多个整合包共用）。\n\n"
            "【迁移预设】\n"
            "右键预设 → 迁移预设…\n\n"
            "【旧版数据库】\n"
            "设置 → 数据库 → 适配旧版数据库")

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
