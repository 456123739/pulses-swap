"""
Pulses Swap - 快速枪包切换器
作者: NimShade
版本: 2.3.5
描述: Minecraft Tacz 模组枪包快速切换工具
UI风格: Pulses 水墨淡色主题（customtkinter 圆角版本）

v2.3.5 更新:
  - 图标改用指定的三枚（填充型）：主界面房子 / 设置齿轮 / 日志文档，
    SVG 存在 packaging/icons/，由 make_icons.py 烘成 Tk 坐标
  - 引擎新增 solid 图元：填充多边形 + 1px 同色描边。
    填充型图标直接描边线稿在 17px 下只有 0.6px 粗、几乎看不见，
    加 1px 边之后才清楚（实测对比过）
  - 中心孔靠 Tk 多边形的 even-odd 填充自动挖出来（外轮廓与孔合进同一个
    polygon），不用背景色描一个假洞 —— 换底色/换选中态都不会露馅
  - make_icons.py 按 viewBox 归一化（原来写死 24，1024 视图的图标会放大 40 倍）

v2.3.4 更新:
  - 图标换成网上的官方图标集（构建期从 CDN 取 SVG 烘成坐标，运行时不联网）：
      主界面 = Lucide house，设置 = Heroicons cog-6-tooth（真正的直齿 + 中心孔），
      日志 = Lucide scroll-text
    选型逐个放大 8 倍 + 真实 17px 对比过：lucide/settings 像花、feather/settings
    没中心孔、lucide/cog 是轮辐（又变太阳）、tabler/settings 带方框太碎
  - 动画整体提速：页面/选项卡 420→260ms、滑块 380→240ms、图标动效 420→300ms、
    按钮 hover 150→110ms、卡片光晕 200→130ms、进度条 260→170ms……
    曲线也由 ease_in_out_cubic 换成起步更快的 ease_out_cubic
  - 新增 packaging/make_icons.py：图标烘制脚本（可重跑，--offline 用本地缓存）

v2.3.3 更新:
  - 修：设置图标画成了「圆 + 8 根放射线」，看着是太阳 —— 改成真正的齿形轮廓
    （8 齿多边形描边）+ 中心孔
  - 修：旋转时把圆的包围盒角点一起转了，45° 会把中心孔压成一根竖线；
    圆在旋转下不变，改成只转圆心、半径照旧

v2.3.2 更新:
  - 修：设置页选项卡「上一个」取的是已更新过的当前值，方向永远算成同一个
    → 表现是「不管点哪边都往左滑」；改为自己记录上一个选项卡
  - 切换方向统一为「点哪边内容就往哪边走」：点左面/上面的选项往左/上滑，
    点右面/下面的往右/下滑（侧边栏竖排 → 页面竖着滑）
  - 去掉全部 emoji：导航图标改成自绘矢量图元（房子/齿轮/三横线），
    不再依赖系统 emoji 字库；按钮文案去掉 📂📦📁📤🔄📋📖📄⏻⚠⏳❌✅⚡ 等字符
  - 侧边栏底部加状态卡（当前整合包 / 状态 / 当前预设），不再空一大片
  - 按钮给固定宽度，左列不再被按钮行撑宽（回到设计稿的 340px）

v2.3.1 更新:
  - 修：侧边栏 sticky="nsw" 不横向拉伸 → 一直只有 124px 宽（显得又窄又挤），
    改为 "nsew" 后按 200px 正常铺开
  - 页面切换方向按「点哪边内容就往哪边走」：点下面/右面的选项内容往下/右走，
    点上面/左面的往上/左走；侧边栏是竖排，页面就竖着滑
  - 切换曲线换成 S 曲线（ease_in_out_cubic）并把时长拉到 420ms，
    原来的 easeOutQuint 前 20% 就走完 2/3，看着像瞬切
  - 主界面右列改为：枪包列表 + 一键替换 → 分割线 → 日志栏（与日志页同一份日志流）
  - 设置页简洁化：删掉所有解释性小字，选项改成带动画的分段控件
  - 设置页底部常态只留「自动保存」，改动时短暂回显「✓ 已自动保存」
  - 图标点击动画：主界面轻跳 / 设置齿轮转 45°（切走转回）/ 日志轻摆
  - 日志分级：过程流水默认不占显示位，只保留最近一条有意义的状态；
    「设置已保存 / 已切换到 xx 模式」这类回显只在完整日志模式显示

v2.3.0 更新:
  - 顶栏（原生菜单栏）移除：原菜单项全部迁入界面，功能一个不少
  - 切换选项曲线动画：侧边栏导航与设置页选项卡改为自绘 Canvas 分段控件，
    选中滑块按缓动曲线逐帧滑动；页面切换为 Canvas 内整页推入/推出
  - 设置自动保存：单选项改动即写 .settings.json，不再需要保存按钮
  - 动画引擎：缓动曲线 + 颜色插值 + 去重补间调度，按钮/卡片/弹窗/Toast/
    进度条/加载指示/新手引导/折叠面板全部带过渡
  - 侧边栏只保留品牌 + 导航项，移除提示文案

v2.2.0 更新:
  - 侧边栏导航 + 设置页选项卡（替代原顶栏菜单入口与设置弹窗）
  - 全部提示/确认改为主窗口内覆盖层，不再新开系统窗口
  - 任务栏 AppUserModelID、窗口图标、窗口尺寸 1280x840

v2.1 更新:
  - 整合包选择区改为大拖入框，拖入任意整合包内文件/文件夹自动定位 tacz
  - 拖入预设包/更新包自动识别并加载，重名时询问是否替换
  - 「新建数据库」默认在程序目录下创建

v2.0 更新:
  - Win11 透明修复（强制不透明 + 禁用 DWM Mica/Acrylic），打包版同样适用
  - 新手引导系统：Step1/2/3/4 描述 + 当前步骤控件高亮描边
  - 引导根据实际状态自动切换
"""

import ctypes
try:                      # ctypes.wintypes 在非 Windows 上会直接抛 ValueError
    import ctypes.wintypes
except Exception:         # pragma: no cover - 仅影响 Windows 回收站功能
    ctypes.wintypes = None
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path
from tkinter import *
# 故意不导入 tkinter.messagebox：它是 Tk 原生模态对话框，必然新开系统窗口。
# 本文件所有提示/确认都走主窗口内的覆盖层（见 show_message），下方另有同名
# 兼容垫片 messagebox，保证漏改的调用点也不会退回系统新窗口。
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
VERSION = "2.3.5"
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

# ==================== Windows 原生回收站 ====================
FO_DELETE = 0x0003
FOF_ALLOWUNDO = 0x0040
FOF_NOCONFIRMATION = 0x0010
FOF_NOERRORUI = 0x0400
FOF_SILENT = 0x0004
FOF_NOCONFIRMMKDIR = 0x0200


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.wintypes.HWND),
        ("wFunc", ctypes.wintypes.UINT),
        ("pFrom", ctypes.wintypes.LPCWSTR),
        ("pTo", ctypes.wintypes.LPCWSTR),
        ("fFlags", ctypes.wintypes.USHORT),
        ("fAnyOperationsAborted", ctypes.wintypes.BOOL),
        ("hNameMappings", ctypes.wintypes.LPVOID),
        ("lpszProgressTitle", ctypes.wintypes.LPCWSTR),
    ]


def move_to_recycle_bin(path) -> bool:
    """使用 Windows 原生 SHFileOperationW 将文件/文件夹送入回收站"""
    if not IS_WINDOWS:
        return False
    try:
        p = Path(path)
        if not p.exists():
            return True
        path_str = str(p.resolve()) + '\0\0'
        op = _SHFILEOPSTRUCTW()
        op.hwnd = None
        op.wFunc = FO_DELETE
        op.pFrom = path_str
        op.pTo = None
        op.fFlags = (FOF_ALLOWUNDO | FOF_NOCONFIRMATION |
                     FOF_NOERRORUI | FOF_SILENT | FOF_NOCONFIRMMKDIR)
        op.fAnyOperationsAborted = False
        op.hNameMappings = None
        op.lpszProgressTitle = None
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        return (result == 0) and (not op.fAnyOperationsAborted)
    except Exception:
        return False


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
FONT_FAMILY_CN   = "Microsoft YaHei UI"
FONT_FAMILY      = FONT_FAMILY_CN
FONT_FAMILY_MONO = "Consolas"

# 字号阶梯（整体上移 1~2pt，拉开层级、避免拥挤）
FS_TINY    = 10   # 提示 / 说明小字（原 9）
FS_SMALL   = 11   # 次要信息、单行标签、单选项（原 10）
FS_BODY    = 12   # 正文与控件默认字号（原 10/11）
FS_SUBHEAD = 13   # 卡片小节标题（原 11 粗体）
FS_TITLE   = 15   # 对话框主标题（原 14 粗体）
FS_DISPLAY = 19   # 展示型标题（原 18）

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

WINDOW_W, WINDOW_H = 1280, 840             # 主窗口（原 1150x760 偏小）
WINDOW_MIN_W, WINDOW_MIN_H = 1140, 800     # 主窗口最小尺寸（纵向预算见 H_STEP_*_MIN）

# 主界面左列纵向预算（px）。逐项按 FS_*/H_*/PAD_* 令牌累加：
#   Step1 整合包 ≈ 215 = 标题(12+6+17) + 拖入框 126 + 间隔 6 + 状态两行 36 + 内边距 12
#   Step2 预设   ≈ 275 = 标题 35 + 列表 ≥110 + 导入框 76 + 间隔 10 + 按钮行 32 + 内边距 12
#   Step3 详情   ≈ 138 = 标题 35 + 三行信息 51 + 版本行(8+32) + 内边距 12
#   合计 628 + 两个 PAD_GAP(10) = 648
# 顶栏（原生菜单栏）已移除，最小窗口内容高度 = 800 - 上下 PAD_WINDOW 16 = 784 ≥ 648，
# 余量 136px 通过 grid 行权重全部给 Step2 的预设列表（它会先被压缩），
# 因此 Step1/Step3 在任何允许的窗口尺寸下都不会被裁切。
H_STEP1_MIN = 215
H_STEP2_MIN = 275
H_STEP3_MIN = 138

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


# ==================== 辅助函数 ====================
def sanitize_filename(name: str) -> str:
    if not name:
        return "unnamed"
    safe = "".join(c if c.isalnum() or c in " _-." else "_" for c in name)
    return safe.strip() or "unnamed"


def get_pack_id(pack_path: Path) -> str:
    name = pack_path.name
    safe_name = sanitize_filename(name)
    path_hash = hashlib.md5(str(pack_path.resolve()).encode('utf-8')).hexdigest()[:6]
    return f"{safe_name}_{path_hash}"


def generate_export_filename(preset_name: str, version: str,
                              is_incremental: bool, increment: int = 0) -> str:
    safe_preset = sanitize_filename(preset_name)
    safe_version = sanitize_filename(version) if version else "v1.0.0"
    if is_incremental:
        return f"{safe_preset}-{safe_version}-更新-{increment}.fgcupdate"
    return f"{safe_preset}-{safe_version}-完整.fgcpack"


def format_size(size_bytes: int) -> str:
    try:
        size = float(size_bytes)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    except Exception:
        return f"{size_bytes} B"


def get_item_fingerprint(item_path: Path) -> dict:
    if not item_path.exists():
        return {}
    if item_path.is_file():
        try:
            stat = item_path.stat()
            return {'type': 'zip', 'size': stat.st_size, 'file_count': 1}
        except Exception:
            return {}
    total_size = 0
    file_count = 0
    try:
        for item in item_path.rglob('*'):
            if item.is_file():
                total_size += item.stat().st_size
                file_count += 1
    except Exception:
        pass
    return {'type': 'folder', 'size': total_size, 'file_count': file_count}


def fingerprints_match(a: dict, b: dict) -> bool:
    if not a or not b:
        return False
    if a.get('size') != b.get('size'):
        return False
    if a.get('file_count', 0) != b.get('file_count', 0):
        return False
    return True


def locate_tacz_by_path(path: Path) -> Path | None:
    """
    从给定路径定位 tacz 文件夹。
    1) 如果是文件，从父目录开始；
    2) 本层找 tacz；
    3) 向上逐层找（最多 8 层）。
    返回 tacz 文件夹路径，找不到返回 None。
    """
    if not path:
        return None
    try:
        p = path if path.is_dir() else path.parent
    except Exception:
        return None
    # 本层
    c = p / 'tacz'
    if c.exists() and c.is_dir():
        return c
    # 向上
    current = p
    for _ in range(8):
        c = current / 'tacz'
        if c.exists() and c.is_dir():
            return c
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


# ==================== 动画引擎 ====================
# 需求：所有交互都要有过渡动画。Tk 控件没有逐控件 alpha，能动的只有
# 「位置 / 尺寸 / 颜色」三样，所以这里统一提供缓动函数 + 颜色插值 +
# 基于 after 的补间调度，上层只描述「从哪到哪」。
#
# 每个补间用 (widget, key) 标识：重复触发会自动取消上一帧序列，
# 不会出现两条动画互相拉扯；控件销毁后 after 回调由 Tk 自动丢弃。
_TWEENS: dict = {}


def clamp01(t):
    return 0.0 if t < 0 else (1.0 if t > 1 else float(t))


# ---------- 缓动曲线 ----------
def ease_linear(t):
    return t


def ease_out_cubic(t):
    """快速起步、缓慢收尾：位移类动画的默认曲线。"""
    return 1 - (1 - t) ** 3


def ease_out_quint(t):
    """比 cubic 更「急起缓停」，用于滑块/页面这种需要干脆利落的大位移。"""
    return 1 - (1 - t) ** 5


def ease_in_out_cubic(t):
    return 4 * t * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 3) / 2


def ease_out_back(t, overshoot=1.4):
    """带一点点回弹，用于浮层/提示的入场。"""
    t -= 1
    return t * t * ((overshoot + 1) * t + overshoot) + 1


# ---------- 数值 / 颜色插值 ----------
def lerp(a, b, t):
    return a + (b - a) * t


def hex_to_rgb(color):
    """把 '#RRGGBB' / '#RGB' 解析成 (r,g,b)；解析不了返回 None。"""
    if not isinstance(color, str):
        return None
    value = color.strip()
    if not value.startswith("#"):
        return None
    value = value[1:]
    try:
        if len(value) == 3:
            return tuple(int(c * 2, 16) for c in value)
        if len(value) >= 6:
            return (int(value[0:2], 16), int(value[2:4], 16),
                    int(value[4:6], 16))
    except ValueError:
        return None
    return None


def rgb_to_hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(
        int(max(0, min(255, round(rgb[0])))),
        int(max(0, min(255, round(rgb[1])))),
        int(max(0, min(255, round(rgb[2])))))


def lerp_color(c1, c2, t):
    """颜色插值；任一端不是合法 hex 时退化为端点取色，绝不抛异常。"""
    a = hex_to_rgb(c1)
    b = hex_to_rgb(c2)
    if a is None or b is None:
        return c1 if t < 0.5 else c2
    return rgb_to_hex((lerp(a[0], b[0], t), lerp(a[1], b[1], t),
                       lerp(a[2], b[2], t)))


# ---------- 补间调度 ----------
def cancel_tween(widget, key):
    job = _TWEENS.pop((id(widget), key), None)
    if job is not None:
        try:
            widget.after_cancel(job)
        except Exception:
            pass


def cancel_all_tweens(widget):
    for token in [k for k in _TWEENS if k[0] == id(widget)]:
        cancel_tween(widget, token[1])


def tween(widget, key, duration_ms, on_frame, on_done=None,
          easing=ease_out_cubic, fps=60):
    """
    用 widget.after 驱动一条补间时间线。

    on_frame(缓动值, 线性进度) 每帧调用；进度按真实耗时计算，掉帧不会变慢。
    另有帧数上限兜底：即使事件循环被压缩（例如同步 after 的测试环境），
    动画也一定会在有限帧内收敛到终点，不会自锁。
    """
    cancel_tween(widget, key)
    interval = max(1, int(round(1000.0 / max(1, fps))))
    duration_ms = max(1, int(duration_ms))
    max_frames = int(duration_ms / interval) + 3
    token = (id(widget), key)
    start = time.perf_counter()
    state = {"frames": 0}

    def step():
        if token not in _TWEENS:
            return
        state["frames"] += 1
        elapsed = (time.perf_counter() - start) * 1000.0
        raw = clamp01(elapsed / duration_ms)
        if state["frames"] >= max_frames:
            raw = 1.0
        try:
            on_frame(easing(raw), raw)
        except Exception:
            pass
        if raw >= 1.0:
            _TWEENS.pop(token, None)
            if on_done is not None:
                try:
                    on_done()
                except Exception:
                    pass
            return
        try:
            _TWEENS[token] = widget.after(interval, step)
        except Exception:
            _TWEENS.pop(token, None)

    # 先占位再排期：万一宿主把 after 做成同步回调，step 里的守卫也能认出自己
    _TWEENS[token] = -1
    try:
        job = widget.after(interval, step)
    except Exception:
        _TWEENS.pop(token, None)
        return
    if token in _TWEENS:
        _TWEENS[token] = job


def attach_hover_glow(widget, base_color=None, hover_color=None, duration_ms=130):
    """卡片/拖入框的 hover 描边过渡：进入混向强调色，离开混回原色。

    卡片里通常还嵌着按钮/标签，鼠标从卡片移到子控件上时 Tk 会给卡片发
    <Leave>，直接响应会来回闪。这里把「离开」延后 90ms，期间若有 <Enter>
    就撤销，等效于「指针真的移出卡片」才收光。
    """
    try:
        base_color = base_color or widget.cget("border_color")
    except Exception:
        base_color = C_BORDER_SOFT
    if hex_to_rgb(base_color) is None:
        base_color = C_BORDER_SOFT
    hover_color = hover_color or C_ACCENT_SOFT
    state = {"color": base_color, "leave_job": None}

    def _to(target, ms=duration_ms):
        start = state["color"]
        if start == target:
            return

        def frame(e, raw):
            state["color"] = lerp_color(start, target, e)
            try:
                widget.configure(border_color=state["color"])
            except Exception:
                pass

        frame(0.0, 0.0)
        tween(widget, "glow", ms, frame, easing=ease_in_out_cubic)

    def _cancel_leave():
        if state["leave_job"] is not None:
            try:
                widget.after_cancel(state["leave_job"])
            except Exception:
                pass
            state["leave_job"] = None

    def _on_enter(_event=None):
        _cancel_leave()
        _to(hover_color)

    def _on_leave(_event=None):
        _cancel_leave()

        def fire():
            state["leave_job"] = None
            _to(base_color)

        try:
            state["leave_job"] = widget.after(90, fire)
        except Exception:
            fire()

    try:
        widget.bind("<Enter>", _on_enter, add="+")
        widget.bind("<Leave>", _on_leave, add="+")
    except Exception:
        pass
    return widget


# ==================== 动画控件 ====================
class AnimatedButton(ctk.CTkButton):
    """带曲线过渡的按钮：hover / 按下都是逐帧混色，而不是瞬间跳色。

    CTk 自带的 hover 是「瞬时换色」，这里把它的 hover 目标设成底色把它架空，
    再由本类用补间驱动 fg_color。CTk 内部处理器与本类处理器在同一次事件
    分发里先后执行，本类每次都从当前插值色继续，因此不会看到跳变。
    """

    def __init__(self, master, base_color, hover_target, press_color=None,
                 **kwargs):
        kwargs["fg_color"] = base_color
        kwargs["hover_color"] = base_color
        super().__init__(master, **kwargs)
        self._base_color = base_color
        self._hover_target = hover_target
        self._press_color = press_color or hover_target
        self._current = base_color
        self._hovering = False
        try:
            self.bind("<Enter>", self._on_enter, add="+")
            self.bind("<Leave>", self._on_leave, add="+")
            self.bind("<ButtonPress-1>", self._on_press, add="+")
            self.bind("<ButtonRelease-1>", self._on_release, add="+")
        except Exception:
            pass

    def _enabled(self):
        try:
            return str(self.cget("state")) == "normal"
        except Exception:
            return True

    def _reassert(self):
        try:
            self.configure(fg_color=self._current)
        except Exception:
            pass

    def _to(self, target, duration=110):
        if target == self._current:
            return
        start = self._current

        def frame(e, raw):
            self._current = lerp_color(start, target, e)
            try:
                self.configure(fg_color=self._current)
            except Exception:
                pass

        frame(0.0, 0.0)
        tween(self, "bg", duration, frame, easing=ease_out_cubic)

    def _on_enter(self, _event=None):
        self._hovering = True
        self._reassert()
        if self._enabled():
            self._to(self._hover_target)

    def _on_leave(self, _event=None):
        self._hovering = False
        self._reassert()
        self._to(self._base_color)

    def _on_press(self, _event=None):
        self._reassert()
        if self._enabled():
            self._to(self._press_color, 70)

    def _on_release(self, _event=None):
        self._reassert()
        if not self._enabled():
            return
        self._to(self._hover_target if self._hovering else self._base_color, 120)


