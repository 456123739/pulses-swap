"""调色板与尺寸令牌：水墨淡色主题。"""
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



# ==================== Pulses 水墨淡色主题 ====================
C_WINDOW_BG      = "#F2F3F5"   # 页面底：iOS 分组列表那种中性浅灰
C_PANEL_BG       = "#FFFFFF"
C_PANEL_ALT_BG   = "#EAEDEF"
C_INPUT_BG       = "#F4F6F7"   # 控件填充底：iOS 的 filled 风格，不靠描边

C_ACCENT         = "#5BA89A"
C_ACCENT_HOVER   = "#4A9285"
C_ACCENT_PRESSED = "#3D7A6E"
C_ACCENT_SOFT    = "#D6E8E4"

C_TEXT_MAIN      = "#2C3E3F"
C_TEXT_SECONDARY = "#6B7B7D"
C_TEXT_MUTED     = "#9AABAD"
C_TEXT_INVERSE   = "#FFFFFF"

C_BORDER         = "#DDE3E5"
C_DIVIDER        = "#E9EDEF"   # 分隔线（1px，缩进用）
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

# 页面切换幕布：比主文字更深一档的墨绿，和 icon.png 的底色接近。
C_COVER_BG       = "#233839"
C_COVER_TEXT     = "#F4F8F7"
C_COVER_MUTED    = "#9DBDB8"

# 层级用色：宣传片靠 box-shadow 分层，CustomTkinter 的 CTkFrame 不支持投影，
# 这里用「卡片底色微差 + 更浅的发丝描边」近似（见 R_CARD 注释）。
C_CARD_BG        = "#FFFFFF"   # 卡片底色：与 C_WINDOW_BG(#F5F7F8) 形成微差层级
C_BORDER_SOFT    = "#E9EDEF"   # 卡片描边已基本不用，保留给需要勾边的地方   # 卡片/控件描边：C_BORDER 向白底混合约 50%，
                               # 近似宣传片的 rgba 半透明极细低对比线

# ==================== 形状令牌（对齐宣传片 :root） ====================
# 宣传片：--r-window:26px / --r-card:16px / --r-control:12px
R_WINDOW   = 26   # 顶层窗口圆角；CustomTkinter 不能给 toplevel 画圆角，
                  # 实际由 DWM_CORNER_PREF 在 Windows 11 上近似（见该常量）
R_CARD     = 14   # 卡片 / 面板（iOS 分组卡片手感）
R_CONTROL  = 10   # 按钮 / 输入框 / 显示框 / 列表框 / 文本框
R_PROGRESS = 4    # 进度条：高 8px，取 4px 即为胶囊全圆角
BORDER_W       = 1   # 发丝描边宽度
BORDER_W_FOCUS = 3   # 新手引导高亮描边宽度

# Windows 11 DWM 窗口圆角偏好：1=直角(v2.1 现状) 2=圆角(约 8px) 3=小圆角(约 4px)。
# 26px 系统不可达，取最接近的 DWM 圆角；如需恢复 v2.1 的直角窗口改回 1。
DWM_CORNER_PREF = 2

# ==================== 尺寸 / 间距令牌 ====================
H_CONTROL   = 32   # 按钮 / 输入框 / 显示框高度（原 28）
H_DROP_AREA = 64   # 导入拖入框高度（比整合包那个大框矮，避免抢视线）
H_LOG_BOX   = 132  # 日志页文本框高度（原 120）
H_HOME_LOG  = 150  # 主界面右下角日志栏高度
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

LEFT_COL_W = 420   # 左列宽度：整合包 + 预设列表（详情条已移到右列顶部）
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
H_STEP1_MIN = 300
H_STEP2_MIN = 330
H_STEP3_MIN = 132   # 右列顶部「预设详情」横条

# 覆盖层卡片 (宽, 高)：改为主窗口内覆盖层后高度由内容自适应，这里只取宽度
DLG_LOCATOR  = (680, 520)   # 数据库定位（含 4 个长文本按钮）
DLG_CHOICE   = (540, 380)   # 迁移后处理 / 身份提示 / 冲突处理
DLG_SMALL    = (520, 340)   # 迁移预设
