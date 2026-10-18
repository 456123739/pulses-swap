"""
主题常量 / 路径 / 字体与尺寸令牌
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





# ==================== 常量定义 ====================
VERSION = "2.4.16"
AUTHOR = "NimShade"
PROJECT_NAME = "Pulses Swap"

IS_WINDOWS = sys.platform.startswith('win')

if getattr(sys, 'frozen', False):
    PROGRAM_DIR = Path(sys.executable).parent
else:
    PROGRAM_DIR = Path(__file__).parent

CONFIG_FILENAME = "PulsesSwap_config.json"
DATABASE_DIRNAME = "PulsesSwap_database"
APP_DIRNAME = "PulsesSwap"


def safe_print(*args, **kwargs) -> None:
    """windowed 打包（console=False）时 sys.stdout 为 None，直接 print 会抛
    AttributeError 并把异常处理路径本身弄崩，这里统一兜底。"""
    try:
        print(*args, **kwargs)
    except Exception:
        pass


def is_dir_writable(directory: Path) -> bool:
    """真实写测试：建目录 → 写临时文件 → 删掉。

    不用 os.access()：在 Windows 上它只看只读属性位，
    对 C:\\Program Files 这类 ACL 拒绝的目录会误报为可写。
    """
    probe = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / f".pulses_write_test_{os.getpid()}_{time.time_ns()}"
        with open(probe, 'w', encoding='utf-8') as f:
            f.write('ok')
        return True
    except Exception:
        return False
    finally:
        if probe is not None:
            try:
                probe.unlink()
            except Exception:
                pass


def get_user_data_dir() -> Path:
    """跨平台用户数据目录：Windows 用 %LOCALAPPDATA%\\PulsesSwap，
    其他平台用 $XDG_DATA_HOME/PulsesSwap 或 ~/.local/share/PulsesSwap。"""
    if IS_WINDOWS:
        base = os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA')
        if base:
            return Path(base) / APP_DIRNAME
        return Path.home() / 'AppData' / 'Local' / APP_DIRNAME
    xdg = os.environ.get('XDG_DATA_HOME')
    if xdg:
        return Path(xdg) / APP_DIRNAME
    return Path.home() / '.local' / 'share' / APP_DIRNAME


def resolve_data_base_dir() -> tuple[Path, bool]:
    """解析数据根目录。返回 (根目录, 是否处于便携模式)。

    优先级：
      1. 程序目录可写 → 直接用程序目录（绿色/便携模式，行为与旧版完全一致）
      2. 程序目录不可写，但数据库确实就在程序目录下
         → 仍然用程序目录（不改变已有用户的数据位置）
      3. 否则 → 用户数据目录（安装到 C:\\Program Files 时的正常路径）。
         即使回退，旧版写在程序目录的 PulsesSwap_config.json 仍会被
         load_db_path() 读到，老用户记下的数据库位置不会丢。
    """
    if is_dir_writable(PROGRAM_DIR):
        return PROGRAM_DIR, True
    if (PROGRAM_DIR / DATABASE_DIRNAME).exists():
        return PROGRAM_DIR, True
    return get_user_data_dir(), False


DATA_BASE_DIR, IS_PORTABLE_MODE = resolve_data_base_dir()

# v2.1 及以前固定把配置写在程序目录，读取时仍需兼容旧文件
LEGACY_BOOTSTRAP_FILE = PROGRAM_DIR / CONFIG_FILENAME

BOOTSTRAP_FILE = DATA_BASE_DIR / CONFIG_FILENAME
DEFAULT_DB_DIR = DATA_BASE_DIR / DATABASE_DIRNAME


def resource_path(filename: str) -> Path:
    """解析随程序分发的资源文件路径（源码运行 / PyInstaller frozen 都适用）。"""
    candidates = []
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        candidates.append(Path(meipass) / filename)
    here = Path(__file__).resolve().parent
    candidates.append(here / filename)                       # 与源码同级
    candidates.append(here.parent / 'packaging' / filename)  # 仓库内 packaging/
    for c in candidates:
        try:
            if c.exists():
                return c
        except Exception:
            continue
    return candidates[0]

LEGACY_DB_DIRNAME = "FGC_database"
LEGACY_CACHE_FILE = ".cache.json"
LEGACY_MIGRATED_MARKER = ".migrated_to_pulses_swap"

# ==================== Pulses 水墨淡色主题 ====================
C_WINDOW_BG      = "#F5F7F8"
C_PANEL_BG       = "#FFFFFF"
C_PANEL_ALT_BG   = "#EDF2F4"
C_INPUT_BG       = "#F7FAFB"

C_ACCENT         = "#5BA89A"
C_ACCENT_HOVER   = "#4A9285"
C_ACCENT_PRESSED = "#3D7A6E"
C_ACCENT_SOFT    = "#D6E8E4"

C_TEXT_MAIN      = "#2C3E3F"
C_TEXT_SECONDARY = "#6B7B7D"
C_TEXT_MUTED     = "#9AABAD"
C_TEXT_INVERSE   = "#FFFFFF"

C_BORDER         = "#D1DCDE"
C_DIVIDER        = "#E0E8EA"
C_FOCUS          = "#5BA89A"

C_SUCCESS        = "#5BA89A"
C_WARNING        = "#C9A961"
C_ERROR          = "#C97B7B"
C_INFO           = "#7B9DC9"

C_STATUS_NORMAL    = "#5BA89A"
C_STATUS_ADDED     = "#7B9DC9"
C_STATUS_REMOVED   = "#C97B7B"
C_STATUS_MODIFIED  = "#B58EC9"
C_STATUS_EXTRA     = "#C9A961"
C_STATUS_MISSING   = "#C97B7B"
C_STATUS_EMPTY     = "#9AABAD"

C_STATUS_NORMAL_BG    = "#E7F1EE"
C_STATUS_MISSING_BG   = "#F7E8E8"
C_STATUS_EXTRA_BG     = "#F7F2E5"
C_STATUS_MODIFIED_BG  = "#F2EAF7"
C_STATUS_ADDED_BG     = "#E8EFF7"

C_GUIDE_GLOW     = "#3D7A6E"

# 层级用色：宣传片靠 box-shadow 分层，CustomTkinter 的 CTkFrame 不支持投影，
# 这里用「卡片底色微差 + 更浅的发丝描边」近似（见 R_CARD 注释）。
C_CARD_BG        = "#FFFFFF"   # 卡片底色：与 C_WINDOW_BG(#F5F7F8) 形成微差层级
C_BORDER_SOFT    = "#E3EAEB"   # 卡片/控件描边：C_BORDER 向白底混合约 50%，
                               # 近似宣传片的 rgba 半透明极细低对比线

# ==================== 形状令牌（对齐宣传片 :root） ====================
# 宣传片：--r-window:26px / --r-card:16px / --r-control:12px
R_WINDOW   = 26   # 顶层窗口圆角；CustomTkinter 不能给 toplevel 画圆角，
                  # 实际由 DWM_CORNER_PREF 在 Windows 11 上近似（见该常量）
R_CARD     = 16   # 卡片 / 面板（含拖入框等 panel）
R_CONTROL  = 12   # 按钮 / 输入框 / 显示框 / 列表框 / 文本框
R_PROGRESS = 4    # 进度条：高 8px，取 4px 即为胶囊全圆角
BORDER_W       = 1   # 发丝描边宽度
BORDER_W_FOCUS = 3   # 新手引导高亮描边宽度

# Windows 11 DWM 窗口圆角偏好：1=直角(v2.1 现状) 2=圆角(约 8px) 3=小圆角(约 4px)。
# 26px 系统不可达，取最接近的 DWM 圆角；如需恢复 v2.1 的直角窗口改回 1。
DWM_CORNER_PREF = 2

# ==================== 字体令牌 ====================
# 跨平台回退链：先 Apple 字体，再 Windows 中文字体，最后通用无衬线。
# 启动时由 apply_font_fallbacks() 取第一个系统真实存在的族。
FONT_STACK_CN = (
    "SF Pro Display", "SF Pro Text", "PingFang SC", "Helvetica Neue",
    "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI",
    "Noto Sans CJK SC", "DejaVu Sans", "Arial",
)
FONT_STACK_MONO = (
    "SF Mono", "JetBrains Mono", "Cascadia Mono",
    "Consolas", "Menlo", "DejaVu Sans Mono", "Courier New",
)
# 兜底值（Windows 必备中文字体）；apply_font_fallbacks() 会就地更新这三个名字。
# ---- 运行时可变状态（统一通过 config.X 访问，避免各模块拿到快照） ----
UI_SCALE = 1.0
ANIMATIONS_ENABLED = True

FONT_FAMILY_CN   = "Microsoft YaHei UI"
FONT_FAMILY      = FONT_FAMILY_CN
FONT_FAMILY_MONO = "Consolas"

# 字号阶梯（整体上移 1~2pt，拉开层级、避免拥挤）
FS_TINY    = 11   # 提示 / 说明小字（原 10，用户反馈太小 → +1）
FS_SMALL   = 12   # 次要信息、单行标签、单选项（原 11）
FS_BODY    = 13   # 正文与控件默认字号（原 12）
FS_SUBHEAD = 15   # 卡片小节标题（原 13 粗体）
FS_TITLE   = 17   # 对话框主标题（原 15 粗体）
FS_DISPLAY = 21   # 展示型标题（原 19）

# ==================== 尺寸 / 间距令牌 ====================
H_CONTROL   = 32   # 按钮 / 输入框 / 显示框高度（原 28）
H_DROP_AREA = 76   # 拖入框高度（原 70）
H_LOG_BOX   = 132  # 日志页文本框高度（原 120）
H_HOME_LOG  = 112  # 主界面右下角日志栏高度（分割线下面那块）
H_PROGRESS  = 8    # 进度条高度
H_BTN_BAR   = 68   # 对话框底部按钮条高度（原 64）
H_TAB_HEAD  = 52   # 设置页选项卡头部高度（自绘分段控件）
PAD_CARD_X  = 16   # 卡片内左右内边距（原 12）
PAD_CARD_Y  = 12   # 卡片内上下内边距（原 10）
PAD_DIALOG  = 18   # 对话框内容边距（原 15/20）
PAD_GAP     = 10   # 卡片之间 / 行与行之间（原 8）
PAD_TIGHT   = 6    # 紧邻控件之间（原 4~6）
PAD_XS      = 4    # 极小间距（原 4）
PAD_MICRO   = 2    # 单选项与说明文字之间的极小间距（原 2）
PAD_INNER   = 8    # 控件内部文字与边框的距离
PAD_INDENT  = 32   # 单选项说明文字的缩进（与指示器对齐，原 32）
PAD_WINDOW  = 8    # 主窗口内容与窗口边框的距离

LEFT_COL_W = 340   # 主界面「Step 1/2/3」列宽度（与宣传片布局一致）
SIDEBAR_W  = 200   # 侧边导航栏宽度（原顶栏/菜单入口改为侧边栏页面）
H_NAV      = 38    # 侧边栏导航项高度

WINDOW_W, WINDOW_H = 1280, 900             # 主窗口（原 1150x760 偏小）
WINDOW_MIN_W, WINDOW_MIN_H = 1140, 812     # 主窗口最小尺寸（纵向预算见 H_STEP_*_MIN）

# 主界面左列纵向预算（px）。逐项按 FS_*/H_*/PAD_* 令牌累加，数值为实测需求：
#   Step1 整合包 ≈ 258 = 标题 + 拖入框 126 + 状态两行 + 内边距
#   Step2 预设管理 ≈ 350 = 标题 + 预设列表(4 行) + 导入框 76 + 按钮行 + 内边距
#   Step3 预设详情 ≈ 190 = 标题 + 三行信息 + 版本号行 + 内边距
#   Step2 预设   ≈ 275 = 标题 35 + 列表 ≥110 + 导入框 76 + 间隔 10 + 按钮行 32 + 内边距 12
#   Step3 详情   ≈ 138 = 标题 35 + 三行信息 51 + 版本行(8+32) + 内边距 12
#   合计 628 + 两个 PAD_GAP(10) = 648
# 顶栏（原生菜单栏）已移除，最小窗口内容高度 = 800 - 上下 PAD_WINDOW 16 = 784 ≥ 648，
# 余量 136px 通过 grid 行权重全部给 Step2 的预设列表（它会先被压缩），
# 因此 Step1/Step3 在任何允许的窗口尺寸下都不会被裁切。
H_STEP1_MIN = 258
H_STEP2_MIN = 292
H_STEP3_MIN = 190

# 覆盖层卡片 (宽, 高)：改为主窗口内覆盖层后高度由内容自适应，这里只取宽度
DLG_LOCATOR  = (680, 520)   # 数据库定位（含 4 个长文本按钮）
DLG_CHOICE   = (540, 380)   # 迁移后处理 / 身份提示 / 冲突处理
DLG_SMALL    = (520, 340)   # 迁移预设


def resolve_font_family(stack, fallback):
    """从回退链中挑第一个系统可用的字体族；无 Tk 环境时返回 fallback。"""
    try:
        from tkinter import font as tkfont
        available = set(tkfont.families())
    except Exception:
        return fallback
    for name in stack:
        if name in available:
            return name
    return fallback


def apply_font_fallbacks():
    """创建 root 之后调用：把 FONT_FAMILY* 解析成当前平台真实存在的字体族。"""
    global FONT_FAMILY_CN, FONT_FAMILY, FONT_FAMILY_MONO
    FONT_FAMILY_CN = resolve_font_family(FONT_STACK_CN, FONT_FAMILY_CN)
    FONT_FAMILY = FONT_FAMILY_CN
    FONT_FAMILY_MONO = resolve_font_family(FONT_STACK_MONO, FONT_FAMILY_MONO)
    return FONT_FAMILY_CN, FONT_FAMILY_MONO


ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")
ctk.set_widget_scaling(1.0)