class CanvasSegmented(Canvas):
    """自绘分段控件（侧边栏导航 / 设置页选项卡共用）。

    选中态是一个可以逐帧滑动的药丸，hover 也是逐帧混色 —— 之所以不用
    CTkButton 直接换色，是因为「切换选项」要的是一条连续的曲线轨迹。
    Canvas 同时会把子项裁剪在自身范围内，滑动过程不会溢到隔壁区域。

    items 支持三种写法：
        (key, text)                    无图标（设置页选项卡用）
        (key, icon, text)              图标 + 文字
        (key, icon, text, anim)        anim 见 ICON_ANIMS
    图标单独成一个 canvas text item，因此可以单独做动画：
        rotate  选中后转到 icon_angle 度，切走时转回 0（设置齿轮）
        hop     选中时原地轻轻弹跳一次
        wobble  选中时左右轻摆一次
    """

    ICON_ANIMS = ("rotate", "hop", "wobble")

    def __init__(self, parent, items, command=None, orientation="vertical",
                 item_height=H_NAV, pad=4, gap=4, radius=R_CONTROL,
                 bg_color=C_CARD_BG, pill_color=C_ACCENT_SOFT,
                 hover_color=C_ACCENT_SOFT, text_color=C_TEXT_MAIN,
                 active_text_color=C_ACCENT, font_size=FS_BODY,
                 bold_active=False, text_anchor="w", text_pad=14,
                 duration_ms=240, hover_ms=110, width=1, height=1,
                 icon_pad=13, icon_half=9, icon_gap=8, icon_anim_ms=300,
                 icon_angle=45.0, icon_hop=6, icon_wobble=16, icon_size=17):
        super().__init__(parent, bg=bg_color, highlightthickness=0, bd=0,
                         width=width, height=height)
        self._items = [self._normalize_item(item) for item in items]
        self._keys = [key for key, _, _, _ in self._items]
        self._command = command
        self._orientation = orientation
        self._item_height = item_height
        self._pad = pad
        self._gap = gap
        self._radius = radius
        self._bg = bg_color
        self._pill_color = pill_color
        self._hover_color = hover_color
        self._text_color = text_color
        self._active_text_color = active_text_color
        # 字体族要在构造时取（apply_font_fallbacks 会就地改写全局名）
        self._font = (FONT_FAMILY, font_size)
        self._font_active = (FONT_FAMILY, font_size,
                             "bold" if bold_active else "normal")
        self._icon_font = (FONT_FAMILY, font_size)
        self._text_anchor = text_anchor
        self._text_pad = text_pad
        self._duration_ms = duration_ms
        self._hover_ms = hover_ms
        self._icon_pad = icon_pad
        self._icon_half = icon_half
        self._icon_gap = icon_gap
        self._icon_anim_ms = icon_anim_ms
        self._icon_angle = float(icon_angle)
        self._icon_hop = float(icon_hop)
        self._icon_wobble = float(icon_wobble)
        self._icon_size = float(icon_size)

        self._active = None
        self._rects = []
        self._text_ids = []
        self._text_colors = {}
        self._icon_ids = []          # 每项：图元 id 列表（矢量图标会有多条）
        self._icon_prims = []        # 每项：图元描述；None 表示文字图标
        self._icon_colors = {}
        self._icon_angles = [0.0] * len(self._items)
        self._icon_origins = [(0.0, 0.0)] * len(self._items)
        self._pill_id = None
        self._pill_rect = None
        self._pill_alpha = 0.0
        self._hover_id = None
        self._hover_rect = None
        self._hover_alpha = 0.0
        self._hover_index = -1
        self._size = (0, 0)
        self._laid_out = False

        # 层级：悬停层 -> 滑块 -> 图标 -> 文字
        self._hover_id = self.create_polygon(
            *self._rect_points((-6, -6, -3, -3)), smooth=True, splinesteps=24,
            fill=bg_color, outline="")
        self._pill_id = self.create_polygon(
            *self._rect_points((-6, -6, -3, -3)), smooth=True, splinesteps=24,
            fill=bg_color, outline="")
        for index, (_, icon, text, _anim) in enumerate(self._items):
            if icon.startswith("@"):
                # 矢量图标：不用 emoji 字库，颜色/角度都能动
                ids, prims = draw_vector_icon(
                    self, icon[1:], -40, -40, self._icon_size, text_color)
                self._icon_ids.append(ids or None)
                self._icon_prims.append(prims)
            elif icon:
                self._icon_ids.append(
                    [self.create_text(0, 0, text=icon, fill=text_color,
                                       anchor="center", font=self._icon_font)])
                self._icon_prims.append(None)
            else:
                self._icon_ids.append(None)
                self._icon_prims.append(None)
            self._icon_colors[index] = text_color
            self._text_ids.append(
                self.create_text(0, 0, text=text, fill=text_color,
                                  anchor=text_anchor, font=self._font))
            self._text_colors[index] = text_color
        self.bind("<Configure>", self._on_configure)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    @staticmethod
    def _normalize_item(item):
        """统一成 (key, icon, text, anim)。"""
        if len(item) == 2:
            return (item[0], "", str(item[1]), None)
        if len(item) == 3:
            return (item[0], str(item[1]), str(item[2]), None)
        return (item[0], str(item[1]), str(item[2]), item[3])

    # ---------- 几何 ----------
    def _rect_points(self, rect):
        x1, y1, x2, y2 = rect
        radius = max(0.0, min(float(self._radius), (x2 - x1) / 2.0,
                              (y2 - y1) / 2.0))
        return [x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
                x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
                x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1]

    def _on_configure(self, event):
        size = (max(1, event.width), max(1, event.height))
        if size == self._size:
            return
        self._size = size
        self._layout(*size)

    def _layout(self, width, height):
        count = max(1, len(self._items))
        rects = []
        if self._orientation == "vertical":
            x1, x2 = self._pad, width - self._pad
            for index in range(count):
                y1 = self._pad + index * (self._item_height + self._gap)
                rects.append((x1, y1, x2, y1 + self._item_height))
        else:
            inner = width - 2 * self._pad - (count - 1) * self._gap
            item_w = inner / float(count)
            y1, y2 = self._pad, height - self._pad
            x = self._pad
            for _ in range(count):
                rects.append((x, y1, x + item_w, y2))
                x += item_w + self._gap
        self._rects = rects
        for index, text_id in enumerate(self._text_ids):
            x1, y1, x2, y2 = rects[index]
            center_y = (y1 + y2) / 2.0
            if self._icon_ids[index] is not None:
                # 图标单独占位，绕自身中心旋转
                icon_x = x1 + self._icon_pad + self._icon_half
                self._icon_origins[index] = (icon_x, center_y)
                self._place_icon(index, icon_x, center_y)
                label_x = icon_x + self._icon_half + self._icon_gap
            else:
                label_x = x1 + self._text_pad
            if self._text_anchor == "w":
                self.coords(text_id, label_x, center_y)
            else:
                self.coords(text_id, (x1 + x2) / 2.0, center_y)
        if self._active in self._keys:
            target = rects[self._keys.index(self._active)]
            resizing = self._pill_rect is not None
            self._pill_rect = target
            self.coords(self._pill_id, *self._rect_points(target))
            if resizing:
                # 窗口尺寸变化会打乱滑块的动画轨迹：取消补间并直接落到目标项
                cancel_tween(self, "pill")
                self._pill_alpha = 1.0
                self.itemconfigure(self._pill_id, fill=self._pill_color)
            elif not self._laid_out:
                # 首次拿到真实尺寸：补一次带淡入的选中，滑块不会「啪」地出现
                self._laid_out = True
                self.select(self._active, animate=True)
            else:
                self._pill_alpha = 1.0
                self.itemconfigure(self._pill_id, fill=self._pill_color)
        if 0 <= self._hover_index < len(rects):
            self._hover_rect = rects[self._hover_index]
            self.coords(self._hover_id, *self._rect_points(self._hover_rect))

    def _index_at(self, x, y):
        for index, (x1, y1, x2, y2) in enumerate(self._rects):
            if x1 <= x <= x2 and y1 <= y <= y2:
                return index
        return -1

    # ---------- 交互 ----------
    def _on_motion(self, event):
        self._set_hover(self._index_at(event.x, event.y))

    def _on_leave(self, _event=None):
        self._set_hover(-1)

    def _on_click(self, event):
        index = self._index_at(event.x, event.y)
        if index < 0:
            return
        self.select(self._keys[index], notify=True)

    def _set_hover(self, index, animate=True):
        if index == self._hover_index:
            return
        self._hover_index = index
        active_index = (self._keys.index(self._active)
                        if self._active in self._keys else -1)
        target_alpha = 1.0 if (0 <= index < len(self._rects)
                               and index != active_index) else 0.0
        if 0 <= index < len(self._rects):
            self._hover_rect = self._rects[index]
            try:
                self.coords(self._hover_id,
                            *self._rect_points(self._hover_rect))
            except Exception:
                pass
        start_alpha = self._hover_alpha

        def paint(alpha):
            self._hover_alpha = alpha
            try:
                self.itemconfigure(
                    self._hover_id,
                    fill=lerp_color(self._bg, self._hover_color, alpha))
            except Exception:
                pass

        if not animate or self._hover_ms <= 0:
            paint(target_alpha)
            return

        def frame(e, raw):
            paint(lerp(start_alpha, target_alpha, e))

        tween(self, "hover", self._hover_ms, frame, easing=ease_out_cubic)

    # ---------- 选中 ----------
    def current(self):
        """当前选中项的 key（未选中返回 None）。"""
        return self._active

    def index_of(self, key):
        return self._keys.index(key) if key in self._keys else -1

    def select(self, key, animate=True, notify=False):
        if key not in self._keys:
            return
        index = self._keys.index(key)
        previous = self._active
        self._active = key
        self._animate_texts(previous, index, animate)
        self._animate_icons(previous, index, animate)
        self._move_pill(index, animate)
        if self._hover_index == index:
            self._set_hover(-1, animate=animate)
        if notify and callable(self._command):
            try:
                self._command(key)
            except Exception:
                pass

    def _move_pill(self, index, animate=True):
        if not self._rects:
            return
        target = self._rects[index]
        if not animate:
            self._pill_rect = target
            self._pill_alpha = 1.0
            self.coords(self._pill_id, *self._rect_points(target))
            self.itemconfigure(self._pill_id, fill=self._pill_color)
            return
        start = self._pill_rect or target
        start_alpha = self._pill_alpha

        def frame(e, raw):
            self._pill_rect = tuple(lerp(a, b, e)
                                    for a, b in zip(start, target))
            self._pill_alpha = lerp(start_alpha, 1.0, e)
            self.coords(self._pill_id, *self._rect_points(self._pill_rect))
            self.itemconfigure(
                self._pill_id,
                fill=lerp_color(self._bg, self._pill_color, self._pill_alpha))

        def done():
            self._pill_rect = target
            self._pill_alpha = 1.0
            self.coords(self._pill_id, *self._rect_points(target))
            self.itemconfigure(self._pill_id, fill=self._pill_color)

        frame(0.0, 0.0)      # 立即落到起点，滑块不等待第一帧
        tween(self, "pill", self._duration_ms, frame, done,
              easing=ease_out_cubic)

    def _animate_texts(self, previous_key, active_index, animate=True):
        for index, text_id in enumerate(self._text_ids):
            is_active = (index == active_index)
            target = self._active_text_color if is_active else self._text_color
            start = self._text_colors.get(index, self._text_color)
            try:
                self.itemconfigure(text_id,
                                   font=self._font_active if is_active
                                   else self._font)
            except Exception:
                pass
            if not animate or start == target:
                self._text_colors[index] = target
                try:
                    self.itemconfigure(text_id, fill=target)
                except Exception:
                    pass
                continue

            def frame(e, raw, i=index, s=start, t=target, item=text_id):
                color = lerp_color(s, t, e)
                self._text_colors[i] = color
                try:
                    self.itemconfigure(item, fill=color)
                except Exception:
                    pass

            frame(0.0, 0.0)
            tween(self, "text{}".format(index), 160, frame,
                  easing=ease_out_cubic)

    # ---------- 图标动画 ----------
    def _place_icon(self, index, x, y):
        """把某个图标摆到 (x, y)：矢量图标按当前角度重算坐标，文字图标直接挪。"""
        ids = self._icon_ids[index]
        if not ids:
            return
        prims = self._icon_prims[index]
        if prims:
            redraw_vector_icon(self, ids, prims, x, y, self._icon_size,
                               self._icon_angles[index])
        else:
            try:
                self.coords(ids[0], x, y)
            except Exception:
                pass

    def _set_icon_color(self, index, color):
        ids = self._icon_ids[index]
        if not ids:
            return
        prims = self._icon_prims[index]
        if prims:
            paint_vector_icon(self, ids, prims, color)
        else:
            try:
                self.itemconfigure(ids[0], fill=color)
            except Exception:
                pass

    def _set_icon_angle(self, index, degrees):
        self._icon_angles[index] = float(degrees)
        if not self._icon_ids[index]:
            return
        if self._icon_prims[index]:
            # 矢量图标：自己算旋转后的坐标（不依赖 Tk 的 text -angle）
            origin = self._icon_origins[index]
            self._place_icon(index, origin[0], origin[1])
            return
        try:
            # Tk 8.6+ 的 canvas text 才支持 -angle；不支持时静默退化为不旋转
            self.itemconfigure(self._icon_ids[index][0],
                               angle=self._icon_angles[index])
        except Exception:
            pass

    def _animate_icons(self, previous_key, active_index, animate=True):
        previous_index = (self._keys.index(previous_key)
                          if previous_key in self._keys else -1)
        for index in dict.fromkeys((active_index, previous_index)):
            if index is None or index < 0:
                continue
            is_active = (index == active_index)
            self._animate_icon_color(index, is_active, animate)
            self._play_icon(index, is_active, animate)

    def _animate_icon_color(self, index, is_active, animate=True):
        if not self._icon_ids[index]:
            return
        target = self._active_text_color if is_active else self._text_color
        start = self._icon_colors.get(index, self._text_color)
        if not animate or start == target:
            self._icon_colors[index] = target
            self._set_icon_color(index, target)
            return

        def frame(e, raw):
            color = lerp_color(start, target, e)
            self._icon_colors[index] = color
            self._set_icon_color(index, color)

        tween(self, "iconcolor{}".format(index), 160, frame,
              easing=ease_out_cubic)

    def _play_icon(self, index, activate, animate=True):
        """图标动画：rotate 选中后转到 icon_angle、切走转回 0；
        hop / wobble 是选中时一次性播放的小动效，切走时无需复位。"""
        if index < 0 or index >= len(self._icon_ids):
            return
        anim = self._items[index][3]
        if not self._icon_ids[index] or anim not in self.ICON_ANIMS:
            return
        key = "icon{}".format(index)

        if anim == "rotate":
            start = self._icon_angles[index]
            target = self._icon_angle if activate else 0.0
            if not animate or abs(target - start) < 0.01:
                self._set_icon_angle(index, target)
                return

            def frame(e, raw):
                self._set_icon_angle(index, lerp(start, target, e))

            frame(0.0, 0.0)
            tween(self, key, self._icon_anim_ms, frame,
                  easing=ease_in_out_cubic)
            return

        if not activate:
            return

        origin = self._icon_origins[index]

        if anim == "hop":
            def frame(e, raw):
                # 三角形包络：起跳 -> 顶点 -> 落回，末帧一定回到原位
                tri = raw * 2.0 if raw <= 0.5 else (1.0 - raw) * 2.0
                self._place_icon(index, origin[0],
                                 origin[1] - self._icon_hop * tri)

            frame(0.0, 0.0)
            tween(self, key, 260, frame, easing=ease_linear)
            return

        def frame(e, raw):
            tri = raw * 2.0 if raw <= 0.5 else (1.0 - raw) * 2.0
            self._set_icon_angle(index, -self._icon_wobble * tri)

        frame(0.0, 0.0)
        tween(self, key, 300, frame, easing=ease_linear)


class SlideStack:
    """把若干页面放进一个 Canvas，用缓动曲线做「推入 / 推出」切换。

    Canvas 会裁剪内嵌窗口，所以页面在滑动过程中不会溢到侧边栏上 ——
    这也是这里不直接用 place() 搬页面的原因（Tk 普通容器不裁剪子控件）。
    """

    def __init__(self, parent, bg_color=C_WINDOW_BG, duration_ms=260,
                 easing=ease_out_cubic):
        self.canvas = Canvas(parent, bg=bg_color, highlightthickness=0, bd=0)
        self.canvas.pack(fill=BOTH, expand=True)
        self.bg_color = bg_color
        self.duration_ms = duration_ms
        self.easing = easing
        self.frames = {}
        self.items = {}
        self.order = []
        self.current = None
        self._size = (1, 1)
        self.canvas.bind("<Configure>", self._on_configure)

    def add(self, key, frame):
        try:
            frame.configure(fg_color=self.bg_color)
        except Exception:
            pass
        item = self.canvas.create_window(
            0, 0, window=frame, anchor="nw",
            width=self._size[0], height=self._size[1])
        self.canvas.itemconfigure(item, state="hidden")
        self.frames[key] = frame
        self.items[key] = item
        if key not in self.order:
            self.order.append(key)
        return item

    def _on_configure(self, event):
        self._size = (max(1, event.width), max(1, event.height))
        for item in self.items.values():
            try:
                self.canvas.itemconfigure(item, width=self._size[0],
                                          height=self._size[1])
            except Exception:
                pass
        if (id(self.canvas), "slide") in _TWEENS:
            # 切换动画进行中被重排：轨迹已失效，直接落到终点
            cancel_tween(self.canvas, "slide")
            self._settle()
        if self.current in self.items:
            self.canvas.coords(self.items[self.current], 0, 0)

    def _settle(self):
        """把所有页面归位：当前页贴左可见，其余隐藏。"""
        for key, item in self.items.items():
            try:
                self.canvas.coords(item, 0, 0)
                self.canvas.itemconfigure(
                    item, state="normal" if key == self.current else "hidden")
            except Exception:
                pass

    def show(self, key, animate=True, direction=1, axis="x"):
        """direction: +1 = 新页从右/下方进来（内容往左/上走）；-1 反之。
        axis: 侧边栏是竖排 → 页面竖着滑；设置页选项卡是横排 → 横着滑。"""
        if key not in self.items or key == self.current:
            return
        span = float(self._size[0] if axis == "x" else self._size[1])
        previous = self.current
        new_item = self.items[key]
        try:
            self.canvas.itemconfigure(new_item, state="normal")
            self.canvas.tag_raise(new_item)
        except Exception:
            pass
        self.current = key
        if previous is None or not animate:
            try:
                self.canvas.coords(new_item, 0, 0)
                if previous is not None and previous in self.items:
                    self.canvas.itemconfigure(self.items[previous],
                                              state="hidden")
                    self.canvas.coords(self.items[previous], 0, 0)
            except Exception:
                pass
            return

        old_item = self.items[previous]
        offset = span * (1 if direction >= 0 else -1)

        def frame(e, raw):
            try:
                if axis == "x":
                    self.canvas.coords(new_item, lerp(offset, 0.0, e), 0)
                    self.canvas.coords(old_item, lerp(0.0, -offset, e), 0)
                else:
                    self.canvas.coords(new_item, 0, lerp(offset, 0.0, e))
                    self.canvas.coords(old_item, 0, lerp(0.0, -offset, e))
            except Exception:
                pass

        def done():
            try:
                self.canvas.coords(new_item, 0, 0)
                self.canvas.coords(old_item, 0, 0)
                self.canvas.itemconfigure(old_item, state="hidden")
            except Exception:
                pass

        frame(0.0, 0.0)      # 先摆到起点，避免第一帧前闪一下原位
        tween(self.canvas, "slide", self.duration_ms, frame, done,
              easing=self.easing)


class Toast:
    """右上角浮出提示：曲线滑入 + 自动淡出，全程不阻塞操作。"""

    def __init__(self, host, text, kind="success", duration_ms=1700):
        self.host = host
        self.color = {"success": C_SUCCESS, "info": C_ACCENT,
                      "warning": C_WARNING, "error": C_ERROR}.get(kind, C_ACCENT)
        self.frame = ctk.CTkFrame(host.overlay_host, fg_color=C_PANEL_BG,
                                   corner_radius=R_CONTROL,
                                   border_width=BORDER_W,
                                   border_color=self.color)
        self.label = ctk.CTkLabel(self.frame, text=text, text_color=self.color,
                                   font=(FONT_FAMILY, FS_SMALL),
                                   fg_color="transparent")
        self.label.pack(padx=PAD_CARD_X, pady=PAD_TIGHT)
        self._offset = 28
        self._hold_ms = duration_ms
        self._place()
        self._play_in()

    def _place(self):
        try:
            self.frame.place(relx=1.0, rely=0.0, anchor="ne",
                              x=-PAD_WINDOW - self._offset, y=PAD_WINDOW)
        except Exception:
            pass

    def _play_in(self):
        def frame(e, raw):
            self._offset = lerp(28.0, 0.0, e)
            self._place()

        def done():
            try:
                self.host.root.after(self._hold_ms, self._play_out)
            except Exception:
                pass

        frame(0.0, 0.0)
        tween(self.frame, "toast_in", 200, frame, done, easing=ease_out_back)

    def _play_out(self):
        def frame(e, raw):
            self._offset = lerp(0.0, 28.0, e)
            self._place()
            try:
                self.frame.configure(
                    fg_color=lerp_color(C_PANEL_BG, C_WINDOW_BG, e),
                    border_color=lerp_color(self.color, C_WINDOW_BG, e))
                self.label.configure(
                    text_color=lerp_color(self.color, C_WINDOW_BG, e))
            except Exception:
                pass

        tween(self.frame, "toast_out", 190, frame, self.close,
              easing=ease_in_out_cubic)

    def close(self):
        cancel_all_tweens(self.frame)
        try:
            self.frame.destroy()
        except Exception:
            pass


# ==================== 矢量图标 ====================
# 不用 emoji 字体：emoji 走系统的 emoji 字库（Windows 上是 Segoe UI Emoji），
#   · 颜色不跟 text_color 走，选中态染色基本失效；
#   · 不少字形是彩色位图，旋转/缩放都不干净；
#   · 没装 emoji 字库的机器上直接掉成方框。
# 这里改成用 Canvas 图元自己画：颜色能逐帧混、角度能逐帧转、任何平台一致。
# 每个图标用 -1..1 的归一化坐标描述，绘制/旋转都只做一次坐标变换。
def _gear_profile(teeth=8, r_out=1.0, r_in=0.70):
    """齿轮轮廓：每个齿 4 个点（齿顶平段 + 齿根平段），连成闭合多边形。

    之前用「圆 + 8 根放射线」画，看着就是太阳；真正的齿轮得有齿形。
    """
    pts = []
    step = 2.0 * math.pi / teeth
    for i in range(teeth):
        base = i * step
        for frac, radius in ((0.04, r_out), (0.42, r_out),
                             (0.54, r_in), (0.92, r_in)):
            ang = base + frac * step
            pts.extend((radius * math.cos(ang), radius * math.sin(ang)))
    return tuple(round(v, 4) for v in pts)


_ICON_PRIMS = {
    "home": (
        ("solid", 0.5269, 0.8394, 0.2219, 0.8394, 0.1888, 0.8358, 0.158, 0.8257, 0.13, 0.8097, 0.1057, 0.7885, 0.0856, 0.7628, 0.0704, 0.7333, 0.0608, 0.7007, 0.0575, 0.6658, 0.0575, 0.5194, 0.0563, 0.5083, 0.0532, 0.4979, 0.0482, 0.4885, 0.0417, 0.4802, 0.0338, 0.4734, 0.0247, 0.4683, 0.0147, 0.465, 0.004, 0.4638, -0.0137, 0.4638, -0.0244, 0.465, -0.0344, 0.4683, -0.0434, 0.4734, -0.0514, 0.4803, -0.0579, 0.4885, -0.0629, 0.498, -0.066, 0.5084, -0.0671, 0.5196, -0.0671, 0.6658, -0.0704, 0.7007, -0.08, 0.7333, -0.0952, 0.7628, -0.1153, 0.7885, -0.1396, 0.8097, -0.1675, 0.8257, -0.1982, 0.8358, -0.2312, 0.8394, -0.5367, 0.8394, -0.5697, 0.8358, -0.6006, 0.8257, -0.6284, 0.8097, -0.6527, 0.7885, -0.6728, 0.7628, -0.6879, 0.7333, -0.6975, 0.7007, -0.7008, 0.6658, -0.7008, 0.0756, -0.7175, 0.0756, -0.7482, 0.0731, -0.774, 0.0661, -0.7953, 0.056, -0.8125, 0.0439, -0.8259, 0.0309, -0.8359, 0.0182, -0.8429, 0.0071, -0.8471, -0.0015, -0.8511, -0.0119, -0.8548, -0.0255, -0.8573, -0.0418, -0.8577, -0.0605, -0.8549, -0.0812, -0.8482, -0.1034, -0.8364, -0.1269, -0.8188, -0.1512, -0.1277, -0.8094, -0.1157, -0.8221, -0.1024, -0.8335, -0.088, -0.8433, -0.0726, -0.8516, -0.0563, -0.8581, -0.0395, -0.8628, -0.0223, -0.8657, -0.0048, -0.8667, 0.0129, -0.8657, 0.0303, -0.8627, 0.0472, -0.8578, 0.0634, -0.8511, 0.079, -0.8427, 0.0936, -0.8326, 0.1073, -0.8208, 0.1198, -0.8075, 0.8087, -0.1512, 0.8265, -0.1269, 0.8384, -0.1034, 0.8452, -0.0812, 0.848, -0.0605, 0.8476, -0.0419, 0.8451, -0.0256, 0.8414, -0.012, 0.8375, -0.0017, 0.8333, 0.0069, 0.8264, 0.0181, 0.8164, 0.0308, 0.803, 0.0438, 0.7858, 0.0559, 0.7644, 0.0661, 0.7385, 0.073, 0.7077, 0.0756, 0.6912, 0.0756, 0.6912, 0.6658, 0.6879, 0.7007, 0.6783, 0.7333, 0.6631, 0.7628, 0.643, 0.7885, 0.6187, 0.8097, 0.5908, 0.8257, 0.56, 0.8358, 0.5269, 0.8394, -0.0138, 0.4121, 0.004, 0.4121, 0.0251, 0.4143, 0.0448, 0.4206, 0.0626, 0.4306, 0.0782, 0.4437, 0.0911, 0.4596, 0.1008, 0.4778, 0.107, 0.4978, 0.1092, 0.5194, 0.1092, 0.6658, 0.1115, 0.6903, 0.118, 0.7132, 0.1285, 0.7339, 0.1422, 0.7519, 0.1589, 0.7668, 0.1781, 0.7781, 0.1992, 0.7852, 0.2219, 0.7877, 0.5269, 0.7877, 0.5495, 0.7852, 0.5707, 0.7781, 0.5898, 0.7668, 0.6065, 0.7519, 0.6203, 0.7339, 0.6307, 0.7132, 0.6373, 0.6903, 0.6396, 0.6658, 0.6396, 0.024, 0.7077, 0.024, 0.7264, 0.0227, 0.7423, 0.0191, 0.7555, 0.0138, 0.7663, 0.0072, 0.7749, -0.0002, 0.7817, -0.0079, 0.7867, -0.0155, 0.7902, -0.0225, 0.793, -0.0298, 0.7953, -0.0387, 0.7965, -0.049, 0.7963, -0.0605, 0.794, -0.0733, 0.7893, -0.087, 0.7816, -0.1016, 0.7704, -0.1169, 0.0823, -0.7721, 0.063, -0.7903, 0.0414, -0.8032, 0.0183, -0.8109, -0.0054, -0.8134, -0.029, -0.8109, -0.0515, -0.8034, -0.0722, -0.7911, -0.781, -0.1158, -0.7919, -0.1011, -0.7994, -0.0868, -0.8039, -0.0733, -0.806, -0.0607, -0.8062, -0.0491, -0.8049, -0.0388, -0.8026, -0.0298, -0.7998, -0.0223, -0.7962, -0.0152, -0.7912, -0.0076, -0.7845, 0.0001, -0.7759, 0.0075, -0.7651, 0.014, -0.7519, 0.0192, -0.7362, 0.0227, -0.7175, 0.024, -0.6492, 0.024, -0.6492, 0.6658, -0.6469, 0.6903, -0.6403, 0.7132, -0.6299, 0.7339, -0.6162, 0.7519, -0.5995, 0.7668, -0.5804, 0.7781, -0.5593, 0.7852, -0.5367, 0.7877, -0.2312, 0.7877, -0.2087, 0.7852, -0.1876, 0.7781, -0.1685, 0.7668, -0.1519, 0.7519, -0.1382, 0.7339, -0.1278, 0.7132, -0.1212, 0.6903, -0.119, 0.6658, -0.119, 0.5194, -0.1167, 0.4978, -0.1105, 0.4778, -0.1007, 0.4596, -0.0878, 0.4437, -0.0723, 0.4306, -0.0545, 0.4206, -0.0348, 0.4143, -0.0137, 0.4121),
    ),
    "gear": (
        ("solid", 0.986, 0.184, 0.9868, 0.1902, 0.9874, 0.1966, 0.9876, 0.2034, 0.9875, 0.2105, 0.9871, 0.2179, 0.9864, 0.2256, 0.9853, 0.2337, 0.984, 0.242, 0.9824, 0.2505, 0.9805, 0.2591, 0.9784, 0.2676, 0.976, 0.2763, 0.9734, 0.2849, 0.9705, 0.2936, 0.9674, 0.3023, 0.964, 0.311, 0.9604, 0.3196, 0.9566, 0.3281, 0.9527, 0.3363, 0.9485, 0.3442, 0.9442, 0.352, 0.9396, 0.3596, 0.9349, 0.3669, 0.93, 0.374, 0.9249, 0.3807, 0.9197, 0.387, 0.9144, 0.3927, 0.909, 0.398, 0.9034, 0.4027, 0.8977, 0.407, 0.8919, 0.4107, 0.886, 0.414, 0.8801, 0.4168, 0.8744, 0.4192, 0.8688, 0.4213, 0.8635, 0.423, 0.8583, 0.4243, 0.8534, 0.4252, 0.8486, 0.4258, 0.844, 0.426, 0.8394, 0.4259, 0.8347, 0.4255, 0.8299, 0.4249, 0.825, 0.424, 0.8199, 0.4229, 0.8147, 0.4215, 0.8094, 0.4199, 0.804, 0.418, 0.7988, 0.4165, 0.7934, 0.4151, 0.7815, 0.4123, 0.7684, 0.4096, 0.754, 0.407, 0.7465, 0.4059, 0.7389, 0.405, 0.7314, 0.4044, 0.7237, 0.404, 0.7161, 0.4039, 0.7084, 0.404, 0.7007, 0.4044, 0.693, 0.405, 0.6852, 0.4059, 0.6775, 0.4069, 0.6698, 0.4082, 0.662, 0.4098, 0.6542, 0.4115, 0.6465, 0.4134, 0.6387, 0.4156, 0.631, 0.418, 0.6234, 0.4207, 0.6161, 0.4239, 0.609, 0.4275, 0.6022, 0.4315, 0.5958, 0.436, 0.5896, 0.4409, 0.5836, 0.4462, 0.578, 0.452, 0.5666, 0.4647, 0.5565, 0.4779, 0.5476, 0.4915, 0.54, 0.5055, 0.5336, 0.52, 0.5285, 0.5349, 0.5246, 0.5502, 0.522, 0.566, 0.5205, 0.5819, 0.5201, 0.5976, 0.5208, 0.6132, 0.5225, 0.6285, 0.5253, 0.6437, 0.5291, 0.6586, 0.534, 0.6734, 0.54, 0.688, 0.5443, 0.698, 0.5471, 0.708, 0.5485, 0.718, 0.5485, 0.728, 0.547, 0.738, 0.5441, 0.748, 0.5398, 0.758, 0.534, 0.768, 0.5308, 0.772, 0.5271, 0.7761, 0.523, 0.7801, 0.5185, 0.7843, 0.5135, 0.7884, 0.5081, 0.7926, 0.5023, 0.7968, 0.496, 0.801, 0.4827, 0.8093, 0.4758, 0.8133, 0.4615, 0.8211, 0.4542, 0.8248, 0.439, 0.832, 0.4312, 0.8354, 0.4233, 0.8386, 0.4153, 0.8417, 0.4072, 0.8445, 0.3991, 0.8472, 0.3908, 0.8496, 0.3825, 0.8519, 0.374, 0.854, 0.3656, 0.8559, 0.3575, 0.8575, 0.3496, 0.8589, 0.342, 0.86, 0.3346, 0.8609, 0.3275, 0.8615, 0.3206, 0.8619, 0.314, 0.862, 0.3095, 0.8618, 0.3051, 0.8611, 0.3008, 0.86, 0.2965, 0.8585, 0.2923, 0.8565, 0.2881, 0.8541, 0.284, 0.8513, 0.28, 0.848, 0.2762, 0.8445, 0.2726, 0.8409, 0.2694, 0.8372, 0.2665, 0.8335, 0.2639, 0.8297, 0.2616, 0.8259, 0.2597, 0.822, 0.258, 0.818, 0.256, 0.818, 0.25, 0.8028, 0.2431, 0.7881, 0.2351, 0.7739, 0.2262, 0.7603, 0.2164, 0.7471, 0.2056, 0.7346, 0.1938, 0.7225, 0.181, 0.711, 0.1675, 0.7005, 0.1534, 0.6913, 0.1389, 0.6836, 0.1237, 0.6773, 0.1081, 0.6723, 0.0919, 0.6688, 0.0752, 0.6667, 0.058, 0.666, 0.0412, 0.6667, 0.0248, 0.6688, 0.0088, 0.6723, -0.0068, 0.6773, -0.0219, 0.6836, -0.0367, 0.6913, -0.051, 0.7005, -0.065, 0.711, -0.0782, 0.7225, -0.0904, 0.7344, -0.1016, 0.7469, -0.1118, 0.7597, -0.1209, 0.7731, -0.1289, 0.7869, -0.136, 0.8012, -0.142, 0.816, -0.1447, 0.8218, -0.1476, 0.8272, -0.1509, 0.8322, -0.1545, 0.8368, -0.1584, 0.8409, -0.1626, 0.8447, -0.1672, 0.848, -0.172, 0.851, -0.1771, 0.8536, -0.1823, 0.8558, -0.1876, 0.8577, -0.193, 0.8592, -0.1986, 0.8605, -0.2043, 0.8613, -0.2101, 0.8618, -0.216, 0.862, -0.2231, 0.8618, -0.2304, 0.8614, -0.238, 0.8606, -0.2458, 0.8595, -0.2537, 0.8581, -0.2619, 0.8564, -0.2704, 0.8543, -0.279, 0.852, -0.2878, 0.8494, -0.3053, 0.8438, -0.314, 0.8407, -0.3315, 0.8342, -0.349, 0.827, -0.3576, 0.8232, -0.3661, 0.8192, -0.3743, 0.815, -0.3823, 0.8108, -0.39, 0.8063, -0.3976, 0.8017, -0.4049, 0.7969, -0.412, 0.792, -0.4188, 0.787, -0.4251, 0.782, -0.431, 0.777, -0.4365, 0.772, -0.4415, 0.767, -0.4461, 0.762, -0.4503, 0.757, -0.454, 0.752, -0.4564, 0.7484, -0.4584, 0.7447, -0.4602, 0.7408, -0.4618, 0.7368, -0.463, 0.7325, -0.4639, 0.7282, -0.4646, 0.7237, -0.465, 0.719, -0.465, 0.714, -0.4644, 0.7086, -0.4634, 0.7026, -0.4618, 0.6963, -0.4596, 0.6894, -0.4569, 0.6821, -0.4537, 0.6743, -0.4449, 0.6543, -0.4407, 0.6422, -0.4373, 0.6297, -0.4348, 0.6168, -0.433, 0.6034, -0.4322, 0.5897, -0.4322, 0.5755, -0.433, 0.561, -0.4349, 0.5464, -0.4381, 0.5321, -0.4425, 0.518, -0.4483, 0.5043, -0.4553, 0.4908, -0.4636, 0.4776, -0.4731, 0.4646, -0.484, 0.452, -0.4912, 0.4448, -0.4988, 0.4383, -0.5067, 0.4325, -0.515, 0.4273, -0.5237, 0.4227, -0.5328, 0.4188, -0.5422, 0.4156, -0.552, 0.413, -0.5619, 0.4109, -0.5718, 0.4092, -0.5814, 0.4078, -0.591, 0.4068, -0.6004, 0.406, -0.6098, 0.4057, -0.6189, 0.4057, -0.628, 0.406, -0.6385, 0.4067, -0.6491, 0.4078, -0.6598, 0.4092, -0.6705, 0.411, -0.6813, 0.4132, -0.6921, 0.4158, -0.703, 0.4187, -0.714, 0.422, -0.721, 0.4237, -0.728, 0.4248, -0.735, 0.4252, -0.742, 0.425, -0.749, 0.4242, -0.756, 0.4228, -0.763, 0.4207, -0.77, 0.418, -0.7755, 0.4157, -0.7808, 0.4127, -0.7861, 0.409, -0.7913, 0.4048, -0.7963, 0.3998, -0.8013, 0.3942, -0.8062, 0.3879, -0.811, 0.381, -0.8157, 0.3737, -0.8203, 0.3661, -0.8247, 0.3584, -0.829, 0.3505, -0.8332, 0.3424, -0.8373, 0.3341, -0.8412, 0.3257, -0.845, 0.317, -0.8486, 0.3082, -0.8521, 0.2994, -0.8553, 0.2905, -0.8583, 0.2815, -0.861, 0.2725, -0.8636, 0.2634, -0.8659, 0.2542, -0.868, 0.245, -0.8698, 0.236, -0.8713, 0.2273, -0.8723, 0.2191, -0.873, 0.2113, -0.8733, 0.2038, -0.8733, 0.1968, -0.8728, 0.1902, -0.872, 0.184, -0.8701, 0.1735, -0.8673, 0.164, -0.8636, 0.1555, -0.859, 0.148, -0.8536, 0.1415, -0.8473, 0.136, -0.8401, 0.1315, -0.8172, 0.1215, -0.8028, 0.1141, -0.7887, 0.1056, -0.775, 0.0963, -0.7617, 0.0859, -0.7488, 0.0746, -0.7362, 0.0623, -0.724, 0.049, -0.7128, 0.035, -0.703, 0.0207, -0.6948, 0.0059, -0.688, -0.0092, -0.6828, -0.0248, -0.679, -0.0408, -0.6768, -0.0572, -0.676, -0.074, -0.6768, -0.0912, -0.679, -0.1079, -0.6828, -0.124, -0.688, -0.1395, -0.6948, -0.1545, -0.703, -0.1689, -0.7128, -0.1827, -0.724, -0.196, -0.7362, -0.2086, -0.7488, -0.2202, -0.7617, -0.2311, -0.775, -0.241, -0.7887, -0.2501, -0.8028, -0.2582, -0.8172, -0.2656, -0.832, -0.272, -0.8364, -0.2738, -0.8406, -0.2761, -0.8447, -0.2789, -0.8485, -0.2822, -0.8522, -0.2861, -0.8556, -0.2906, -0.8589, -0.2955, -0.862, -0.301, -0.8648, -0.3068, -0.8673, -0.3126, -0.8693, -0.3184, -0.871, -0.3242, -0.8723, -0.3301, -0.8733, -0.3361, -0.8738, -0.342, -0.874, -0.348, -0.8739, -0.3546, -0.8735, -0.3614, -0.8729, -0.3683, -0.872, -0.3755, -0.8709, -0.3828, -0.8695, -0.3904, -0.8679, -0.3981, -0.866, -0.406, -0.8639, -0.414, -0.8617, -0.4219, -0.8568, -0.4375, -0.854, -0.4452, -0.8482, -0.4605, -0.8417, -0.4754, -0.8383, -0.4827, -0.8347, -0.4898, -0.831, -0.4967, -0.8272, -0.5035, -0.8233, -0.5102, -0.8192, -0.5167, -0.815, -0.523, -0.8107, -0.529, -0.8063, -0.5347, -0.8018, -0.5399, -0.7973, -0.5447, -0.7926, -0.5492, -0.7878, -0.5532, -0.783, -0.5568, -0.778, -0.56, -0.774, -0.5623, -0.7701, -0.5642, -0.7661, -0.5658, -0.7623, -0.567, -0.7584, -0.5678, -0.7546, -0.5682, -0.7508, -0.5683, -0.747, -0.568, -0.7432, -0.5674, -0.7353, -0.5659, -0.7313, -0.565, -0.7228, -0.5627, -0.714, -0.56, -0.6989, -0.5545, -0.6837, -0.5501, -0.6683, -0.5466, -0.6528, -0.5442, -0.637, -0.5429, -0.6212, -0.5426, -0.6052, -0.5433, -0.589, -0.545, -0.573, -0.5479, -0.5574, -0.5519, -0.5424, -0.5572, -0.5278, -0.5637, -0.5136, -0.5715, -0.4999, -0.5804, -0.4867, -0.5906, -0.474, -0.602, -0.4682, -0.6082, -0.4628, -0.6147, -0.4578, -0.6215, -0.4533, -0.6287, -0.4491, -0.6363, -0.4453, -0.6442, -0.442, -0.6524, -0.439, -0.661, -0.4364, -0.6697, -0.434, -0.6784, -0.4319, -0.6871, -0.43, -0.6957, -0.4284, -0.7044, -0.427, -0.7129, -0.4259, -0.7215, -0.425, -0.73, -0.4239, -0.7466, -0.4236, -0.7547, -0.4235, -0.7625, -0.4236, -0.7702, -0.4239, -0.7776, -0.4243, -0.7849, -0.425, -0.792, -0.4264, -0.805, -0.4284, -0.8207, -0.43, -0.832, -0.4319, -0.8382, -0.4346, -0.8486, -0.4362, -0.8561, -0.4376, -0.8639, -0.4379, -0.8677, -0.438, -0.8714, -0.4378, -0.875, -0.4372, -0.8784, -0.4364, -0.8817, -0.4354, -0.8849, -0.4307, -0.8949, -0.4268, -0.9016, -0.4223, -0.908, -0.4173, -0.9142, -0.4116, -0.9203, -0.4053, -0.9261, -0.3985, -0.9316, -0.391, -0.937, -0.3832, -0.9421, -0.3752, -0.9471, -0.367, -0.9518, -0.3588, -0.9562, -0.3503, -0.9605, -0.3417, -0.9646, -0.3329, -0.9684, -0.324, -0.972, -0.315, -0.9754, -0.3061, -0.9786, -0.2973, -0.9815, -0.2885, -0.9842, -0.2798, -0.9868, -0.2711, -0.9891, -0.2625, -0.9911, -0.254, -0.993, -0.2379, -0.9961, -0.2305, -0.9973, -0.217, -0.999, -0.2109, -0.9996, -0.2052, -0.9999, -0.2, -1.0, -0.1937, -0.9997, -0.1877, -0.9989, -0.182, -0.9976, -0.1767, -0.9957, -0.1718, -0.9934, -0.1672, -0.9904, -0.1629, -0.987, -0.159, -0.983, -0.1554, -0.9787, -0.1521, -0.9744, -0.149, -0.9701, -0.1462, -0.9657, -0.1438, -0.9614, -0.1416, -0.9569, -0.1396, -0.9525, -0.138, -0.948, -0.1321, -0.9347, -0.1252, -0.9218, -0.1176, -0.9093, -0.109, -0.8972, -0.0996, -0.8856, -0.0892, -0.8743, -0.0781, -0.8635, -0.066, -0.853, -0.0532, -0.8434, -0.0399, -0.8351, -0.026, -0.828, -0.0115, -0.8222, 0.0035, -0.8178, 0.0191, -0.8146, 0.0353, -0.8126, 0.052, -0.812, 0.0693, -0.8126, 0.086, -0.8144, 0.1023, -0.8175, 0.118, -0.8217, 0.1333, -0.8272, 0.148, -0.8339, 0.1623, -0.8419, 0.176, -0.851, 0.189, -0.8611, 0.201, -0.8718, 0.212, -0.8832, 0.222, -0.8952, 0.231, -0.908, 0.239, -0.9213, 0.246, -0.9353, 0.252, -0.95, 0.2541, -0.954, 0.2566, -0.9581, 0.2593, -0.9621, 0.2623, -0.9662, 0.2655, -0.9704, 0.2691, -0.9746, 0.2729, -0.9788, 0.277, -0.983, 0.2813, -0.987, 0.2856, -0.9904, 0.2899, -0.9934, 0.2943, -0.9957, 0.2986, -0.9976, 0.3031, -0.9989, 0.3075, -0.9997, 0.312, -1.0, 0.3191, -0.9999, 0.3263, -0.9995, 0.3337, -0.9989, 0.3413, -0.998, 0.349, -0.9969, 0.3568, -0.9955, 0.3648, -0.9939, 0.373, -0.992, 0.3812, -0.9899, 0.3894, -0.9876, 0.3976, -0.9852, 0.4057, -0.9825, 0.4139, -0.9797, 0.4219, -0.9766, 0.43, -0.9734, 0.438, -0.97, 0.4459, -0.9664, 0.4537, -0.9625, 0.4613, -0.9584, 0.4688, -0.954, 0.476, -0.9494, 0.4832, -0.9445, 0.4902, -0.9394, 0.497, -0.934, 0.5036, -0.9284, 0.5098, -0.9227, 0.5157, -0.9169, 0.5212, -0.911, 0.5265, -0.9049, 0.5313, -0.8987, 0.5358, -0.8924, 0.54, -0.886, 0.5423, -0.882, 0.5441, -0.8778, 0.5455, -0.8736, 0.5465, -0.8692, 0.547, -0.8648, 0.5471, -0.8603, 0.5468, -0.8557, 0.546, -0.851, 0.544, -0.8422, 0.543, -0.8383, 0.541, -0.8315, 0.539, -0.8262, 0.538, -0.824, 0.5321, -0.8094, 0.5272, -0.7946, 0.5236, -0.7797, 0.521, -0.7645, 0.5196, -0.7492, 0.5192, -0.7336, 0.5201, -0.7179, 0.522, -0.702, 0.5251, -0.6862, 0.5294, -0.671, 0.5348, -0.6562, 0.5415, -0.642, 0.5493, -0.6282, 0.5584, -0.615, 0.5686, -0.6022, 0.58, -0.59, 0.5923, -0.5787, 0.6054, -0.5687, 0.6191, -0.56, 0.6335, -0.5527, 0.6486, -0.5468, 0.6644, -0.5422, 0.6808, -0.5389, 0.698, -0.537, 0.7153, -0.5363, 0.7324, -0.5366, 0.7491, -0.5379, 0.7655, -0.5402, 0.7816, -0.5436, 0.7974, -0.5481, 0.8128, -0.5535, 0.828, -0.56, 0.8321, -0.5623, 0.8364, -0.5642, 0.841, -0.5658, 0.8458, -0.567, 0.8507, -0.5678, 0.8559, -0.5682, 0.8614, -0.5683, 0.867, -0.568, 0.8726, -0.5673, 0.8781, -0.5661, 0.8833, -0.5645, 0.8882, -0.5625, 0.893, -0.56, 0.8976, -0.5571, 0.9019, -0.5538, 0.906, -0.55, 0.9134, -0.5425, 0.9206, -0.5342, 0.9275, -0.5249, 0.9342, -0.5147, 0.9408, -0.5037, 0.9471, -0.4917, 0.9531, -0.4788, 0.959, -0.465, 0.9645, -0.4507, 0.9696, -0.4364, 0.9741, -0.4221, 0.9782, -0.4077, 0.9819, -0.3934, 0.9851, -0.3789, 0.9878, -0.3645, 0.99, -0.35, 0.9907, -0.3417, 0.9908, -0.3339, 0.9903, -0.3266, 0.9892, -0.3197, 0.9876, -0.3134, 0.9853, -0.3074, 0.9825, -0.302, 0.979, -0.297, 0.9752, -0.2925, 0.9714, -0.2883, 0.9676, -0.2846, 0.9637, -0.2812, 0.9599, -0.2783, 0.9559, -0.2758, 0.952, -0.2737, 0.948, -0.272, 0.9328, -0.266, 0.9181, -0.2589, 0.904, -0.2509, 0.8905, -0.2417, 0.8775, -0.2316, 0.8651, -0.2204, 0.8533, -0.2082, 0.842, -0.195, 0.8317, -0.181, 0.8227, -0.1666, 0.8152, -0.1516, 0.809, -0.1362, 0.8042, -0.1204, 0.8007, -0.1041, 0.7987, -0.0873, 0.798, -0.07, 0.7986, -0.0533, 0.8003, -0.0371, 0.8032, -0.0214, 0.8072, -0.0062, 0.8125, 0.0084, 0.8188, 0.0224, 0.8263, 0.036, 0.835, 0.049, 0.8446, 0.0613, 0.8549, 0.0727, 0.866, 0.0832, 0.8777, 0.0928, 0.8902, 0.1014, 0.9034, 0.1092, 0.9174, 0.116, 0.932, 0.122, 0.9387, 0.126, 0.945, 0.13, 0.9507, 0.134, 0.956, 0.138, 0.9613, 0.1427, 0.9661, 0.1476, 0.9705, 0.1529, 0.9745, 0.1585, 0.978, 0.1644, 0.9811, 0.1706, 0.9838, 0.1772, 0.986, 0.184, 0.056, 0.364, 0.0783, 0.3635, 0.1004, 0.3619, 0.1221, 0.3592, 0.1435, 0.3555, 0.1646, 0.3507, 0.1854, 0.3449, 0.2058, 0.338, 0.226, 0.33, 0.2457, 0.3211, 0.2647, 0.3114, 0.283, 0.3008, 0.3007, 0.2895, 0.3178, 0.2773, 0.3342, 0.2644, 0.3499, 0.2506, 0.365, 0.236, 0.3794, 0.2207, 0.3929, 0.2048, 0.4057, 0.1883, 0.4178, 0.1713, 0.429, 0.1536, 0.4394, 0.1353, 0.4491, 0.1165, 0.458, 0.097, 0.466, 0.0771, 0.4729, 0.0568, 0.4787, 0.0362, 0.4835, 0.0152, 0.4872, -0.006, 0.4899, -0.0277, 0.4915, -0.0497, 0.492, -0.072, 0.4915, -0.0943, 0.4899, -0.1163, 0.4872, -0.138, 0.4835, -0.1593, 0.4787, -0.1802, 0.4729, -0.2008, 0.466, -0.2211, 0.458, -0.241, 0.4491, -0.2604, 0.4394, -0.2792, 0.429, -0.2974, 0.4177, -0.315, 0.4057, -0.3319, 0.3929, -0.3483, 0.3794, -0.3639, 0.365, -0.379, 0.3499, -0.3934, 0.3342, -0.4069, 0.3178, -0.4197, 0.3008, -0.4318, 0.283, -0.443, 0.2647, -0.4534, 0.2457, -0.4631, 0.226, -0.472, 0.2058, -0.48, 0.1854, -0.4869, 0.1646, -0.4927, 0.1435, -0.4975, 0.1221, -0.5012, 0.1004, -0.5039, 0.0783, -0.5055, 0.056, -0.506, 0.0337, -0.5055, 0.0117, -0.5039, -0.01, -0.5012, -0.0312, -0.4975, -0.0522, -0.4927, -0.0728, -0.4869, -0.0931, -0.48, -0.113, -0.472, -0.1324, -0.4631, -0.1513, -0.4534, -0.1694, -0.443, -0.187, -0.4317, -0.2039, -0.4197, -0.2203, -0.4069, -0.2359, -0.3934, -0.251, -0.379, -0.2654, -0.3639, -0.2789, -0.3483, -0.2917, -0.3319, -0.3037, -0.315, -0.315, -0.2974, -0.3254, -0.2793, -0.3351, -0.2604, -0.344, -0.241, -0.352, -0.2211, -0.3589, -0.2008, -0.3647, -0.1802, -0.3695, -0.1593, -0.3732, -0.138, -0.3759, -0.1163, -0.3775, -0.0943, -0.378, -0.072, -0.3775, -0.0497, -0.3759, -0.0277, -0.3732, -0.006, -0.3695, 0.0152, -0.3647, 0.0362, -0.3589, 0.0568, -0.352, 0.0771, -0.344, 0.097, -0.3351, 0.1165, -0.3254, 0.1353, -0.315, 0.1536, -0.3038, 0.1713, -0.2917, 0.1883, -0.2789, 0.2048, -0.2654, 0.2207, -0.251, 0.236, -0.2359, 0.2506, -0.2202, 0.2644, -0.2039, 0.2773, -0.187, 0.2895, -0.1694, 0.3008, -0.1512, 0.3114, -0.1324, 0.3211, -0.113, 0.33, -0.0931, 0.338, -0.0728, 0.3449, -0.0522, 0.3507, -0.0313, 0.3555, -0.01, 0.3592, 0.0117, 0.3619, 0.0337, 0.3635, 0.056, 0.364),
    ),
    "log": (
        ("solid", -0.8125, 0.275, -0.8265, 0.2733, -0.84, 0.2686, -0.8527, 0.2612, -0.8641, 0.2516, -0.8737, 0.2402, -0.8811, 0.2275, -0.8858, 0.214, -0.8875, 0.2, -0.8875, -0.2, -0.8858, -0.214, -0.8811, -0.2275, -0.8737, -0.2402, -0.8641, -0.2516, -0.8527, -0.2612, -0.84, -0.2686, -0.8265, -0.2733, -0.8125, -0.275, -0.7985, -0.2733, -0.785, -0.2686, -0.7723, -0.2612, -0.7609, -0.2516, -0.7513, -0.2402, -0.7439, -0.2275, -0.7392, -0.214, -0.7375, -0.2, -0.7375, 0.2, -0.7387, 0.2176, -0.7422, 0.2328, -0.748, 0.2457, -0.7562, 0.2563, -0.7668, 0.2645, -0.7797, 0.2703, -0.7949, 0.2738, -0.8125, 0.275),
        ("solid", 0.9875, 0.0, 0.9846, -0.0363, 0.9764, -0.0699, 0.9631, -0.1006, 0.9453, -0.1281, 0.9234, -0.1521, 0.8979, -0.1723, 0.8691, -0.1883, 0.8375, -0.2, 0.8375, -0.6875, 0.8318, -0.7465, 0.8154, -0.801, 0.7894, -0.8499, 0.7547, -0.8922, 0.7124, -0.9269, 0.6635, -0.9529, 0.609, -0.9693, 0.55, -0.975, -0.6, -0.975, -0.659, -0.9693, -0.7135, -0.9529, -0.7624, -0.9269, -0.8047, -0.8922, -0.8394, -0.8499, -0.8654, -0.801, -0.8818, -0.7465, -0.8875, -0.6875, -0.8875, -0.65, -0.8858, -0.636, -0.8811, -0.6225, -0.8737, -0.6098, -0.8641, -0.5984, -0.8527, -0.5888, -0.84, -0.5814, -0.8265, -0.5767, -0.8125, -0.575, -0.7985, -0.5767, -0.785, -0.5814, -0.7723, -0.5888, -0.7609, -0.5984, -0.7513, -0.6098, -0.7439, -0.6225, -0.7392, -0.636, -0.7375, -0.65, -0.7375, -0.6875, -0.7347, -0.7149, -0.7266, -0.7406, -0.7138, -0.764, -0.6969, -0.7844, -0.6765, -0.8013, -0.6531, -0.8141, -0.6274, -0.8222, -0.6, -0.825, 0.5625, -0.825, 0.5899, -0.8222, 0.6156, -0.8141, 0.639, -0.8013, 0.6594, -0.7844, 0.6763, -0.764, 0.6891, -0.7406, 0.6972, -0.7149, 0.7, -0.6875, 0.7, -0.2, 0.672, -0.1878, 0.6449, -0.1705, 0.6196, -0.1488, 0.5969, -0.1234, 0.5777, -0.0951, 0.5629, -0.0646, 0.5534, -0.0327, 0.55, 0.0, 0.5529, 0.0363, 0.5611, 0.0699, 0.5744, 0.1006, 0.5922, 0.1281, 0.6141, 0.1521, 0.6396, 0.1723, 0.6684, 0.1883, 0.7, 0.2, 0.7, 0.6875, 0.6972, 0.7149, 0.6891, 0.7406, 0.6763, 0.764, 0.6594, 0.7844, 0.639, 0.8013, 0.6156, 0.8141, 0.5899, 0.8222, 0.5625, 0.825, -0.6, 0.825, -0.6274, 0.8222, -0.6531, 0.8141, -0.6765, 0.8013, -0.6969, 0.7844, -0.7138, 0.764, -0.7266, 0.7406, -0.7347, 0.7149, -0.7375, 0.6875, -0.7375, 0.65, -0.7392, 0.636, -0.7439, 0.6225, -0.7513, 0.6098, -0.7609, 0.5984, -0.7723, 0.5888, -0.785, 0.5814, -0.7985, 0.5767, -0.8125, 0.575, -0.8265, 0.5767, -0.84, 0.5814, -0.8527, 0.5888, -0.8641, 0.5984, -0.8737, 0.6098, -0.8811, 0.6225, -0.8858, 0.636, -0.8875, 0.65, -0.8875, 0.6875, -0.8818, 0.7465, -0.8654, 0.801, -0.8394, 0.8499, -0.8047, 0.8922, -0.7624, 0.9269, -0.7135, 0.9529, -0.659, 0.9693, -0.6, 0.975, 0.5625, 0.975, 0.6215, 0.9693, 0.676, 0.9529, 0.7249, 0.9269, 0.7672, 0.8922, 0.8019, 0.8499, 0.8279, 0.801, 0.8443, 0.7465, 0.85, 0.6875, 0.85, 0.2125, 0.881, 0.1967, 0.9084, 0.1775, 0.932, 0.1552, 0.9516, 0.1297, 0.9671, 0.1013, 0.9783, 0.0701, 0.9852, 0.0363, 0.9875, -0.0, 0.775, 0.1, 0.7563, 0.0983, 0.7383, 0.0932, 0.7214, 0.0848, 0.7063, 0.0734, 0.6935, 0.0591, 0.6836, 0.042, 0.6772, 0.0222, 0.675, 0.0, 0.6767, -0.0187, 0.6818, -0.0367, 0.6902, -0.0536, 0.7016, -0.0687, 0.7159, -0.0815, 0.733, -0.0914, 0.7528, -0.0978, 0.775, -0.1, 0.7972, -0.0983, 0.817, -0.0932, 0.8341, -0.0848, 0.8484, -0.0734, 0.8598, -0.0591, 0.8682, -0.042, 0.8733, -0.0222, 0.875, 0.0, 0.8692, 0.0187, 0.8611, 0.0367, 0.851, 0.0536, 0.8391, 0.0688, 0.8253, 0.0815, 0.81, 0.0914, 0.7931, 0.0978, 0.775, 0.1),
        ("solid", 0.2875, -0.35, -0.325, -0.35, -0.339, -0.3512, -0.3525, -0.3547, -0.3652, -0.3605, -0.3766, -0.3688, -0.3862, -0.3793, -0.3936, -0.3922, -0.3983, -0.4074, -0.4, -0.425, -0.3983, -0.439, -0.3936, -0.4525, -0.3862, -0.4652, -0.3766, -0.4766, -0.3652, -0.4862, -0.3525, -0.4936, -0.339, -0.4983, -0.325, -0.5, 0.2875, -0.5, 0.3015, -0.4983, 0.315, -0.4936, 0.3277, -0.4862, 0.3391, -0.4766, 0.3487, -0.4652, 0.3561, -0.4525, 0.3608, -0.439, 0.3625, -0.425, 0.3608, -0.4074, 0.3561, -0.3922, 0.3487, -0.3793, 0.3391, -0.3687, 0.3277, -0.3605, 0.315, -0.3547, 0.3015, -0.3512, 0.2875, -0.35),
        ("solid", 0.2875, 0.075, -0.325, 0.075, -0.339, 0.0738, -0.3525, 0.0703, -0.3652, 0.0645, -0.3766, 0.0562, -0.3862, 0.0457, -0.3936, 0.0328, -0.3983, 0.0176, -0.4, 0.0, -0.3983, -0.014, -0.3936, -0.0275, -0.3862, -0.0402, -0.3766, -0.0516, -0.3652, -0.0612, -0.3525, -0.0686, -0.339, -0.0733, -0.325, -0.075, 0.2875, -0.075, 0.3015, -0.0733, 0.315, -0.0686, 0.3277, -0.0612, 0.3391, -0.0516, 0.3487, -0.0402, 0.3561, -0.0275, 0.3608, -0.014, 0.3625, 0.0, 0.3608, 0.0176, 0.3561, 0.0328, 0.3487, 0.0457, 0.3391, 0.0562, 0.3277, 0.0645, 0.315, 0.0703, 0.3015, 0.0738, 0.2875, 0.075),
        ("solid", 0.2875, 0.5, -0.325, 0.5, -0.339, 0.4983, -0.3525, 0.4936, -0.3652, 0.4862, -0.3766, 0.4766, -0.3862, 0.4652, -0.3936, 0.4525, -0.3983, 0.439, -0.4, 0.425, -0.3983, 0.411, -0.3936, 0.3975, -0.3862, 0.3848, -0.3766, 0.3734, -0.3652, 0.3638, -0.3525, 0.3564, -0.339, 0.3517, -0.325, 0.35, 0.2875, 0.35, 0.3015, 0.3517, 0.315, 0.3564, 0.3277, 0.3638, 0.3391, 0.3734, 0.3487, 0.3848, 0.3561, 0.3975, 0.3608, 0.411, 0.3625, 0.425, 0.3608, 0.4426, 0.3561, 0.4578, 0.3487, 0.4707, 0.3391, 0.4813, 0.3277, 0.4895, 0.315, 0.4953, 0.3015, 0.4988, 0.2875, 0.5),
        ("solid", -0.7, 0.5, -0.9125, 0.5, -0.9265, 0.4983, -0.94, 0.4936, -0.9527, 0.4862, -0.9641, 0.4766, -0.9737, 0.4652, -0.9811, 0.4525, -0.9858, 0.439, -0.9875, 0.425, -0.9858, 0.411, -0.9811, 0.3975, -0.9737, 0.3848, -0.9641, 0.3734, -0.9527, 0.3638, -0.94, 0.3564, -0.9265, 0.3517, -0.9125, 0.35, -0.7, 0.35, -0.686, 0.3517, -0.6725, 0.3564, -0.6598, 0.3638, -0.6484, 0.3734, -0.6388, 0.3848, -0.6314, 0.3975, -0.6267, 0.411, -0.625, 0.425, -0.6267, 0.4426, -0.6314, 0.4578, -0.6388, 0.4707, -0.6484, 0.4813, -0.6598, 0.4895, -0.6725, 0.4953, -0.686, 0.4988, -0.7, 0.5),
        ("solid", -0.7, -0.35, -0.9125, -0.35, -0.9301, -0.3512, -0.9453, -0.3547, -0.9582, -0.3605, -0.9688, -0.3688, -0.977, -0.3793, -0.9828, -0.3922, -0.9863, -0.4074, -0.9875, -0.425, -0.9863, -0.439, -0.9828, -0.4525, -0.977, -0.4652, -0.9688, -0.4766, -0.9582, -0.4862, -0.9453, -0.4936, -0.9301, -0.4983, -0.9125, -0.5, -0.7, -0.5, -0.686, -0.4983, -0.6725, -0.4936, -0.6598, -0.4862, -0.6484, -0.4766, -0.6388, -0.4652, -0.6314, -0.4525, -0.6267, -0.439, -0.625, -0.425, -0.6267, -0.4074, -0.6314, -0.3922, -0.6388, -0.3793, -0.6484, -0.3687, -0.6598, -0.3605, -0.6725, -0.3547, -0.686, -0.3512, -0.7, -0.35),
    ),
}


def _icon_points(pts, cx, cy, size, angle, kind="line"):
    """把归一化坐标按 size/角度映射到画布坐标。

    圆要特殊处理：直接旋转包围盒的两个角点会把它压成椭圆甚至一条线
    （45° 时中心孔会变成一根竖线）。圆在旋转下不变，只转圆心、半径照旧。
    """
    rad = math.radians(angle or 0.0)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    half = size / 2.0

    def _map(x, y):
        return (cx + (x * cos_a - y * sin_a) * half,
                cy + (x * sin_a + y * cos_a) * half)

    if kind == "oval" and len(pts) == 4:
        x1, y1, x2, y2 = pts
        mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        rx, ry = abs(x2 - x1) / 2.0, abs(y2 - y1) / 2.0
        px, py = _map(mx, my)
        return [px - rx * half, py - ry * half, px + rx * half, py + ry * half]

    out = []
    for i in range(0, len(pts), 2):
        px, py = _map(pts[i], pts[i + 1])
        out.extend((px, py))
    return out


def draw_vector_icon(canvas, name, cx, cy, size, color, angle=0.0, width=1.7):
    """在 canvas 上画一个矢量图标，返回 (图元 id 列表, 图元描述)。"""
    prims = _ICON_PRIMS.get(name)
    if not prims:
        return [], None
    ids = []
    for prim in prims:
        pts = _icon_points(prim[1:], cx, cy, size, angle, prim[0])
        try:
            if prim[0] == "oval":
                ids.append(canvas.create_oval(*pts, outline=color, width=width))
            elif prim[0] == "poly":
                ids.append(canvas.create_polygon(*pts, fill="", outline=color,
                                                  width=width, joinstyle="round"))
            elif prim[0] == "solid":
                # 填充型图标：实心形状，孔由 even-odd 填充自动挖出来；
                # 再描 1px 同色边 —— 线稿型图标（如主界面房子）在 17px 下
                # 只有 0.6px 粗，不描边几乎看不见
                ids.append(canvas.create_polygon(*pts, fill=color,
                                                  outline=color, width=1,
                                                  joinstyle="round"))
            else:
                ids.append(canvas.create_line(*pts, fill=color, width=width,
                                              capstyle="round"))
        except Exception:
            pass
    return ids, prims


def redraw_vector_icon(canvas, ids, prims, cx, cy, size, angle=0.0):
    """只改坐标，不重建图元：逐帧动画时不会闪。"""
    for item, prim in zip(ids, prims):
        try:
            canvas.coords(item, *_icon_points(prim[1:], cx, cy, size, angle,
                                              prim[0]))
        except Exception:
            pass


def paint_vector_icon(canvas, ids, prims, color):
    """矢量图标的染色：线用 fill，圆用 outline。"""
    for index, item in enumerate(ids):
        try:
            kind = prims[index][0] if prims else "line"
            if kind in ("oval", "poly"):
                canvas.itemconfigure(item, outline=color)
            elif kind == "solid":
                canvas.itemconfigure(item, fill=color, outline=color)
            else:
                canvas.itemconfigure(item, fill=color)
        except Exception:
            pass


# ==================== 控件工厂 ====================
def make_button(parent, text, command=None, width=None, state="normal", accent=False):
    """统一按钮工厂：返回的按钮自带 hover / 按下的曲线过渡。"""
    kwargs = dict(
        text=text, command=command,
        text_color=C_TEXT_INVERSE if accent else C_TEXT_MAIN,
        border_color=C_ACCENT if accent else C_BORDER_SOFT,
        border_width=BORDER_W, corner_radius=R_CONTROL,
        font=(FONT_FAMILY, FS_BODY), height=H_CONTROL, state=state)
    if width is not None:
        kwargs['width'] = width
    if accent:
        return AnimatedButton(parent, C_ACCENT, C_ACCENT_HOVER,
                               press_color=C_ACCENT_HOVER, **kwargs)
    return AnimatedButton(parent, C_PANEL_ALT_BG, C_ACCENT_SOFT, **kwargs)


def make_entry(parent, textvariable=None, placeholder="", width=None):
    kwargs = dict(
        fg_color=C_INPUT_BG, border_color=C_BORDER_SOFT, border_width=BORDER_W,
        corner_radius=R_CONTROL, text_color=C_TEXT_MAIN,
        placeholder_text=placeholder, placeholder_text_color=C_TEXT_MUTED,
        font=(FONT_FAMILY, FS_BODY), height=H_CONTROL)
    if textvariable is not None:
        kwargs['textvariable'] = textvariable
    if width is not None:
        kwargs['width'] = width
    return ctk.CTkEntry(parent, **kwargs)


def make_display_box(parent, text="", width=None, height=H_CONTROL):
    frame = ctk.CTkFrame(parent, fg_color=C_INPUT_BG, border_color=C_BORDER_SOFT,
                          border_width=BORDER_W, corner_radius=R_CONTROL,
                          height=height)
    frame.pack_propagate(False)
    label = ctk.CTkLabel(frame, text=text, text_color=C_TEXT_SECONDARY,
                          font=(FONT_FAMILY, FS_SMALL), anchor="w",
                          fg_color="transparent")
    label.pack(fill=BOTH, expand=True, padx=PAD_INNER)
    return frame, label


def make_label(parent, text="", fg=None, bg=None, font_size=FS_BODY, bold=False,
               justify=None):
    if fg is None:
        fg = C_TEXT_MAIN
    weight = "bold" if bold else "normal"
    kwargs = dict(text=text, text_color=fg,
                  font=(FONT_FAMILY, font_size, weight),
                  anchor="w")
    kwargs['fg_color'] = bg if bg is not None else "transparent"
    # justify 只在显式传入时下发，避免影响其余单行标签的外观。
    # （原来多行提示写的是 justify=LEFT，但本工厂没有该参数 -> 一进设置页就 TypeError）
    if justify is not None:
        kwargs['justify'] = justify
    return ctk.CTkLabel(parent, **kwargs)


# ==================== 窗口内覆盖层对话框 ====================
# 需求：所有提示/确认都出现在主程序窗口内部，不开新的系统窗口。
# tkinter.messagebox 是 Tk 原生模态对话框（必然新开窗口），所以这里自绘：
#   · 遮罩 + 居中卡片用 place() 铺在主窗口内容区（含侧边栏）之上；
#   · 全部用 relx/rely/relwidth/relheight 相对定位，窗口 resize 时由 Tk 自动跟随，
#     因此不需要任何 <Configure> 绑定，也就不会在拖拽窗口时触发重排；
#   · 模态阻塞用 root.wait_variable() 的嵌套事件循环，不创建任何窗口，无需 grab_set；
#   · 模态性：遮罩吃掉鼠标事件、focus_set 把键盘焦点收进卡片、Tab 只在卡片内循环、
#     ESC 关闭（等价于「取消/否」）、点遮罩本身不关闭；
#   · Tk 控件不支持逐控件 alpha，遮罩用纯色 C_PANEL_ALT_BG 近似半透明。

_OVERLAY_HOST = None      # 由 PulsesSwapApp.setup_ui() 注册的宿主（见 set_overlay_host）
_OVERLAY_WIDTH = {"info": 460, "warning": 480, "error": 560, "question": 480}
_OVERLAY_STACK = []       # 当前打开的覆盖层（后开的在最上层），用于多层弹窗时的 ESC 判定
_DEFAULT_BUTTONS = {
    "info":     [("确定", True, True)],
    "warning":  [("确定", True, True)],
    "error":    [("确定", True, True)],
    "question": [("是", True, True), ("否", False, False)],
}


def set_overlay_host(host):
    """注册覆盖层宿主（PulsesSwapApp 实例）；必须晚于主窗口骨架创建。"""
    global _OVERLAY_HOST
    _OVERLAY_HOST = host


def get_overlay_host():
    return _OVERLAY_HOST


def _run_modal(build_and_wait):
    """
    把「建卡片 + 嵌套等待」整体切到主线程执行。
    导入/导出等 worker 线程里也会弹确认框，而 Tk 调用不是线程安全的，
    所以这里统一用 root.after 回主线程，再用 Event 把结果带回业务线程。
    """
    if threading.current_thread() is threading.main_thread():
        return build_and_wait()
    host = _OVERLAY_HOST
    if host is None:
        # 宿主未注册（主窗口骨架还没建好）时没有可用的 after 通道，只能就地构建
        return build_and_wait()
    box, done = {}, threading.Event()

    def _call():
        try:
            box['value'] = build_and_wait()
        except Exception as exc:            # pragma: no cover - 纯防御
            box['error'] = exc
        finally:
            done.set()

    try:
        host.root.after(0, _call)
    except Exception:
        return None
    done.wait()
    if 'error' in box:
        raise box['error']
    return box.get('value')


class _OverlayCardBase:
    """
    覆盖层卡片的内容构建 + 关闭/等待语义。
    容器（窗口内遮罩 / 启动兜底的 Toplevel）由子类提供，内容代码完全复用。
    """

    def __init__(self, width=480, escape_value=None):
        self.width = width
        self.escape_value = escape_value
        self.result = escape_value
        self.focusables = []
        self._closed = False
        self.root = None
        self.body = None

    # ---------- 生命周期（容器部分由子类实现） ----------
    def _teardown(self):
        raise NotImplementedError

    def _release(self):
        """子类用于唤醒阻塞中的 wait()。"""
        return None

    def wait(self):
        raise NotImplementedError

    def close(self, value=None):
        if self._closed:
            return
        self._closed = True
        self.result = value
        try:
            self._teardown()
        except Exception:
            pass
        try:
            self._release()
        except Exception:
            pass

    # ---------- 键盘模态 ----------
    def _is_top(self):
        """是否是当前最上层的卡片（多层覆盖时只有最上层响应 ESC）。"""
        return True

    def _on_escape(self, event=None):
        if not self._is_top():
            return "break"
        self.close(self.escape_value)
        return "break"

    def _on_return(self, value):
        self.close(value)
        return "break"

    def _on_tab(self, event=None):
        return self._cycle_focus(1)

    def _on_tab_back(self, event=None):
        return self._cycle_focus(-1)

    def _cycle_focus(self, step):
        """Tab 只在卡片内循环，避免焦点跑到遮罩下面的主界面控件上。"""
        ring = [w for w in self.focusables if w is not None]
        if not ring:
            return "break"
        try:
            index = ring.index(self.root.focus_get())
        except Exception:
            index = -1 if step > 0 else 0
        try:
            ring[(index + step) % len(ring)].focus_set()
        except Exception:
            pass
        return "break"

    def register_focusable(self, widget):
        self.focusables.append(widget)
        return widget

    def _key_widgets(self):
        return []

    # ---------- 内容构建 ----------
    def add_title(self, text, fg=None):
        label = make_label(self.body, text=text,
                            fg=C_ACCENT if fg is None else fg,
                            font_size=FS_SUBHEAD, bold=True)
        label.pack(anchor=W, pady=(0, PAD_TIGHT))
        return label

    def add_text(self, text, fg=None, font_size=FS_BODY, wrap_extra=6):
        label = make_label(self.body, text=text,
                            fg=C_TEXT_MAIN if fg is None else fg,
                            font_size=font_size)
        label.configure(
            wraplength=max(200, self.width - 2 * PAD_DIALOG - wrap_extra),
            justify=LEFT, anchor=W)
        label.pack(anchor=W, fill=X, pady=(0, PAD_INNER))
        return label

    def add_buttons(self, buttons, default=None):
        """buttons: [(文字, 返回值, 是否强调色)]；default 为回车触发的返回值。"""
        default_value = buttons[0][1] if default is None else default
        bar = ctk.CTkFrame(self.body, fg_color="transparent")
        bar.pack(fill=X, side=BOTTOM, pady=(PAD_DIALOG, 0))
        for text, value, accent in reversed(buttons):
            btn = make_button(bar, text,
                               command=lambda v=value: self.close(v),
                               accent=accent)
            btn.pack(side=RIGHT, padx=(PAD_TIGHT, 0))
            self.register_focusable(btn)
            try:
                btn.bind("<Return>", lambda e, v=value: self._on_return(v))
            except Exception:
                pass
        for widget in self._key_widgets():
            try:
                widget.bind("<Return>",
                             lambda e, v=default_value: self._on_return(v))
            except Exception:
                pass
        return bar


class OverlayCard(_OverlayCardBase):
    """窗口内覆盖层：遮罩 + 居中卡片，全部相对定位，窗口 resize 时自动跟随。"""

    def __init__(self, host, width=480, escape_value=None):
        super().__init__(width=width, escape_value=escape_value)
        self.host = host
        self.root = host.root
        self._esc_funcid = None
        self._var = IntVar(master=self.root)

        self.mask = ctk.CTkFrame(host.overlay_host, fg_color=C_PANEL_ALT_BG,
                                  corner_radius=0)
        self.mask.place(relx=0.0, rely=0.0, relwidth=1.0, relheight=1.0)
        self.mask.lift()
        # height=1 让卡片高度完全由内容决定（CTkFrame 默认 200x200 会撑出空白）
        self.card = ctk.CTkFrame(self.mask, fg_color=C_PANEL_BG,
                                  corner_radius=R_CARD, border_width=BORDER_W,
                                  border_color=C_BORDER_SOFT,
                                  width=width, height=1)
        self.card.place(relx=0.5, rely=0.5, anchor="center")
        self.body = ctk.CTkFrame(self.card, fg_color="transparent")
        self.body.pack(fill=BOTH, expand=True, padx=PAD_DIALOG, pady=PAD_DIALOG)

        try:
            # ESC 走 root 级绑定（子控件拿到焦点后仍然有效），关闭时按 funcid 解绑
            self._esc_funcid = self.root.bind("<Escape>", self._on_escape, add="+")
            for widget in self._key_widgets():
                widget.bind("<Escape>", self._on_escape)
                widget.bind("<Tab>", self._on_tab)
                widget.bind("<Shift-Tab>", self._on_tab_back)
            self.mask.focus_set()
        except Exception:
            pass
        self._play_entrance()
        _OVERLAY_STACK.append(self)

    def _play_entrance(self):
        """卡片入场：从下方 4.5% 处曲线滑到居中，同时描边从强调色淡回发丝色。"""
        def frame(e, raw):
            try:
                self.card.place_configure(rely=lerp(0.545, 0.5, e))
                self.card.configure(
                    border_color=lerp_color(C_ACCENT_SOFT, C_BORDER_SOFT, e))
            except Exception:
                pass

        frame(0.0, 0.0)
        tween(self.card, "entrance", 190, frame, easing=ease_out_cubic)

    def _key_widgets(self):
        return [self.mask, self.card, self.body]

    def _is_top(self):
        return bool(_OVERLAY_STACK) and _OVERLAY_STACK[-1] is self

    def _teardown(self):
        try:
            if _OVERLAY_STACK and _OVERLAY_STACK[-1] is self:
                _OVERLAY_STACK.pop()
        except Exception:
            pass
        try:
            if self._esc_funcid is not None:
                self.root.unbind("<Escape>", self._esc_funcid)
        except Exception:
            pass
        try:
            self.mask.destroy()
        except Exception:
            pass

    def _release(self):
        self._var.set(1)          # 唤醒 wait_variable 的嵌套事件循环

    def wait(self):
        self.root.wait_variable(self._var)
        if not self._closed:
            # 防御：wait 已返回但卡片没走 close()（例如变量被外部置位），
            # 这里补一次收尾，保证遮罩/栈不会残留
            self.close(self.result)
        return self.result


class ToplevelCard(_OverlayCardBase):
    """
    兜底容器：宿主尚未注册（主窗口骨架还没建好）时才会用到，退化成一个 Toplevel。
    内容代码与窗口内覆盖层完全共用，保证极端情况下提示不会静默丢失。
    """

    def __init__(self, parent, width=520, height=560, escape_value=None,
                 title=PROJECT_NAME):
        super().__init__(width=width, escape_value=escape_value)
        self.root = parent
        self.window = ctk.CTkToplevel(parent)
        self.window.title(title)
        self.window.geometry(f"{width}x{height}")
        self.window.configure(fg_color=C_WINDOW_BG)
        # 子窗口图标与主窗口保持一致（apply_window_icon 定义在文件末尾，
        # 运行时才解析，这里调用没有先后顺序问题）
        try:
            apply_window_icon(self.window)
        except Exception:
            pass
        self.body = ctk.CTkFrame(self.window, fg_color="transparent")
        self.body.pack(fill=BOTH, expand=True, padx=PAD_DIALOG, pady=PAD_DIALOG)
        try:
            self.window.transient(parent)
        except Exception:
            pass
        try:
            self.window.grab_set()
            self.window.protocol("WM_DELETE_WINDOW",
                                  lambda: self.close(escape_value))
            self.window.bind("<Escape>", self._on_escape)
        except Exception:
            pass

    def _key_widgets(self):
        return [self.window, self.body]

    def _teardown(self):
        try:
            self.window.destroy()
        except Exception:
            pass

    def wait(self):
        self.window.wait_window()
        return self.result


def make_card(host, parent, width=520, escape_value=None, title=PROJECT_NAME):
    """有宿主就用窗口内覆盖层；没有宿主（启动极早期）才退化成 Toplevel。"""
    if host is not None:
        return OverlayCard(host, width=width, escape_value=escape_value)
    return ToplevelCard(parent, width=width, escape_value=escape_value,
                         title=title)


def show_message(parent, title, text, kind="info", buttons=None, escape_value=None):
    """
    自绘的窗口内对话框（替代 messagebox.*）。
    parent 只用于兼容原调用形式；宿主统一走 set_overlay_host 注册的实例。
    返回被点击按钮的值：普通提示为 True，ask 类为 True/False，ESC 为 escape_value。
    """
    if escape_value is None:
        escape_value = False if kind == "question" else True
    specs = buttons if buttons is not None else _DEFAULT_BUTTONS.get(
        kind, _DEFAULT_BUTTONS["info"])

    def _build_and_wait():
        card = make_card(_OVERLAY_HOST, parent,
                          width=_OVERLAY_WIDTH.get(kind, 480),
                          escape_value=escape_value, title=title)
        card.add_title(title)
        card.add_text(text)
        card.add_buttons(specs)
        return card.wait()

    return _run_modal(_build_and_wait)


def show_info(title, message="", parent=None, **kwargs):
    return show_message(parent, title, message, "info")


def show_warning(title, message="", parent=None, **kwargs):
    return show_message(parent, title, message, "warning")


def show_error(title, message="", parent=None, **kwargs):
    return show_message(parent, title, message, "error")


def ask_yes_no(title, message="", parent=None, **kwargs):
    return bool(show_message(parent, title, message, "question"))


def ask_ok_cancel(title, message="", parent=None, **kwargs):
    return bool(show_message(
        parent, title, message, "question",
        buttons=[("确定", True, True), ("取消", False, False)],
        escape_value=False))


class _MessageBoxCompat:
    """
    兼容垫片：本文件已把所有 messagebox.* 调用点换成 show_*/ask_*（见上方），
    这个对象保证万一还有漏改或后续新增的 messagebox.xxx(...) 调用，
    也仍然走窗口内覆盖层，而不是退回系统新窗口。
    """

    @staticmethod
    def showinfo(title=None, message="", **kwargs):
        return show_info(title, message)

    @staticmethod
    def showwarning(title=None, message="", **kwargs):
        return show_warning(title, message)

    @staticmethod
    def showerror(title=None, message="", **kwargs):
        return show_error(title, message)

    @staticmethod
    def askyesno(title=None, message="", **kwargs):
        return ask_yes_no(title, message)

    @staticmethod
    def askokcancel(title=None, message="", **kwargs):
        return ask_ok_cancel(title, message)

    @staticmethod
    def askquestion(title=None, message="", **kwargs):
        return "yes" if ask_yes_no(title, message) else "no"


messagebox = _MessageBoxCompat()


# ==================== 数据库定位 ====================
class DatabaseLocator:
    @staticmethod
    def load_db_path() -> Path | None:
        # 先读当前数据目录下的配置，再兼容旧版写在程序目录的配置
        candidates = [BOOTSTRAP_FILE]
        if LEGACY_BOOTSTRAP_FILE != BOOTSTRAP_FILE:
            candidates.append(LEGACY_BOOTSTRAP_FILE)
        for cfg in candidates:
            try:
                if not cfg.exists():
                    continue
                with open(cfg, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                path = data.get('database_path')
                if path:
                    return Path(path)
            except Exception:
                continue
        return None

    @staticmethod
    def save_db_path(path: Path) -> bool:
        targets = [BOOTSTRAP_FILE]
        if LEGACY_BOOTSTRAP_FILE != BOOTSTRAP_FILE:
            targets.append(LEGACY_BOOTSTRAP_FILE)
        last_error = None
        for cfg in targets:
            try:
                cfg.parent.mkdir(parents=True, exist_ok=True)
                with open(cfg, 'w', encoding='utf-8') as f:
                    json.dump({'database_path': str(path)}, f,
                              indent=2, ensure_ascii=False)
                return True
            except Exception as e:
                last_error = e
        safe_print(f"保存数据库位置失败: {type(last_error).__name__}: {last_error}")
        return False

    @staticmethod
    def is_valid_database(path: Path) -> bool:
        if not path.exists() or not path.is_dir():
            return False
        if (path / '.settings.json').exists() or (path / '.global.json').exists():
            return True
        try:
            for sub in path.iterdir():
                if sub.is_dir() and (sub / 'index.json').exists():
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def is_empty_folder(path: Path) -> bool:
        if not path.exists() or not path.is_dir():
            return False
        try:
            return not any(path.iterdir())
        except Exception:
            return False

    @staticmethod
    def init_database_detailed(path: Path) -> tuple[bool, str]:
        """创建数据库。失败时把真实异常类型与消息一并返回，交给调用方展示。"""
        try:
            path.mkdir(parents=True, exist_ok=True)
            sf = path / '.settings.json'
            if not sf.exists():
                with open(sf, 'w', encoding='utf-8') as f:
                    json.dump({'storage_mode': 'isolated', 'role': 'player'},
                              f, indent=2, ensure_ascii=False)
            gf = path / '.global.json'
            if not gf.exists():
                with open(gf, 'w', encoding='utf-8') as f:
                    json.dump({'recent_packs': []}, f, indent=2, ensure_ascii=False)
            return True, ""
        except Exception as e:
            detail = f"{type(e).__name__}: {e}"
            safe_print(f"初始化数据库失败: {detail} (位置: {path})")
            return False, detail

    @staticmethod
    def init_database(path: Path) -> bool:
        ok, _ = DatabaseLocator.init_database_detailed(path)
        return ok


# ==================== 旧版 FGC v2 数据库适配 ====================
class LegacyDatabaseMigrator:
    @staticmethod
    def is_legacy_database(path: Path) -> bool:
        if not path or not path.exists() or not path.is_dir():
            return False
        if (path / LEGACY_MIGRATED_MARKER).exists():
            return False
        if path.name == LEGACY_DB_DIRNAME:
            return True
        cache = path / LEGACY_CACHE_FILE
        if cache.exists():
            try:
                with open(cache, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                presets = data.get('presets', {})
                for info in presets.values():
                    if 'version' not in info:
                        return True
                    for v in info.get('gunpacks', {}).values():
                        if isinstance(v, list):
                            return True
            except Exception:
                pass
        try:
            for sub in path.iterdir():
                if sub.is_dir() and not sub.name.startswith('.'):
                    idx = sub / 'index.json'
                    if idx.exists() and not (sub / 'version.txt').exists():
                        return True
        except Exception:
            pass
        return False

    @staticmethod
    def find_legacy_databases(root: Path) -> list[Path]:
        found = []
        candidates = [
            root / LEGACY_DB_DIRNAME,
            root / 'tacz' / LEGACY_DB_DIRNAME,
        ]
        if root.parent:
            candidates.append(root.parent / LEGACY_DB_DIRNAME)
        for c in candidates:
            if c and c.exists() and LegacyDatabaseMigrator.is_legacy_database(c):
                found.append(c)
        return found

    @staticmethod
    def convert_preset_index(legacy_data: dict, preset_path: Path) -> dict:
        raw = legacy_data.get('gunpacks', {})
        standard = {}
        for name, value in raw.items():
            item_path = preset_path / name
            fp = get_item_fingerprint(item_path)
            if fp:
                standard[name] = fp
            elif isinstance(value, (list, tuple)):
                standard[name] = {
                    'type': 'zip', 'size': 0, 'file_count': 1,
                    'legacy_hash': str(value[0]) if value else ''}
            elif isinstance(value, dict):
                standard[name] = value
            else:
                standard[name] = {'type': 'zip', 'size': 0, 'file_count': 1}

        version = (legacy_data.get('version')
                   or legacy_data.get('description')
                   or 'v1.0.0')
        return {
            'name': legacy_data.get('name', preset_path.name),
            'version': version,
            'description': legacy_data.get('description', ''),
            'gunpacks': standard,
            'applied': legacy_data.get('applied', False),
            'incremental_count': legacy_data.get('incremental_count', 0),
            'legacy_migrated': True,
        }

    @staticmethod
    def migrate_legacy_to_new(legacy_db: Path, new_db: Path,
                              log_manager=None,
                              conflict_mode: str = 'rename',
                              progress_callback=None,
                              after_migrate: str = 'mark') -> dict:
        stats = {'migrated': 0, 'skipped': 0, 'renamed': 0,
                 'errors': [], 'disposed': 'none'}
        new_db.mkdir(parents=True, exist_ok=True)

        try:
            preset_dirs = [p for p in legacy_db.iterdir()
                           if p.is_dir() and not p.name.startswith('.')]
        except Exception as e:
            if log_manager:
                log_manager.log(f"扫描旧版数据库失败: {e}", 'ERROR')
            stats['errors'].append(f"扫描失败: {e}")
            return stats

        total = len(preset_dirs)
        if log_manager:
            log_manager.log(
                f"开始适配旧版数据库，共 {total} 个预设", 'PROCESS')

        for idx, preset_dir in enumerate(preset_dirs):
            target_name = preset_dir.name
            target_path = new_db / target_name

            if target_path.exists():
                if conflict_mode == 'skip':
                    stats['skipped'] += 1
                    if log_manager:
                        log_manager.log(f"跳过已存在预设: {target_name}", 'WARNING')
                    if progress_callback:
                        progress_callback(idx + 1, total, f"跳过 {target_name}")
                    continue
                elif conflict_mode == 'rename':
                    i = 1
                    while (new_db / f"{target_name}_legacy{i}").exists():
                        i += 1
                    target_name = f"{target_name}_legacy{i}"
                    target_path = new_db / target_name
                    stats['renamed'] += 1
                elif conflict_mode == 'overwrite':
                    shutil.rmtree(target_path, ignore_errors=True)

            try:
                shutil.copytree(preset_dir, target_path)
                idx_file = target_path / 'index.json'
                new_data = None
                if idx_file.exists():
                    with open(idx_file, 'r', encoding='utf-8') as f:
                        legacy_data = json.load(f)
                    new_data = LegacyDatabaseMigrator.convert_preset_index(
                        legacy_data, target_path)
                    with open(idx_file, 'w', encoding='utf-8') as f:
                        json.dump(new_data, f, indent=2, ensure_ascii=False)
                with open(target_path / 'version.txt', 'w', encoding='utf-8') as f:
                    f.write((new_data or {}).get('version', 'v1.0.0'))
                stats['migrated'] += 1
                if log_manager:
                    log_manager.log(
                        f"已迁移预设: {preset_dir.name} -> {target_name}", 'SUCCESS')
            except Exception as e:
                stats['errors'].append(f"{preset_dir.name}: {e}")
                if log_manager:
                    log_manager.log(f"迁移 {preset_dir.name} 失败: {e}", 'ERROR')

            if progress_callback:
                progress_callback(idx + 1, total, f"迁移 {preset_dir.name}")

        if after_migrate == 'mark':
            try:
                marker = legacy_db / LEGACY_MIGRATED_MARKER
                with open(marker, 'w', encoding='utf-8') as f:
                    json.dump({
                        'migrated_to': str(new_db),
                        'migrated_at': datetime.now().isoformat(),
                        'migrated_count': stats['migrated'],
                        'renamed_count': stats['renamed'],
                        'skipped_count': stats['skipped'],
                    }, f, indent=2, ensure_ascii=False)
                stats['disposed'] = 'marked'
                if log_manager:
                    log_manager.log(
                        f"已在旧库写入迁移标记: {marker}", 'SUCCESS')
            except Exception as e:
                stats['errors'].append(f"写迁移标记失败: {e}")
                if log_manager:
                    log_manager.log(f"写迁移标记失败: {e}", 'ERROR')

        elif after_migrate == 'delete':
            try:
                ok = move_to_recycle_bin(legacy_db)
                if ok:
                    stats['disposed'] = 'recycled'
                    if log_manager:
                        log_manager.log(
                            f"旧版数据库已移入回收站: {legacy_db}", 'SUCCESS')
                else:
                    shutil.rmtree(legacy_db, ignore_errors=True)
                    stats['disposed'] = 'deleted'
                    if log_manager:
                        log_manager.log(
                            f"旧版数据库已删除（无法移入回收站）: {legacy_db}",
                            'SUCCESS')
            except Exception as e:
                stats['errors'].append(f"删除旧库失败: {e}")
                if log_manager:
                    log_manager.log(f"删除旧库失败: {e}", 'ERROR')

        return stats


# ==================== 数据库定位对话框 ====================
class DatabaseLocatorDialog:
    def __init__(self, parent):
        self.parent = parent
        self.result: Path | None = None
        self.legacy_to_migrate: Path | None = None

    def show(self) -> Path | None:
        # 改为主窗口内覆盖层，不再新开窗口。启动流程里 setup_ui() 先于
        # _init_database_flow() 执行，所以这里主窗口骨架一定已经建好；
        # 万一宿主未注册，make_card 会退化成 Toplevel，保证提示不会静默丢失。
        dlg_w = DLG_LOCATOR[0]
        card = make_card(get_overlay_host(), self.parent, width=dlg_w,
                          escape_value=None, title="初始化 Pulses Swap")
        frame = card.body

        make_label(frame, text="欢迎使用 Pulses Swap",
                    fg=C_ACCENT, font_size=FS_TITLE, bold=True).pack(
                        anchor=W, pady=(0, PAD_TIGHT))
        make_label(frame, text="Step 1 · 选择数据库位置",
                    fg=C_GUIDE_GLOW, font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, pady=(0, PAD_INNER))

        desc = make_label(frame,
            text="首次启动需要指定数据库位置。\n"
                 "数据库用于保存预设、校验数据和程序设置。\n\n"
                 "• 新用户 → 点「新建数据库」或「使用默认位置」\n"
                 "• 已有 Pulses Swap 数据库 → 点「定位已有数据库」\n"
                 "• 有旧版 FGC_database → 点「适配旧版数据库」",
            fg=C_TEXT_SECONDARY, font_size=FS_BODY)
        desc.configure(wraplength=dlg_w - 2 * PAD_DIALOG - 6, justify=LEFT, anchor=W)
        desc.pack(anchor=W, fill=X, pady=(0, PAD_DIALOG))

        loc_frame = ctk.CTkFrame(frame, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                   border_width=BORDER_W, border_color=C_BORDER_SOFT)
        loc_frame.pack(fill=X, pady=(0, PAD_DIALOG))

        make_label(loc_frame,
                    text=("默认数据库位置（与程序同目录）:" if IS_PORTABLE_MODE
                          else "默认数据库位置（用户数据目录）:"),
                    fg=C_TEXT_SECONDARY, font_size=FS_SMALL).pack(
                        anchor=W, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        make_label(loc_frame, text=str(DEFAULT_DB_DIR),
                    fg=C_TEXT_MAIN, font_size=FS_SMALL).pack(
                        anchor=W, padx=PAD_CARD_X, pady=(0, PAD_CARD_Y))

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill=X, pady=(0, PAD_TIGHT))

        btn_refs = {}

        def _highlight(target_key):
            for k, b in btn_refs.items():
                try:
                    if k == target_key:
                        b.configure(border_color=C_GUIDE_GLOW,
                                    border_width=BORDER_W_FOCUS)
                    else:
                        b.configure(border_color=C_BORDER_SOFT,
                                    border_width=BORDER_W)
                except Exception:
                    pass

        def _init_or_report(path, title):
            """创建数据库；失败时把真实异常类型/消息带进弹窗，而不是只说一句失败。"""
            ok, err = DatabaseLocator.init_database_detailed(path)
            if not ok:
                show_error(
                    "错误", f"{title}：{err}\n位置: {path}", parent=self.parent)
            return ok

        def _choose(path, legacy=None):
            """选定数据库并关闭覆盖层。"""
            self.result = path
            if legacy is not None:
                self.legacy_to_migrate = legacy
            card.close(True)

        def on_existing():
            folder = filedialog.askdirectory(
                title="选择已有的数据库文件夹",
                initialdir=str(PROGRAM_DIR),
                parent=self.parent)
            if not folder:
                return
            path = Path(folder)
            if LegacyDatabaseMigrator.is_legacy_database(path):
                if ask_yes_no("检测到旧版数据库",
                    "该文件夹是旧版 FGC_database。\n\n"
                    "是否先适配为新版数据库？", parent=self.parent):
                    if _init_or_report(DEFAULT_DB_DIR, "创建数据库失败"):
                        _choose(DEFAULT_DB_DIR, legacy=path)
                return
            if DatabaseLocator.is_valid_database(path):
                _choose(path)
            else:
                show_error("错误",
                    "所选文件夹不是有效的数据库。\n\n"
                    "有效的数据库应包含 .settings.json 或预设子文件夹。",
                    parent=self.parent)

        def on_legacy():
            folder = filedialog.askdirectory(
                title="选择旧版 FGC_database 文件夹",
                initialdir=str(PROGRAM_DIR),
                parent=self.parent)
            if not folder:
                return
            path = Path(folder)
            if not LegacyDatabaseMigrator.is_legacy_database(path):
                if (path / LEGACY_MIGRATED_MARKER).exists():
                    show_info("已迁移",
                        "该旧版数据库已被标记为「已迁移」。\n\n"
                        "如需重新适配，请手动删除旧库根目录下的\n"
                        f"{LEGACY_MIGRATED_MARKER} 文件后再试。",
                        parent=self.parent)
                else:
                    show_error("错误",
                        "所选文件夹不是旧版 FGC_database。\n\n"
                        "旧版数据库应包含预设子文件夹和 index.json。",
                        parent=self.parent)
                return
            if _init_or_report(DEFAULT_DB_DIR, "创建数据库失败"):
                _choose(DEFAULT_DB_DIR, legacy=path)

        def on_new():
            # 默认在数据目录下新建（便携模式即程序目录）
            default_hint = ("程序目录" if IS_PORTABLE_MODE else "用户数据目录")
            if ask_yes_no("新建数据库",
                f"是否在{default_hint}下新建数据库？\n\n"
                f"位置: {DEFAULT_DB_DIR}\n\n"
                f"选「否」可手动选择其他文件夹。",
                parent=self.parent):
                path = DEFAULT_DB_DIR
            else:
                folder = filedialog.askdirectory(
                    title="选择用于新建数据库的文件夹",
                    initialdir=str(PROGRAM_DIR),
                    parent=self.parent)
                if not folder:
                    return
                path = Path(folder)
            if path.exists() and not DatabaseLocator.is_empty_folder(path):
                if DatabaseLocator.is_valid_database(path):
                    _choose(path)
                    return
                show_error("错误",
                    "所选文件夹非空且不是有效数据库。\n\n"
                    "请选择一个空文件夹用于新建数据库。",
                    parent=self.parent)
                return
            if _init_or_report(path, "创建数据库失败"):
                _choose(path)

        def on_default():
            if _init_or_report(DEFAULT_DB_DIR, "创建默认数据库失败"):
                _choose(DEFAULT_DB_DIR)

        b_exist = make_button(btn_frame, "定位已有数据库", command=on_existing)
        b_exist.pack(side=LEFT, padx=(0, PAD_TIGHT))
        b_legacy = make_button(btn_frame, "适配旧版数据库", command=on_legacy)
        b_legacy.pack(side=LEFT, padx=PAD_TIGHT)
        b_new = make_button(btn_frame, "新建数据库", command=on_new, accent=True)
        b_new.pack(side=LEFT, padx=PAD_TIGHT)
        b_default = make_button(btn_frame, "使用默认位置", command=on_default)
        b_default.pack(side=LEFT, padx=PAD_TIGHT)
        for _btn in (b_exist, b_legacy, b_new, b_default):
            card.register_focusable(_btn)

        btn_refs = {
            'exist': b_exist, 'legacy': b_legacy,
            'new': b_new, 'default': b_default,
        }
        _highlight('new')

        card.wait()
        return self.result


# ==================== 设置管理 ====================
class AppSettings:
    def __init__(self):
        self.storage_mode = "isolated"
        self.role = "player"
        self._settings_file: Path | None = None

    def bind_database(self, db_path: Path):
        self._settings_file = db_path / ".settings.json"
        self.load()

    def load(self):
        if self._settings_file and self._settings_file.exists():
            try:
                with open(self._settings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.storage_mode = data.get('storage_mode', 'isolated')
                self.role = data.get('role', 'player')
            except Exception:
                pass

    def save(self) -> bool:
        if not self._settings_file:
            return False
        try:
            self._settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._settings_file, 'w', encoding='utf-8') as f:
                json.dump({'storage_mode': self.storage_mode, 'role': self.role},
                          f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"保存设置失败: {e}")
            return False

    def get_db_path(self, pack_path: Path) -> Path:
        if not self._settings_file:
            return DEFAULT_DB_DIR / "unknown"
        base = self._settings_file.parent
        if self.storage_mode == "merged":
            return base
        return pack_path / "PulsesSwap_database"


# ==================== 日志系统 ====================
class LogManager:
    """日志缓冲 + 显示。

    显示分两档：
      · 单行模式（默认）：只显示「最近一条非细节日志」，避免回显类噪声刷屏；
      · 完整日志（日志页「显示完整日志」）：显示全部，含细节/进度条目。
    细节条目仍然会被记录，只是单行模式下不占用显示位。
    """

    # 这些层级默认算「细节日志」，只有完整日志模式才显示
    VERBOSE_LEVELS = ("DEBUG", "PROCESS")

    def __init__(self, text_widget, root):
        self.text_widget = text_widget
        self.root = root
        self.full_log = []          # [(log_line, level, verbose)]
        self.show_full = False
        self.widgets = []           # 同一份日志可以同时投到多个文本框
        self._configure_tags(text_widget)
        self.widgets.append(text_widget)

    @staticmethod
    def _configure_tags(widget):
        try:
            inner = widget._textbox
            inner.tag_configure('INFO', foreground=C_TEXT_MAIN)
            inner.tag_configure('WARNING', foreground=C_WARNING)
            inner.tag_configure('ERROR', foreground=C_ERROR)
            inner.tag_configure('SUCCESS', foreground=C_SUCCESS)
            inner.tag_configure('DEBUG', foreground=C_INFO)
            inner.tag_configure('PROCESS', foreground='#8E7BB8')
            inner.tag_configure('GUIDE', foreground=C_GUIDE_GLOW)
            inner.tag_configure('timestamp', foreground=C_TEXT_MUTED)
        except Exception:
            pass

    def attach(self, widget):
        """把同一份日志同时投到另一个文本框（主界面右下角的日志栏）。"""
        if widget is None or widget in self.widgets:
            return widget
        self._configure_tags(widget)
        self.widgets.append(widget)
        self._render(widget)
        return widget

    def log(self, message: str, level: str = 'INFO', verbose: bool = None):
        """verbose=None 时按层级判断；显式 True/False 可覆盖。"""
        if verbose is None:
            verbose = level in self.VERBOSE_LEVELS
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_line = f"[{timestamp}] [{level}] {message}\n"
        self.full_log.append((log_line, level, bool(verbose)))
        if threading.current_thread() is threading.main_thread():
            self._update_display()
        else:
            self.root.after(0, self._update_display)

    def set_show_full(self, show_full: bool):
        self.show_full = show_full
        if threading.current_thread() is threading.main_thread():
            self._update_display()
        else:
            self.root.after(0, self._update_display)

    def _visible_entries(self):
        """当前该显示哪些行：完整模式全部，否则只留最近一条非细节日志。"""
        if self.show_full:
            return [(line, level) for line, level, _verbose in self.full_log]
        for log_line, level, verbose in reversed(self.full_log):
            if not verbose:
                return [(log_line, level)]
        return []

    def _update_display(self):
        for widget in list(self.widgets):
            self._render(widget)

    def _render(self, widget):
        try:
            widget.delete("1.0", END)
            for log_line, level in self._visible_entries():
                self._insert_log(widget, log_line, level)
            widget.see(END)
        except Exception:
            pass

    def _insert_log(self, widget, log_line: str, level: str):
        try:
            inner = widget._textbox
            end = log_line.find(']') + 1
            inner.insert(END, log_line[:end], 'timestamp')
            inner.insert(END, log_line[end:], level)
        except Exception:
            try:
                widget.insert(END, log_line)
            except Exception:
                pass

    def clear(self):
        self.full_log.clear()
        for widget in list(self.widgets):
            try:
                widget.delete("1.0", END)
            except Exception:
                pass


# ==================== 新手引导系统 ====================
class GuideManager:
    def __init__(self, root):
        self.root = root
        self._steps: dict = {}
        self._current: str | None = None
        self._originals: dict = {}

    def register(self, step_name: str, widgets: list,
                 desc: str = "", colors: tuple = None):
        self._steps[step_name] = {
            'widgets': [w for w in widgets if w is not None],
            'desc': desc,
            'colors': colors or (C_GUIDE_GLOW, BORDER_W_FOCUS),
        }

    def clear_registered(self):
        self._steps.clear()

    def show(self, step_name: str):
        self._restore_all()
        if step_name not in self._steps:
            self._current = None
            return
        self._current = step_name
        info = self._steps[step_name]
        border_color, border_width = info['colors']
        for w in info['widgets']:
            self._highlight(w, border_color, border_width)

    def hide(self):
        self._restore_all()
        self._current = None

    def _highlight(self, widget, color, width):
        try:
            wid = id(widget)
            if wid not in self._originals:
                try:
                    orig_bc = widget.cget('border_color')
                except Exception:
                    orig_bc = C_BORDER
                try:
                    orig_bw = widget.cget('border_width')
                except Exception:
                    orig_bw = BORDER_W
                self._originals[wid] = {
                    'widget': widget,
                    'border_color': orig_bc,
                    'border_width': orig_bw,
                }
            widget.configure(border_width=width)
            self._pulse(widget, color)
        except Exception:
            pass

    def _pulse(self, widget, color):
        """描边呼吸：在强调色与提亮色之间来回缓动（三角波），直到 hide()。"""
        light = lerp_color(color, "#FFFFFF", 0.6)

        def frame(e, raw):
            triangle = raw if raw <= 0.5 else (1.0 - raw)
            try:
                widget.configure(
                    border_color=lerp_color(color, light, triangle))
            except Exception:
                pass

        frame(0.0, 0.0)
        tween(widget, "guide", 1100, frame, on_done=lambda: self._pulse(
            widget, color), easing=ease_linear)

    def _restore_all(self):
        for wid, saved in list(self._originals.items()):
            try:
                w = saved['widget']
                cancel_tween(w, "guide")
                w.configure(border_color=saved['border_color'],
                            border_width=saved['border_width'])
            except Exception:
                pass
        self._originals.clear()


# ==================== 最近打开 ====================
class RecentPacksManager:
    def __init__(self, path: Path):
        self.path = path
        self.recent = []
        self.load()

    def load(self):
        if self.path.exists():
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.recent = data.get('recent_packs', [])
            except Exception:
                self.recent = []

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            if self.path.exists():
                try:
                    with open(self.path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except Exception:
                    data = {}
            data['recent_packs'] = self.recent
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def add(self, pack_path: str, pack_name: str):
        self.recent = [r for r in self.recent if r.get('path') != pack_path]
        self.recent.insert(0, {
            'path': pack_path, 'name': pack_name,
            'last_opened': datetime.now().isoformat()})
        self.recent = self.recent[:10]
        self.save()

    def get_all(self) -> list[dict]:
        return self.recent


# ==================== TACZ 文件监控 ====================
class _TaczEventHandler(FileSystemEventHandler):
    IGNORE_NAMES = {'tacz-pre.toml', '.export-state.json', 'blacklist.txt'}
    IGNORE_DIRS = {'tacz_default_gun'}

    def __init__(self, trigger):
        super().__init__()
        self.trigger = trigger

    def _interesting(self, path_str: str) -> bool:
        if not path_str:
            return False
        name = os.path.basename(path_str)
        if name in self.IGNORE_NAMES:
            return False
        if name.startswith('.') or name.endswith('.tmp') or name.endswith('~'):
            return False
        try:
            parts = Path(path_str).parts
            for d in self.IGNORE_DIRS:
                if d in parts:
                    return False
        except Exception:
            pass
        return True

    def on_any_event(self, event):
        try:
            if event.event_type == 'opened':
                return
            if not self._interesting(event.src_path):
                return
            dest = getattr(event, 'dest_path', None)
            if dest and not self._interesting(dest):
                return
            self.trigger()
        except Exception:
            pass


class TaczWatcher:
    DEBOUNCE_SEC = 0.8

    def __init__(self, tacz_path: Path, on_change_callback, log_manager=None):
        self.tacz_path = tacz_path
        self.on_change_callback = on_change_callback
        self.log = log_manager
        self.observer = None
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active

    def start(self) -> bool:
        if not HAS_WATCHDOG or self._active:
            return False
        if not self.tacz_path or not self.tacz_path.exists():
            return False
        try:
            handler = _TaczEventHandler(self._schedule)
            self.observer = Observer()
            self.observer.daemon = True
            self.observer.schedule(handler, str(self.tacz_path), recursive=True)
            self.observer.start()
            self._active = True
            if self.log:
                self.log.log(f"已启动 TACZ 监控: {self.tacz_path}", 'INFO',
                                  verbose=True)
            return True
        except Exception as e:
            if self.log:
                self.log.log(f"启动 TACZ 监控失败: {e}", 'WARNING')
            self.observer = None
            self._active = False
            return False

    def stop(self):
        with self._lock:
            if self._timer is not None:
                try:
                    self._timer.cancel()
                except Exception:
                    pass
                self._timer = None
        if self.observer is not None:
            try:
                self.observer.stop()
                self.observer.join(timeout=2)
            except Exception:
                pass
            self.observer = None
        if self._active and self.log:
            self.log.log("已停止 TACZ 监控", 'INFO', verbose=True)
        self._active = False

    def _schedule(self):
        with self._lock:
            if self._timer is not None:
                try:
                    self._timer.cancel()
                except Exception:
                    pass
            self._timer = threading.Timer(self.DEBOUNCE_SEC, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self):
        with self._lock:
            self._timer = None
        try:
            self.on_change_callback()
        except Exception as e:
            if self.log:
                self.log.log(f"文件变更回调出错: {e}", 'WARNING')


# ==================== 预设数据管理 ====================
class PresetManager:
    PROTECTED_FILES = ['tacz-pre.toml', '.export-state.json', 'blacklist.txt']
    PROTECTED_DIRS = ['tacz_default_gun']
    CACHE_FILE = '.cache.json'
    BATCH_SIZE = 5
    BATCH_DELAY = 0.005

    def __init__(self, db_path: Path, log_manager, tacz_path=None, pack_name=""):
        self.database_path = db_path
        self.tacz_path = tacz_path
        self.pack_name = pack_name
        self.log = log_manager
        self.current_preset: str | None = None
        self.presets: dict[str, dict] = {}
        self.cache_path = db_path / self.CACHE_FILE if db_path else None

    def load_from_cache(self) -> bool:
        if not self.cache_path or not self.cache_path.exists():
            return False
        try:
            with open(self.cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            db_mtime = self.database_path.stat().st_mtime if self.database_path.exists() else 0
            if cache_data.get('db_mtime', 0) != db_mtime:
                return False
            self.presets = cache_data.get('presets', {})
            self.current_preset = cache_data.get('current_preset')
            self.log.log(f"从缓存加载预设成功，共 {len(self.presets)} 个预设",
                          'SUCCESS', verbose=True)
            return True
        except Exception as e:
            self.log.log(f"加载缓存失败: {e}", 'WARNING')
            return False

    def save_cache(self):
        if not self.cache_path:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'db_mtime': self.database_path.stat().st_mtime if self.database_path.exists() else 0,
                    'presets': self.presets,
                    'current_preset': self.current_preset
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log.log(f"保存缓存失败: {e}", 'WARNING')

    def load_all_presets(self, use_cache: bool = True):
        if use_cache and self.load_from_cache():
            return
        self.presets = {}
        if not self.database_path.exists():
            return
        for preset_dir in self.database_path.iterdir():
            if preset_dir.is_dir() and not preset_dir.name.startswith('.'):
                self._load_preset(preset_dir)
        self.log.log(f"预设加载完成，共 {len(self.presets)} 个预设", 'INFO',
                          verbose=True)
        self.save_cache()

    def _load_preset(self, preset_path: Path):
        try:
            index_file = preset_path / 'index.json'
            if not index_file.exists():
                self.presets[preset_path.name] = {
                    'path': str(preset_path), 'name': preset_path.name,
                    'version': 'v1.0.0', 'gunpacks': {}, 'applied': False,
                    'incremental_count': 0}
                return
            with open(index_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            raw = data.get('gunpacks', {})
            standard = {}
            for name, value in raw.items():
                if isinstance(value, dict):
                    standard[name] = value
                elif isinstance(value, (list, tuple)):
                    standard[name] = {'type': 'zip', 'size': 0,
                                      'file_count': 1,
                                      'legacy_hash': str(value[0]) if value else ''}
                else:
                    standard[name] = {'type': 'zip', 'size': 0, 'file_count': 1}
            if standard != raw:
                data['gunpacks'] = standard
                with open(index_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                self.log.log(f"预设 '{preset_path.name}' 已自动适配为新格式", 'INFO',
                          verbose=True)

            version = (data.get('version')
                       or data.get('description')
                       or 'v1.0.0')
            self.presets[preset_path.name] = {
                'path': str(preset_path),
                'name': data.get('name', preset_path.name),
                'version': version,
                'gunpacks': standard,
                'applied': data.get('applied', False),
                'incremental_count': data.get('incremental_count', 0)}
            if self.presets[preset_path.name]['applied']:
                self.current_preset = preset_path.name
        except Exception as e:
            self.log.log(f"加载预设 {preset_path.name} 失败: {e}", 'ERROR')

    def create_preset(self, name: str, version: str = 'v1.0.0') -> bool:
        if not name or name in self.presets:
            return False
        preset_path = self.database_path / name
        try:
            preset_path.mkdir(parents=True, exist_ok=True)
            index_data = {'name': name, 'version': version, 'gunpacks': {},
                          'applied': False, 'incremental_count': 0}
            with open(preset_path / 'index.json', 'w', encoding='utf-8') as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)
            with open(preset_path / 'version.txt', 'w', encoding='utf-8') as f:
                f.write(version)
            self.presets[name] = {
                'path': str(preset_path), 'name': name, 'version': version,
                'gunpacks': {}, 'applied': False, 'incremental_count': 0}
            self.save_cache()
            self.log.log(f"预设 '{name}' 创建成功", 'SUCCESS')
            return True
        except Exception as e:
            self.log.log(f"创建预设失败: {e}", 'ERROR')
            return False

    def update_preset_version(self, preset_name: str, version: str) -> bool:
        if preset_name not in self.presets:
            return False
        try:
            preset_info = self.presets[preset_name]
            preset_info['version'] = version
            preset_path = Path(preset_info['path'])
            index_file = preset_path / 'index.json'
            if index_file.exists():
                with open(index_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                data['version'] = version
                with open(index_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            with open(preset_path / 'version.txt', 'w', encoding='utf-8') as f:
                f.write(version)
            self.save_cache()
            return True
        except Exception as e:
            self.log.log(f"更新版本号失败: {e}", 'ERROR')
            return False

    def rename_preset(self, old_name: str, new_name: str) -> bool:
        if old_name not in self.presets or new_name in self.presets:
            return False
        if not new_name or not new_name.strip():
            return False
        for char in r'\/:*?"<>|':
            if char in new_name:
                self.log.log(f"预设名称不能包含非法字符: {char}", 'ERROR')
                return False
        try:
            preset_info = self.presets[old_name]
            old_path = Path(preset_info['path'])
            new_path = self.database_path / new_name
            was_applied = preset_info.get('applied', False)
            if was_applied:
                preset_info['applied'] = False
                self.current_preset = None
            old_path.rename(new_path)
            index_file = new_path / 'index.json'
            if index_file.exists():
                with open(index_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                data['name'] = new_name
                with open(index_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            preset_info['path'] = str(new_path)
            preset_info['name'] = new_name
            self.presets[new_name] = preset_info
            del self.presets[old_name]
            if was_applied:
                preset_info['applied'] = True
                self.current_preset = new_name
                self._update_preset_status(new_path, True)
            self.save_cache()
            return True
        except Exception as e:
            self.log.log(f"重命名预设失败: {e}", 'ERROR')
            return False

    def delete_preset(self, name: str) -> bool:
        if name not in self.presets:
            return False
        if self.presets[name].get('applied', False):
            self.log.log(f"预设 '{name}' 已应用，请先取消应用再删除", 'WARNING')
            return False
        try:
            preset_info = self.presets[name]
            preset_path = Path(preset_info['path'])
            if preset_path.exists():
                shutil.rmtree(preset_path)
            del self.presets[name]
            if self.current_preset == name:
                self.current_preset = None
            self.save_cache()
            return True
        except Exception as e:
            self.log.log(f"删除预设失败: {e}", 'ERROR')
            return False

    def _get_gunpacks_from_folder(self, folder_path: Path) -> dict:
        result = {}
        if not folder_path.exists():
            return result
        protected_all = self.PROTECTED_FILES + self.PROTECTED_DIRS
        for item in folder_path.iterdir():
            if item.name in ['description.txt', 'index.json', 'version.txt']:
                continue
            if item.name in protected_all:
                continue
            fp = get_item_fingerprint(item)
            if fp:
                result[item.name] = fp
        return result

    def detect_changes(self, preset_name: str) -> dict:
        preset_info = self.presets.get(preset_name)
        if not preset_info or not self.tacz_path:
            return {'added': [], 'removed': [], 'modified': []}
        current = self._get_gunpacks_from_folder(self.tacz_path)
        indexed = preset_info.get('gunpacks', {})
        added, removed, modified = [], [], []
        for name, curr_fp in current.items():
            if name not in indexed:
                added.append(name)
            elif not fingerprints_match(curr_fp, indexed[name]):
                modified.append(name)
        for name in indexed:
            if name not in current:
                removed.append(name)
        return {'added': added, 'removed': removed, 'modified': modified}

    def has_changes(self, preset_name: str) -> bool:
        c = self.detect_changes(preset_name)
        return bool(c['added'] or c['removed'] or c['modified'])

    def _move_items(self, src_dir: Path, dst_dir: Path, exclude=None,
                    progress_callback=None) -> int:
        if not src_dir.exists():
            return 0
        exclude = exclude or []
        items = [i for i in src_dir.iterdir() if i.name not in exclude]
        total = len(items)
        moved = 0
        for i, item in enumerate(items):
            try:
                dest = dst_dir / item.name
                if dest.exists():
                    if dest.is_dir():
                        shutil.rmtree(dest)
                    else:
                        dest.unlink()
                shutil.move(str(item), str(dest))
                moved += 1
                if progress_callback:
                    progress_callback(i + 1, total, f"移动 {item.name}")
                if (i + 1) % self.BATCH_SIZE == 0:
                    time.sleep(self.BATCH_DELAY)
            except Exception as e:
                self.log.log(f"移动 {item.name} 失败: {e}", 'WARNING')
        return moved

    def _clear_dir(self, dir_path: Path, exclude=None):
        if not dir_path.exists():
            return
        exclude = exclude or []
        for item in dir_path.iterdir():
            if item.name in exclude:
                continue
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except Exception as e:
                self.log.log(f"删除 {item.name} 失败: {e}", 'ERROR')

    def _safe_remove(self, path: Path) -> bool:
        if move_to_recycle_bin(path):
            return True
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            return True
        except Exception as e:
            self.log.log(f"删除 {path.name} 失败: {e}", 'ERROR')
            return False

    def apply_preset(self, preset_name: str, progress_callback=None) -> bool:
        if preset_name not in self.presets:
            return False
        if not self.tacz_path or not self.tacz_path.exists():
            return False
        current_applied = None
        for name, info in self.presets.items():
            if info.get('applied', False):
                current_applied = name
                break
        if current_applied == preset_name:
            return True
        target_preset = self.presets[preset_name]
        target_path = Path(target_preset['path'])
        protected_all = self.PROTECTED_FILES + self.PROTECTED_DIRS
        try:
            self.log.log(f"开始切换预设: {current_applied or 'None'} -> {preset_name}", 'PROCESS')
            if current_applied and current_applied in self.presets:
                cur_info = self.presets[current_applied]
                cur_path = Path(cur_info['path'])
                moved = self._move_items(self.tacz_path, cur_path, protected_all, progress_callback)
                cur_info['applied'] = False
                self._update_preset_status(cur_path, False)
                self.log.log(f"已回收 {moved} 个枪包到 '{current_applied}'", 'INFO',
                          verbose=True)
            self._clear_dir(self.tacz_path, protected_all)
            moved = self._move_items(target_path, self.tacz_path,
                                     ['description.txt', 'index.json', 'version.txt'],
                                     progress_callback)
            target_preset['applied'] = True
            self._update_preset_status(target_path, True)
            self.current_preset = preset_name
            self.save_cache()
            self.log.log(f"成功应用预设 '{preset_name}' (移动了 {moved} 个枪包)", 'SUCCESS')
            return True
        except Exception as e:
            self.log.log(f"应用预设失败: {e}", 'ERROR')
            return False

    def _update_preset_status(self, preset_path: Path, applied: bool):
        try:
            index_file = preset_path / 'index.json'
            if not index_file.exists():
                return
            with open(index_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data['applied'] = applied
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            for name, info in self.presets.items():
                if Path(info['path']) == preset_path:
                    info['applied'] = applied
                    break
            self.save_cache()
        except Exception as e:
            self.log.log(f"更新预设状态失败: {e}", 'ERROR')

    def update_preset_index(self, preset_name: str, from_tacz: bool = False) -> bool:
        if preset_name not in self.presets:
            return False
        preset_info = self.presets[preset_name]
        preset_path = Path(preset_info['path'])
        try:
            if from_tacz and self.tacz_path:
                gunpacks = self._get_gunpacks_from_folder(self.tacz_path)
                self.log.log(f"从Tacz读取到 {len(gunpacks)} 个枪包", 'INFO',
                          verbose=True)
            else:
                gunpacks = self._get_gunpacks_from_folder(preset_path)
                self.log.log(f"从预设 '{preset_name}' 读取到 {len(gunpacks)} 个枪包",
                          'INFO', verbose=True)
            index_data = {
                'name': preset_info['name'],
                'version': preset_info.get('version', 'v1.0.0'),
                'gunpacks': gunpacks,
                'applied': preset_info.get('applied', False),
                'incremental_count': preset_info.get('incremental_count', 0)}
            with open(preset_path / 'index.json', 'w', encoding='utf-8') as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)
            preset_info['gunpacks'] = gunpacks
            self.save_cache()
            self.log.log(f"预设 '{preset_name}' 校验数据已更新", 'SUCCESS')
            return True
        except Exception as e:
            self.log.log(f"更新预设索引失败: {e}", 'ERROR')
            return False

    def export_preset(self, preset_name: str, export_path: Path, progress_callback=None) -> bool:
        if preset_name not in self.presets:
            return False
        if preset_name == "default":
            self.log.log("不允许导出名为 'default' 的预设", 'ERROR')
            return False

        preset_info = self.presets[preset_name]
        preset_path = Path(preset_info['path'])
        was_applied = preset_info.get('applied', False)

        if was_applied and self.tacz_path and self.tacz_path.exists():
            source_path = self.tacz_path
            self.log.log(f"预设 '{preset_name}' 已应用，从 TACZ 读取枪包内容",
                          'INFO', verbose=True)
        else:
            source_path = preset_path
            self.log.log(f"从预设文件夹读取导出内容: {preset_name}", 'INFO',
                          verbose=True)

        try:
            if was_applied and self.tacz_path and self.tacz_path.exists():
                current_gunpacks = self._get_gunpacks_from_folder(self.tacz_path)
            else:
                current_gunpacks = self._get_gunpacks_from_folder(preset_path)

            index_data = {
                'name': preset_info['name'],
                'version': preset_info.get('version', 'v1.0.0'),
                'gunpacks': current_gunpacks,
                'applied': was_applied,
                'incremental_count': preset_info.get('incremental_count', 0)
            }
            with open(preset_path / 'index.json', 'w', encoding='utf-8') as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)

            protected_all = self.PROTECTED_FILES + self.PROTECTED_DIRS
            items = []
            added_names = set()

            if source_path == preset_path:
                for item in source_path.rglob('*'):
                    if item == source_path:
                        continue
                    rel = item.relative_to(source_path)
                    if rel.parts and rel.parts[0] in protected_all:
                        continue
                    items.append(item)
                    added_names.add(str(rel))
            else:
                for item in source_path.rglob('*'):
                    if item == source_path:
                        continue
                    rel = item.relative_to(source_path)
                    if rel.parts and rel.parts[0] in protected_all:
                        continue
                    items.append(item)
                    added_names.add(str(rel))

                for meta_name in ['index.json', 'description.txt', 'version.txt']:
                    meta_path = preset_path / meta_name
                    if meta_path.exists() and meta_name not in added_names:
                        items.append(meta_path)
                        added_names.add(meta_name)

            total = len(items)
            if total == 0:
                with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_STORED):
                    pass
                self.log.log(f"预设 '{preset_name}' 导出成功（空包）", 'SUCCESS')
                if progress_callback:
                    progress_callback(0, 0, "完成")
                return True

            self.log.log(f"正在打包 {total} 个项目...", 'PROCESS')
            with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_STORED) as zipf:
                for idx, item in enumerate(items):
                    try:
                        if source_path == preset_path:
                            arcname = item.relative_to(preset_path)
                        else:
                            try:
                                arcname = item.relative_to(source_path)
                            except ValueError:
                                arcname = item.relative_to(preset_path)

                        if item.is_file():
                            zipf.write(item, arcname)
                        else:
                            zipf.write(item, str(arcname) + '/')
                    except Exception as e:
                        self.log.log(f"打包 {item.name} 失败: {e}", 'WARNING')
                    if progress_callback and idx % 2 == 0:
                        progress_callback(idx + 1, total, f"打包 {item.name}")
                    if idx % 20 == 0:
                        time.sleep(0.001)

            self.log.log(f"预设 '{preset_name}' 导出成功: {export_path.name}", 'SUCCESS')
            if progress_callback:
                progress_callback(total, total, "完成")
            return True

        except Exception as e:
            self.log.log(f"导出预设失败: {e}", 'ERROR')
            return False

    def export_incremental(self, preset_name: str, export_path: Path, progress_callback=None) -> bool:
        if preset_name not in self.presets or not self.tacz_path:
            return False
        if preset_name == "default":
            self.log.log("不允许导出名为 'default' 的预设", 'ERROR')
            return False

        preset_info = self.presets[preset_name]
        if not preset_info.get('applied', False):
            self.log.log("只能对已应用的预设导出增量更新", 'ERROR')
            return False

        changes = self.detect_changes(preset_name)
        total_changes = len(changes['added']) + len(changes['removed']) + len(changes['modified'])
        if total_changes == 0:
            self.log.log("未检测到任何变更", 'INFO')
            return False
        self.log.log(
            f"检测到变更: 新增 {len(changes['added'])} / "
            f"移除 {len(changes['removed'])} / "
            f"修改 {len(changes['modified'])}",
            'INFO')

        base_gunpacks = preset_info.get('gunpacks', {})
        new_gunpacks = self._get_gunpacks_from_folder(self.tacz_path)

        files_to_pack = []
        for name in changes['added'] + changes['modified']:
            item = self.tacz_path / name
            if item.exists():
                files_to_pack.append(item)

        increment = preset_info.get('incremental_count', 0) + 1

        metadata = {
            'format': 'pulses_swap_incremental',
            'format_version': 2,
            'preset_name': preset_name,
            'pack_name': self.pack_name,
            'version': preset_info.get('version', 'v1.0.0'),
            'increment': increment,
            'changes': changes,
            'base_gunpacks_index': base_gunpacks,
            'new_gunpacks_index': new_gunpacks,
            'timestamp': datetime.now().isoformat()
        }

        try:
            total = len(files_to_pack) + 1
            processed = 0
            with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_STORED) as zipf:
                zipf.writestr('_increment.json',
                              json.dumps(metadata, indent=2, ensure_ascii=False))
                processed += 1
                if progress_callback:
                    progress_callback(processed, total, "写入元数据")
                for item in files_to_pack:
                    try:
                        if item.is_file():
                            zipf.write(item, item.name)
                        else:
                            for sub in item.rglob('*'):
                                if sub.is_file():
                                    zipf.write(sub, str(sub.relative_to(self.tacz_path)))
                    except Exception as e:
                        self.log.log(f"打包 {item.name} 失败: {e}", 'WARNING')
                    processed += 1
                    if progress_callback:
                        progress_callback(processed, total, f"打包 {item.name}")
                    time.sleep(0.001)

            self.log.log("导出完成，正在同步校验数据...", 'PROCESS')
            preset_info['gunpacks'] = new_gunpacks
            preset_info['incremental_count'] = increment
            preset_path = Path(preset_info['path'])
            index_data = {
                'name': preset_info['name'],
                'version': preset_info.get('version', 'v1.0.0'),
                'gunpacks': new_gunpacks,
                'applied': True,
                'incremental_count': increment
            }
            with open(preset_path / 'index.json', 'w', encoding='utf-8') as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)
            self.save_cache()

            self.log.log(f"增量更新包导出成功: {export_path.name} (迭代 {increment})", 'SUCCESS')
            self.log.log(f"校验数据已同步为最新 ({len(new_gunpacks)} 个枪包)",
                          'SUCCESS', verbose=True)
            if progress_callback:
                progress_callback(total, total, "完成")
            return True
        except Exception as e:
            self.log.log(f"导出增量包失败: {e}", 'ERROR')
            return False

    def import_preset(self, import_path: Path, progress_callback=None) -> bool:
        try:
            temp_dir = Path(tempfile.mkdtemp())
            with zipfile.ZipFile(import_path, 'r') as zipf:
                members = zipf.infolist()
                total = len(members)
                for idx, member in enumerate(members):
                    if member.is_dir():
                        continue
                    try:
                        zipf.extract(member, temp_dir)
                        if progress_callback and idx % 2 == 0:
                            progress_callback(idx + 1, total, f"解压 {member.filename}")
                    except Exception as e:
                        self.log.log(f"解压失败 {member.filename}: {e}", 'WARNING')
                    if idx % 20 == 0:
                        time.sleep(0.001)
            index_file = temp_dir / 'index.json'
            if not index_file.exists():
                self.log.log("导入失败: 缺少index.json", 'ERROR')
                shutil.rmtree(temp_dir)
                return False
            with open(index_file, 'r', encoding='utf-8') as f:
                index_data = json.load(f)
            preset_name = index_data.get('name', import_path.stem)
            raw = index_data.get('gunpacks', {})
            standard = {}
            for name, value in raw.items():
                if isinstance(value, dict):
                    standard[name] = value
                elif isinstance(value, list):
                    standard[name] = {'type': 'zip', 'size': 0, 'file_count': 1,
                                      'hash': str(value[0]) if value else ''}
                else:
                    standard[name] = {'type': 'zip', 'size': 0, 'file_count': 1}
            index_data['gunpacks'] = standard
            index_data['version'] = index_data.get('version',
                                                    index_data.get('description', 'v1.0.0'))
            index_data['incremental_count'] = index_data.get('incremental_count', 0)
            if preset_name in self.presets:
                if not ask_yes_no("确认覆盖", f"预设 '{preset_name}' 已存在，是否覆盖？"):
                    shutil.rmtree(temp_dir)
                    return False
                old_path = Path(self.presets[preset_name]['path'])
                if old_path.exists():
                    shutil.rmtree(old_path)
                del self.presets[preset_name]
            preset_path = self.database_path / preset_name
            if preset_path.exists():
                shutil.rmtree(preset_path)
            shutil.move(str(temp_dir), str(preset_path))
            with open(preset_path / 'index.json', 'w', encoding='utf-8') as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)
            self._load_preset(preset_path)
            gunpacks = self._get_gunpacks_from_folder(preset_path)
            self.presets[preset_name]['gunpacks'] = gunpacks
            index_data['gunpacks'] = gunpacks
            with open(preset_path / 'index.json', 'w', encoding='utf-8') as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)
            self.save_cache()
            if progress_callback:
                progress_callback(100, 100, "完成")
            self.log.log(f"预设 '{preset_name}' 导入成功", 'SUCCESS')
            return True
        except Exception as e:
            self.log.log(f"导入预设失败: {e}", 'ERROR')
            return False

    def import_incremental(self, import_path: Path, progress_callback=None) -> bool:
        try:
            temp_dir = Path(tempfile.mkdtemp())
            with zipfile.ZipFile(import_path, 'r') as zipf:
                for member in zipf.infolist():
                    if member.is_dir():
                        continue
                    try:
                        zipf.extract(member, temp_dir)
                    except Exception as e:
                        self.log.log(f"解压失败 {member.filename}: {e}", 'WARNING')
            meta_file = temp_dir / '_increment.json'
            if not meta_file.exists():
                self.log.log("不是有效的增量更新包（缺少元数据）", 'ERROR')
                shutil.rmtree(temp_dir)
                return False
            with open(meta_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            if metadata.get('format') != 'pulses_swap_incremental':
                self.log.log("不是有效的增量更新包（格式不匹配）", 'ERROR')
                shutil.rmtree(temp_dir)
                return False

            preset_name = metadata.get('preset_name')
            version = metadata.get('version', '')
            increment = metadata.get('increment', 0)
            changes = metadata.get('changes', {})
            new_gunpacks = metadata.get('new_gunpacks_index', {})
            base_gunpacks = metadata.get('base_gunpacks_index')

            if preset_name not in self.presets:
                self.log.log(f"目标预设 '{preset_name}' 不存在", 'ERROR')
                shutil.rmtree(temp_dir)
                return False
            preset_info = self.presets[preset_name]
            if preset_info.get('version', '') != version:
                self.log.log(f"版本不匹配: 本地 '{preset_info.get('version','')}' vs 更新 '{version}'", 'ERROR')
                shutil.rmtree(temp_dir)
                show_error("版本不匹配",
                    f"增量更新包版本与本地不一致：\n\n"
                    f"本地版本: {preset_info.get('version','')}\n"
                    f"更新版本: {version}\n\n"
                    f"请确认您使用的是对应的增量包。")
                return False
            if not preset_info.get('applied', False):
                self.log.log(f"预设 '{preset_name}' 未应用，无法导入增量更新", 'ERROR')
                shutil.rmtree(temp_dir)
                show_error("无法应用",
                    f"预设 '{preset_name}' 当前未应用。\n\n"
                    f"请先切换到该预设后再导入增量更新。")
                return False

            if base_gunpacks:
                self.log.log("正在校验本地枪包与增量包要求的原始状态...", 'PROCESS')
                local_gunpacks = self._get_gunpacks_from_folder(self.tacz_path)
                missing = []
                modified = []
                for name, base_fp in base_gunpacks.items():
                    if name not in local_gunpacks:
                        missing.append(name)
                    elif not fingerprints_match(local_gunpacks[name], base_fp):
                        modified.append(name)

                if missing or modified:
                    self.log.log("增量更新校验失败：本地枪包与增量包要求的原始状态不匹配", 'ERROR')
                    if missing:
                        self.log.log(f"  缺失 {len(missing)} 个枪包（需向管理员请求）:", 'ERROR')
                        for n in missing[:10]:
                            self.log.log(f"    × {n}", 'ERROR')
                        if len(missing) > 10:
                            self.log.log(f"    ... 还有 {len(missing)-10} 个", 'ERROR')
                    if modified:
                        self.log.log(f"  内容已被修改 {len(modified)} 个枪包:", 'ERROR')
                        for n in modified[:10]:
                            self.log.log(f"    ~ {n}", 'ERROR')
                        if len(modified) > 10:
                            self.log.log(f"    ... 还有 {len(modified)-10} 个", 'ERROR')

                    lines = ["增量更新无法应用：本地枪包状态与增量包要求的原始状态不匹配。\n"]
                    if missing:
                        lines.append(f"缺失的枪包（{len(missing)} 个，需向管理员请求）：")
                        for n in missing[:10]:
                            lines.append(f"  × {n}")
                        if len(missing) > 10:
                            lines.append(f"  ... 还有 {len(missing)-10} 个")
                        lines.append("")
                    if modified:
                        lines.append(f"内容已被修改的枪包（{len(modified)} 个）：")
                        for n in modified[:10]:
                            lines.append(f"  ~ {n}")
                        if len(modified) > 10:
                            lines.append(f"  ... 还有 {len(modified)-10} 个")
                        lines.append("")
                    lines.append("请先恢复这些枪包到原始状态后再重试。")

                    shutil.rmtree(temp_dir)
                    show_error("增量更新校验失败", "\n".join(lines))
                    return False
                else:
                    self.log.log("本地枪包与原始状态匹配", 'SUCCESS', verbose=True)
            else:
                self.log.log("提示：此增量包未包含原始校验数据，跳过兼容性校验", 'WARNING')

            added = changes.get('added', [])
            removed = changes.get('removed', [])
            modified = changes.get('modified', [])
            self.log.log(f"增量更新: 新增 {len(added)} / 移除 {len(removed)} / "
                          f"修改 {len(modified)}", 'INFO', verbose=True)

            for name in removed:
                target = self.tacz_path / name
                if target.exists():
                    if self._safe_remove(target):
                        self.log.log(f"已移除 {name}（可在回收站找回）", 'DEBUG')

            for name in added + modified:
                src = temp_dir / name
                if not src.exists():
                    continue
                dst = self.tacz_path / name
                if dst.exists():
                    if dst.is_dir():
                        shutil.rmtree(dst)
                    else:
                        dst.unlink()
                shutil.move(str(src), str(dst))

            if new_gunpacks:
                preset_info['gunpacks'] = new_gunpacks
            else:
                preset_info['gunpacks'] = self._get_gunpacks_from_folder(self.tacz_path)
            preset_info['incremental_count'] = increment
            preset_path = Path(preset_info['path'])
            index_data = {
                'name': preset_info['name'],
                'version': preset_info.get('version', 'v1.0.0'),
                'gunpacks': preset_info['gunpacks'], 'applied': True,
                'incremental_count': increment}
            with open(preset_path / 'index.json', 'w', encoding='utf-8') as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)
            self.save_cache()
            shutil.rmtree(temp_dir, ignore_errors=True)
            self.log.log(f"增量更新导入成功 (迭代 {increment})", 'SUCCESS')
            return True
        except Exception as e:
            self.log.log(f"导入增量包失败: {e}", 'ERROR')
            return False

    def get_current_gunpacks_for_preset(self, preset_name: str, use_cache: bool = True) -> dict:
        if preset_name not in self.presets:
            return {}
        preset_info = self.presets[preset_name]
        if preset_info.get('applied', False):
            if self.tacz_path and self.tacz_path.exists():
                return self._get_gunpacks_from_folder(self.tacz_path)
            return {}
        if use_cache and preset_info.get('gunpacks'):
            return preset_info['gunpacks']
        return self._get_gunpacks_from_folder(Path(preset_info['path']))


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
            font_size=FS_SMALL, bold_active=True, text_anchor="center",
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
                                     border_width=BORDER_W,
                                     border_color=C_BORDER_SOFT)
        self.btn_bar.pack(fill=X, pady=(PAD_GAP, 0))
        self.btn_bar.pack_propagate(False)
        make_button(self.btn_bar, "恢复默认", command=self._reset_defaults,
                     width=100).pack(side=RIGHT, padx=(PAD_TIGHT, PAD_DIALOG),
                                     pady=(H_BTN_BAR - H_CONTROL) // 2)
        self.saved_label = make_label(self.btn_bar, text=self._saved_hint(),
                                       fg=C_TEXT_MUTED, font_size=FS_TINY)
        self.saved_label.pack(side=LEFT, padx=PAD_DIALOG)

        self.reload()
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
            # 点左面的选项卡内容往左走，点右面的往右走
            if old_index >= 0 and new_index >= 0 and new_index > old_index:
                direction = -1
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
                                  border_width=BORDER_W, border_color=C_BORDER_SOFT)
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
            height=2 * (H_NAV + PAD_XS) + 12)
        self.mode_seg.pack(fill=X, padx=PAD_TIGHT, pady=PAD_TIGHT)

        make_label(tab, text="用户身份", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, pady=(0, PAD_TIGHT))
        role_card = ctk.CTkFrame(tab, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                  border_width=BORDER_W, border_color=C_BORDER_SOFT)
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
            height=2 * (H_NAV + PAD_XS) + 12)
        self.role_seg.pack(fill=X, padx=PAD_TIGHT, pady=PAD_TIGHT)

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
                                border_width=BORDER_W, border_color=C_BORDER_SOFT)
        db_card.pack(fill=X, pady=(0, PAD_DIALOG))
        self.db_path_label = make_label(db_card, text="", fg=C_TEXT_MAIN,
                                        font_size=FS_SMALL)
        self.db_path_label.configure(wraplength=620, justify=LEFT, anchor=W)
        self.db_path_label.pack(anchor=W, padx=PAD_CARD_X, pady=PAD_CARD_Y)

        make_label(tab, text="数据库管理", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, pady=(0, PAD_TIGHT))
        db_mgr_card = ctk.CTkFrame(tab, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                    border_width=BORDER_W, border_color=C_BORDER_SOFT)
        db_mgr_card.pack(fill=X, pady=(0, PAD_DIALOG))

        btn_row1 = ctk.CTkFrame(db_mgr_card, fg_color="transparent")
        btn_row1.pack(fill=X, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        make_button(btn_row1, "切换数据库", command=self.on_switch_db).pack(
            side=LEFT, padx=(0, PAD_TIGHT))
        make_button(btn_row1, "合并数据库", command=self.on_merge_db).pack(
            side=LEFT, padx=PAD_TIGHT)
        make_button(btn_row1, "适配旧版数据库", command=self.on_migrate_legacy).pack(
            side=LEFT, padx=PAD_TIGHT)

        btn_row2 = ctk.CTkFrame(db_mgr_card, fg_color="transparent")
        btn_row2.pack(fill=X, padx=PAD_CARD_X, pady=(0, PAD_TIGHT))
        make_button(btn_row2, "打开数据库文件夹", command=self.on_open_db).pack(
            side=LEFT, padx=(0, PAD_TIGHT))
        make_button(btn_row2, "强制更新校验数据",
                     command=self.app.force_update_validation).pack(
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
                                  border_width=BORDER_W, border_color=C_BORDER_SOFT)
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
                              self.settings.role)):
                if seg is not None and seg.current() != key:
                    seg.select(key, animate=False)
        except Exception:
            pass
        self._update_db_labels()
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
                os.startfile(str(db))
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
            self.saved_label.configure(text="✓ 已自动保存",
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
                  on_done=self._reset_saved_text, easing=ease_in_out_cubic)

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


# ==================== 主窗口 ====================
class PulsesSwapApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{PROJECT_NAME} v{VERSION}")
        self.root.geometry(f"{WINDOW_W}x{WINDOW_H}")
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

        self.setup_ui()
        self.setup_menu()

        self.root.after(80, self._disable_win11_transparency)
        self.root.after(150, self._init_database_flow)

    def _disable_win11_transparency(self):
        if not IS_WINDOWS:
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if not hwnd:
                hwnd = self.root.winfo_id()
            v0 = ctypes.c_int(0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 38, ctypes.byref(v0), ctypes.sizeof(v0))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(v0), ctypes.sizeof(v0))
            # 33 = DWMWA_WINDOW_CORNER_PREFERENCE：按设计令牌给窗口圆角
            v1 = ctypes.c_int(DWM_CORNER_PREF)
            try:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, 33, ctypes.byref(v1), ctypes.sizeof(v1))
            except Exception:
                pass
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
        main_frame.grid_columnconfigure(0, weight=0, minsize=SIDEBAR_W)
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

        # 导航项用 Canvas 自绘：选中滑块可以逐帧滑到目标项，图标各自带动效
        # （主界面=轻跳、设置=齿轮转 45°、日志=轻摆，见 CanvasSegmented）
        nav_items = (("home", "@home", "主界面", "hop"),
                     ("settings", "@gear", "设置", "rotate"),
                     ("log", "@log", "日志", "wobble"))
        nav_height = len(nav_items) * (H_NAV + PAD_XS) + 2 * PAD_XS
        self.nav = CanvasSegmented(
            sidebar, nav_items, command=self.show_page,
            orientation="vertical", item_height=H_NAV, pad=4, gap=PAD_XS,
            radius=R_CONTROL, bg_color=C_CARD_BG, pill_color=C_ACCENT_SOFT,
            hover_color=C_ACCENT_SOFT, text_color=C_TEXT_MAIN,
            active_text_color=C_ACCENT, font_size=FS_BODY, bold_active=True,
            text_anchor="w", text_pad=14, icon_pad=11, icon_half=9,
            icon_gap=8, icon_angle=45.0, duration_ms=240, height=nav_height)
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
        item = self.stack.items.get(self.active_page)
        if item is not None:
            def frame(e, raw):
                try:
                    self.stack.canvas.coords(item, lerp(56.0, 0.0, e), 0)
                except Exception:
                    pass

            frame(0.0, 0.0)
            tween(self.stack.canvas, "entrance", 460, frame,
                  easing=ease_out_quint)
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
                if (self.PAGE_ORDER.index(name)
                        > self.PAGE_ORDER.index(previous)):
                    direction = -1
            except ValueError:
                direction = 1
        self.active_page = name
        self._update_nav_state(name, animate=animate)
        self.stack.show(name, animate=animate, direction=direction, axis="y")
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
        page.grid_columnconfigure(0, weight=0, minsize=LEFT_COL_W)
        page.grid_columnconfigure(1, weight=1)

        left_panel = ctk.CTkFrame(page, fg_color="transparent")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, PAD_GAP))
        # 纵向预算：Step1/Step3 固定高度，剩余空间全部给 Step2 的预设列表，
        # 这样窗口变小/DPI 放大时先压缩列表，Step3 卡片不会被裁（见 H_STEP*_MIN）
        left_panel.grid_columnconfigure(0, weight=1)
        left_panel.grid_rowconfigure(0, weight=0, minsize=H_STEP1_MIN)
        left_panel.grid_rowconfigure(1, weight=1, minsize=H_STEP2_MIN)
        left_panel.grid_rowconfigure(2, weight=0, minsize=H_STEP3_MIN)

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
            text_color=C_TEXT_SECONDARY, font=(FONT_FAMILY, FS_BODY),
            justify=LEFT, anchor="w", fg_color="transparent")
        self.pack_drop_label.pack(fill=X, padx=PAD_GAP, pady=(PAD_GAP, PAD_XS))

        # 路径显示
        self.pack_path_frame, self.pack_path_label = make_display_box(
            self.pack_drop_area, text="未选择", height=H_CONTROL)
        self.pack_path_frame.pack(fill=X, padx=PAD_GAP, pady=(0, PAD_TIGHT))

        # 按钮行
        pack_btn_row = ctk.CTkFrame(self.pack_drop_area, fg_color="transparent")
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

        # 最近打开（折叠）：外层 wrap 固定高度，展开/收起用高度补间驱动
        self.recent_wrap = ctk.CTkFrame(pack_content, fg_color="transparent",
                                         height=1)
        self.recent_wrap.pack(fill=X)
        self.recent_wrap.pack_propagate(False)
        self.recent_frame = ctk.CTkFrame(self.recent_wrap, fg_color=C_PANEL_ALT_BG,
                                          corner_radius=R_CONTROL, border_width=BORDER_W,
                                          border_color=C_BORDER_SOFT)
        self.recent_listbox = Listbox(self.recent_frame, height=5,
                                       bg=C_PANEL_ALT_BG, fg=C_TEXT_MAIN,
                                       selectbackground=C_ACCENT_SOFT,
                                       selectforeground=C_ACCENT,
                                       relief='flat', highlightthickness=0,
                                       font=(FONT_FAMILY, FS_SMALL))
        self.recent_listbox.pack(fill=BOTH, expand=True, padx=PAD_TIGHT, pady=PAD_TIGHT)
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
        self.preset_listbox = Listbox(preset_list_wrap, height=6,
                                       bg=C_CARD_BG, fg=C_TEXT_MAIN,
                                       selectbackground=C_ACCENT_SOFT,
                                       selectforeground=C_ACCENT,
                                       relief='flat', highlightthickness=0,
                                       font=(FONT_FAMILY, FS_BODY))
        self.preset_listbox.pack(fill=BOTH, expand=True, padx=PAD_XS, pady=PAD_XS)
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
            text_color=C_TEXT_SECONDARY, font=(FONT_FAMILY, FS_TINY),
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
        self.gunpack_listbox = Listbox(gunpack_list_wrap, height=10,
                                        bg=C_CARD_BG, fg=C_TEXT_MAIN,
                                        selectbackground=C_ACCENT_SOFT,
                                        selectforeground=C_ACCENT,
                                        relief='flat', highlightthickness=0,
                                        font=(FONT_FAMILY, FS_BODY))
        self.gunpack_listbox.pack(fill=BOTH, expand=True, padx=PAD_XS, pady=PAD_XS)

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
                os.startfile(str(self.current_pack_path))
                self.log_manager.log(f"已打开整合包路径: {self.current_pack_path}",
                                      'INFO', verbose=True)
            else:
                show_error("错误", f"路径不存在: {self.current_pack_path}")
        except Exception as e:
            self.log_manager.log(f"打开整合包路径失败: {e}", 'ERROR')
            show_error("错误", f"打开失败: {e}")

    def open_tacz_folder(self):
        if not self.tacz_path:
            show_warning("提示", "请先选择一个整合包")
            return
        if not self.tacz_path.exists():
            show_error("错误", f"TACZ 路径不存在: {self.tacz_path}")
            return
        try:
            os.startfile(str(self.tacz_path))
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
                self.root.after(0, lambda p=pct: self.progress_bar.set(p))
                self.root.after(0, lambda m=m, c=c, t=t: self.progress_label.configure(
                    text=f"{m} ({c}/{t})"))
            # 只处理重绘空闲任务：原来用 update() 会连带处理用户事件，
            # 拖拽窗口大小时每个进度回调都会重入一次完整事件循环，明显卡顿
            self.root.after(0, lambda: self.root.update_idletasks())

        def worker():
            try:
                stats = LegacyDatabaseMigrator.migrate_legacy_to_new(
                    legacy_path, dst, self.log_manager,
                    conflict_mode='rename',
                    progress_callback=progress_cb,
                    after_migrate=after_mode)
                self.root.after(0, self._on_migrate_finished, stats, after_mode)
            except Exception as e:
                self.log_manager.log(f"适配旧库出错: {e}", 'ERROR')
                self.root.after(0, self._on_migrate_finished,
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
                                        font=(FONT_FAMILY, FS_SMALL),
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
                                        font=(FONT_FAMILY, FS_SMALL),
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
                                text_color=C_TEXT_MAIN, font=(FONT_FAMILY, FS_SMALL),
                                fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER,
                                border_color=C_BORDER)
        check.pack(anchor=W, pady=(PAD_XS, PAD_GAP))
        card.register_focusable(check)

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill=X, side=BOTTOM, pady=(PAD_GAP, 0))

        def on_ok():
            if dont_remind_var.get():
                self.dont_remind_this_session = True
            card.close('ok')

        def on_export():
            if dont_remind_var.get():
                self.dont_remind_this_session = True
            card.close('export')

        if self.settings.role == "developer":
            export_btn = make_button(btn_frame, "导出增量更新", command=on_export,
                                      accent=True)
            export_btn.pack(side=RIGHT, padx=PAD_XS)
            card.register_focusable(export_btn)
        ok_btn = make_button(btn_frame, "确定", command=on_ok)
        ok_btn.pack(side=RIGHT)
        card.register_focusable(ok_btn)
        return card.wait()

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
                self.recent_wrap.configure(height=max(1, int(self._recent_height)))
            except Exception:
                pass

        def done():
            self._recent_height = float(target)
            try:
                self.recent_wrap.configure(height=max(1, int(target)))
            except Exception:
                pass
            if hide_after:
                try:
                    self.recent_frame.pack_forget()
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
            self.log_manager.log(f"加载预设失败: {e}", 'ERROR')
        finally:
            self.root.after(0, self._on_presets_loaded)

    def _on_presets_loaded(self):
        self.loading_presets = False
        self._stop_loading_dots()
        self._disable_buttons(False)
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
                    if self.preset_listbox.get(i) == first:
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

    # ==================== 加载指示动画 ====================
    def _start_loading_dots(self, prefix="刷新中"):
        """加载文字脉冲：小圆点逐帧增长，替代静态的「...」。"""
        def frame(e, raw):
            dots = "." * min(3, int(raw * 4))
            try:
                self.loading_label.configure(text=f"{prefix}{dots}")
            except Exception:
                pass

        frame(0.0, 0.0)
        tween(self.loading_label, "dots", 560, frame,
              on_done=lambda: self._start_loading_dots(prefix),
              easing=ease_linear)

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
        tween(label, "color", duration, frame, easing=ease_out_cubic)

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
        self.open_pack_btn.configure(state="disabled")
        self.open_tacz_btn.configure(state="disabled")
        self._disable_buttons(True)
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
            self.root.after(0, self._do_tacz_refresh)
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
            self.preset_listbox.insert(END, name)
            if info.get('applied', False):
                idx = self.preset_listbox.size() - 1
                self.preset_listbox.itemconfig(idx, bg=C_ACCENT_SOFT, fg=C_ACCENT)
        if self.preset_manager.current_preset:
            self.pack_name_label.configure(text=f"当前预设: {self.preset_manager.current_preset}")
        else:
            self.pack_name_label.configure(text="当前预设: 无")
        if self.current_selected_preset:
            for i in range(self.preset_listbox.size()):
                if self.preset_listbox.get(i) == self.current_selected_preset:
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
            self.root.after(0, self._on_refresh_presets_done)

    def _on_refresh_presets_done(self):
        self.loading_presets = False
        self._stop_loading_dots()
        self._disable_buttons(False)
        self._update_preset_list()
        self.log_manager.log("预设列表刷新完成", 'INFO', verbose=True)
        self._update_guide()

    def on_preset_selected(self, event):
        if not self.preset_manager or self.loading_presets:
            return
        sel = self.preset_listbox.curselection()
        if not sel:
            return
        name = self.preset_listbox.get(sel[0])
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
        name = self.preset_listbox.get(idx)
        info = self.preset_manager.presets.get(name)
        if not info:
            return
        self.preset_listbox.selection_clear(0, END)
        self.preset_listbox.selection_set(idx)
        self.on_preset_selected(None)
        menu = Menu(self.root, tearoff=0, bg=C_PANEL_BG, fg=C_TEXT_MAIN,
                    activebackground=C_ACCENT_SOFT, activeforeground=C_ACCENT,
                    font=(FONT_FAMILY, FS_SMALL))
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

                self.root.after(0, self._on_migrate_preset_finished,
                                True, preset_name, target_db, src_removed)
            except Exception as e:
                self.log_manager.log(f"迁移预设失败: {e}", 'ERROR')
                self.root.after(0, self._on_migrate_preset_finished,
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
                                         font=(FONT_FAMILY, FS_SMALL),
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
                                       font=(FONT_FAMILY, FS_SMALL),
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
                    if self.preset_listbox.get(i) == new_name:
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
                os.startfile(str(path))
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
                self.root.after(0, self._on_export_finished, ok, export_path)
            except Exception as e:
                self.log_manager.log(f"导出错误: {e}", 'ERROR')
                self.root.after(0, self._on_export_finished, False, export_path)
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
                self.root.after(0, self._on_export_inc_finished, ok, export_path)
            except Exception as e:
                self.log_manager.log(f"导出增量包错误: {e}", 'ERROR')
                self.root.after(0, self._on_export_inc_finished, False, export_path)
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
                self.root.after(0, self._on_import_finished, ok, import_path)
            except Exception as e:
                self.log_manager.log(f"导入错误: {e}", 'ERROR')
                self.root.after(0, self._on_import_finished, False, import_path)
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
                self.root.after(0, self._on_import_inc_finished, ok, import_path)
            except Exception as e:
                self.log_manager.log(f"导入增量包错误: {e}", 'ERROR')
                self.root.after(0, self._on_import_inc_finished, False, import_path)
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
            self.root.after(0, lambda: self._animate_progress(pct))
            self.root.after(0, lambda: self.progress_label.configure(
                text=f"{message} ({current}/{total})"))
        self.root.after(0, lambda: self.root.update_idletasks())

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
        self.root.after(0, lambda: self.progress_bar.pack_forget())
        self.root.after(0, lambda: self.progress_label.pack_forget())
        self.root.after(0, lambda: setattr(self, "_progress_value", 0.0))
        self.root.after(0, lambda: self.root.update_idletasks())

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
                self.root.after(0, self._on_apply_finished, result)
            except Exception as e:
                self.log_manager.log(f"错误: {e}", 'ERROR')
                self.root.after(0, self._on_apply_finished, False)
        threading.Thread(target=worker, daemon=True).start()

    def _on_apply_finished(self, success):
        self.hide_progress()
        self.set_busy_state(False, "")
        if success:
            self._update_preset_list()
            self.refresh_gunpacks(use_cache=False)
            if self.preset_manager and self.preset_manager.current_preset:
                for i in range(self.preset_listbox.size()):
                    if self.preset_listbox.get(i) == self.preset_manager.current_preset:
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
            os.startfile(str(self.preset_manager.database_path))
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
            v0 = ctypes.c_int(0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 38, ctypes.byref(v0), ctypes.sizeof(v0))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(v0), ctypes.sizeof(v0))
            # 33 = DWMWA_WINDOW_CORNER_PREFERENCE：按设计令牌给窗口圆角
            v1 = ctypes.c_int(DWM_CORNER_PREF)
            try:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, 33, ctypes.byref(v1), ctypes.sizeof(v1))
            except Exception:
                pass
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