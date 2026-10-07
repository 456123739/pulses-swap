"""
Pulses Swap - 快速枪包切换器
作者: NimShade
版本: 2.1
描述: Minecraft Tacz 模组枪包快速切换工具
UI风格: Pulses 水墨淡色主题（customtkinter 圆角版本）

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
from tkinter import filedialog, messagebox

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
VERSION = "2.1"
AUTHOR = "NimShade"
PROJECT_NAME = "Pulses Swap"

if getattr(sys, 'frozen', False):
    PROGRAM_DIR = Path(sys.executable).parent
else:
    PROGRAM_DIR = Path(__file__).parent

BOOTSTRAP_FILE = PROGRAM_DIR / "PulsesSwap_config.json"
DEFAULT_DB_DIR = PROGRAM_DIR / "PulsesSwap_database"

IS_WINDOWS = sys.platform.startswith('win')

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
H_LOG_BOX   = 132  # 日志文本框高度（原 120）
H_PROGRESS  = 8    # 进度条高度
H_BTN_BAR   = 68   # 对话框底部按钮条高度（原 64）
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

LEFT_COL_W = 340   # 主窗口左栏宽度（与宣传片布局一致）

WINDOW_W, WINDOW_H = 1150, 760             # 主窗口（与宣传片一致）
WINDOW_MIN_W, WINDOW_MIN_H = 1000, 700     # 主窗口最小尺寸

# 固定尺寸对话框 (宽, 高)：字号放大后需同步留足按钮行宽度
DLG_LOCATOR  = (680, 520)   # 数据库定位（含 4 个长文本按钮，原 580x500）
DLG_SETTINGS = (560, 800)   # 设置（可滚动，原 540x780）
DLG_CHOICE   = (540, 380)   # 迁移后处理 / 身份提示 / 冲突处理（原 480~520x320~340）
DLG_SMALL    = (520, 340)   # 迁移预设（原 480x300）


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


# ==================== 控件工厂 ====================
def make_button(parent, text, command=None, width=None, state="normal", accent=False):
    kwargs = dict(
        text=text, command=command,
        fg_color=C_ACCENT if accent else C_PANEL_ALT_BG,
        hover_color=C_ACCENT_HOVER if accent else C_ACCENT_SOFT,
        text_color=C_TEXT_INVERSE if accent else C_TEXT_MAIN,
        border_color=C_ACCENT if accent else C_BORDER_SOFT,
        border_width=BORDER_W, corner_radius=R_CONTROL,
        font=(FONT_FAMILY, FS_BODY), height=H_CONTROL, state=state)
    if width is not None:
        kwargs['width'] = width
    return ctk.CTkButton(parent, **kwargs)


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


def make_label(parent, text="", fg=None, bg=None, font_size=FS_BODY, bold=False):
    if fg is None:
        fg = C_TEXT_MAIN
    weight = "bold" if bold else "normal"
    kwargs = dict(text=text, text_color=fg,
                  font=(FONT_FAMILY, font_size, weight),
                  anchor="w")
    kwargs['fg_color'] = bg if bg is not None else "transparent"
    return ctk.CTkLabel(parent, **kwargs)


# ==================== 数据库定位 ====================
class DatabaseLocator:
    @staticmethod
    def load_db_path() -> Path | None:
        if BOOTSTRAP_FILE.exists():
            try:
                with open(BOOTSTRAP_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                path = data.get('database_path')
                if path:
                    return Path(path)
            except Exception:
                pass
        return None

    @staticmethod
    def save_db_path(path: Path):
        try:
            with open(BOOTSTRAP_FILE, 'w', encoding='utf-8') as f:
                json.dump({'database_path': str(path)}, f,
                          indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存数据库位置失败: {e}")

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
    def init_database(path: Path) -> bool:
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
            return True
        except Exception as e:
            print(f"初始化数据库失败: {e}")
            return False


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
        dlg_w, dlg_h = DLG_LOCATOR
        dialog = ctk.CTkToplevel(self.parent)
        dialog.title("初始化 Pulses Swap")
        dialog.geometry(f"{dlg_w}x{dlg_h}")
        dialog.resizable(False, False)
        dialog.transient(self.parent)
        dialog.grab_set()
        dialog.configure(fg_color=C_WINDOW_BG)
        try:
            dialog.attributes('-alpha', 1.0)
            dialog.attributes('-transparentcolor', '')
        except Exception:
            pass

        dialog.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() - dlg_w) // 2
        y = self.parent.winfo_y() + (self.parent.winfo_height() - dlg_h) // 2
        dialog.geometry(f"+{x}+{y}")

        frame = ctk.CTkFrame(dialog, fg_color="transparent")
        frame.pack(fill=BOTH, expand=True, padx=PAD_DIALOG, pady=PAD_DIALOG)

        make_label(frame, text="欢迎使用 Pulses Swap",
                    fg=C_ACCENT, font_size=FS_TITLE, bold=True).pack(
                        anchor=W, pady=(0, PAD_TIGHT))
        make_label(frame, text="Step 1 · 选择数据库位置",
                    fg=C_GUIDE_GLOW, font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, pady=(0, PAD_INNER))

        desc = make_label(frame,
            text="首次启动需要指定数据库位置。\n"
                 "数据库用于保存预设、校验数据和程序设置。\n\n"
                 "• 新用户 → 点「✨ 新建数据库」或「使用默认位置」\n"
                 "• 已有 Pulses Swap 数据库 → 点「📂 定位已有数据库」\n"
                 "• 有旧版 FGC_database → 点「📦 适配旧版数据库」",
            fg=C_TEXT_SECONDARY, font_size=FS_BODY)
        desc.configure(wraplength=dlg_w - 2 * PAD_DIALOG - 6, justify=LEFT, anchor=W)
        desc.pack(anchor=W, fill=X, pady=(0, PAD_DIALOG))

        loc_frame = ctk.CTkFrame(frame, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                   border_width=BORDER_W, border_color=C_BORDER_SOFT)
        loc_frame.pack(fill=X, pady=(0, PAD_DIALOG))

        make_label(loc_frame, text="默认数据库位置（与程序同目录）:",
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

        def on_existing():
            folder = filedialog.askdirectory(
                title="选择已有的数据库文件夹",
                initialdir=str(PROGRAM_DIR),
                parent=dialog)
            if not folder:
                return
            path = Path(folder)
            if LegacyDatabaseMigrator.is_legacy_database(path):
                if messagebox.askyesno("检测到旧版数据库",
                    "该文件夹是旧版 FGC_database。\n\n"
                    "是否先适配为新版数据库？", parent=dialog):
                    if DatabaseLocator.init_database(DEFAULT_DB_DIR):
                        self.result = DEFAULT_DB_DIR
                        self.legacy_to_migrate = path
                        dialog.destroy()
                return
            if DatabaseLocator.is_valid_database(path):
                self.result = path
                dialog.destroy()
            else:
                messagebox.showerror("错误",
                    "所选文件夹不是有效的数据库。\n\n"
                    "有效的数据库应包含 .settings.json 或预设子文件夹。",
                    parent=dialog)

        def on_legacy():
            folder = filedialog.askdirectory(
                title="选择旧版 FGC_database 文件夹",
                initialdir=str(PROGRAM_DIR),
                parent=dialog)
            if not folder:
                return
            path = Path(folder)
            if not LegacyDatabaseMigrator.is_legacy_database(path):
                if (path / LEGACY_MIGRATED_MARKER).exists():
                    messagebox.showinfo("已迁移",
                        "该旧版数据库已被标记为「已迁移」。\n\n"
                        "如需重新适配，请手动删除旧库根目录下的\n"
                        f"{LEGACY_MIGRATED_MARKER} 文件后再试。",
                        parent=dialog)
                else:
                    messagebox.showerror("错误",
                        "所选文件夹不是旧版 FGC_database。\n\n"
                        "旧版数据库应包含预设子文件夹和 index.json。",
                        parent=dialog)
                return
            if DatabaseLocator.init_database(DEFAULT_DB_DIR):
                self.result = DEFAULT_DB_DIR
                self.legacy_to_migrate = path
                dialog.destroy()

        def on_new():
            # 默认在程序目录下新建
            if messagebox.askyesno("新建数据库",
                f"是否在程序目录下新建数据库？\n\n"
                f"位置: {DEFAULT_DB_DIR}\n\n"
                f"选「否」可手动选择其他文件夹。",
                parent=dialog):
                path = DEFAULT_DB_DIR
            else:
                folder = filedialog.askdirectory(
                    title="选择用于新建数据库的文件夹",
                    initialdir=str(PROGRAM_DIR),
                    parent=dialog)
                if not folder:
                    return
                path = Path(folder)
            if path.exists() and not DatabaseLocator.is_empty_folder(path):
                if DatabaseLocator.is_valid_database(path):
                    self.result = path
                    dialog.destroy()
                    return
                messagebox.showerror("错误",
                    "所选文件夹非空且不是有效数据库。\n\n"
                    "请选择一个空文件夹用于新建数据库。",
                    parent=dialog)
                return
            if DatabaseLocator.init_database(path):
                self.result = path
                dialog.destroy()
            else:
                messagebox.showerror("错误", "创建数据库失败", parent=dialog)

        def on_default():
            if DatabaseLocator.init_database(DEFAULT_DB_DIR):
                self.result = DEFAULT_DB_DIR
                dialog.destroy()
            else:
                messagebox.showerror("错误", "创建默认数据库失败", parent=dialog)

        b_exist = make_button(btn_frame, "📂 定位已有数据库", command=on_existing)
        b_exist.pack(side=LEFT, padx=(0, PAD_TIGHT))
        b_legacy = make_button(btn_frame, "📦 适配旧版数据库", command=on_legacy)
        b_legacy.pack(side=LEFT, padx=PAD_TIGHT)
        b_new = make_button(btn_frame, "✨ 新建数据库", command=on_new, accent=True)
        b_new.pack(side=LEFT, padx=PAD_TIGHT)
        b_default = make_button(btn_frame, "使用默认位置", command=on_default)
        b_default.pack(side=LEFT, padx=PAD_TIGHT)

        btn_refs = {
            'exist': b_exist, 'legacy': b_legacy,
            'new': b_new, 'default': b_default,
        }
        _highlight('new')

        self.parent.wait_window(dialog)
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
    def __init__(self, text_widget, root):
        self.text_widget = text_widget
        self.root = root
        self.full_log = []
        self.show_full = False
        try:
            inner = text_widget._textbox
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

    def log(self, message: str, level: str = 'INFO'):
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_line = f"[{timestamp}] [{level}] {message}\n"
        self.full_log.append((log_line, level))
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

    def _update_display(self):
        try:
            self.text_widget.delete("1.0", END)
            if self.show_full:
                for log_line, level in self.full_log:
                    self._insert_log(log_line, level)
            else:
                if self.full_log:
                    log_line, level = self.full_log[-1]
                    self._insert_log(log_line, level)
            self.text_widget.see(END)
        except Exception:
            pass

    def _insert_log(self, log_line: str, level: str):
        try:
            inner = self.text_widget._textbox
            end = log_line.find(']') + 1
            inner.insert(END, log_line[:end], 'timestamp')
            inner.insert(END, log_line[end:], level)
        except Exception:
            try:
                self.text_widget.insert(END, log_line)
            except Exception:
                pass

    def clear(self):
        self.full_log.clear()
        try:
            self.text_widget.delete("1.0", END)
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
            widget.configure(border_color=color, border_width=width)
        except Exception:
            pass

    def _restore_all(self):
        for wid, saved in list(self._originals.items()):
            try:
                w = saved['widget']
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
                self.log.log(f"已启动 TACZ 监控: {self.tacz_path}", 'INFO')
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
            self.log.log("已停止 TACZ 监控", 'INFO')
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
            self.log.log(f"从缓存加载预设成功，共 {len(self.presets)} 个预设", 'SUCCESS')
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
        self.log.log(f"预设加载完成，共 {len(self.presets)} 个预设", 'INFO')
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
                self.log.log(f"预设 '{preset_path.name}' 已自动适配为新格式", 'INFO')

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
                self.log.log(f"已回收 {moved} 个枪包到 '{current_applied}'", 'INFO')
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
                self.log.log(f"从Tacz读取到 {len(gunpacks)} 个枪包", 'INFO')
            else:
                gunpacks = self._get_gunpacks_from_folder(preset_path)
                self.log.log(f"从预设 '{preset_name}' 读取到 {len(gunpacks)} 个枪包", 'INFO')
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
            self.log.log(f"预设 '{preset_name}' 已应用，从 TACZ 读取枪包内容", 'INFO')
        else:
            source_path = preset_path
            self.log.log(f"从预设文件夹读取导出内容: {preset_name}", 'INFO')

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
            self.log.log(f"校验数据已同步为最新 ({len(new_gunpacks)} 个枪包)", 'SUCCESS')
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
                if not messagebox.askyesno("确认覆盖", f"预设 '{preset_name}' 已存在，是否覆盖？"):
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
                messagebox.showerror("版本不匹配",
                    f"增量更新包版本与本地不一致：\n\n"
                    f"本地版本: {preset_info.get('version','')}\n"
                    f"更新版本: {version}\n\n"
                    f"请确认您使用的是对应的增量包。")
                return False
            if not preset_info.get('applied', False):
                self.log.log(f"预设 '{preset_name}' 未应用，无法导入增量更新", 'ERROR')
                shutil.rmtree(temp_dir)
                messagebox.showerror("无法应用",
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
                    self.log.log("❌ 增量更新校验失败：本地枪包与增量包要求的原始状态不匹配", 'ERROR')
                    if missing:
                        self.log.log(f"  缺失 {len(missing)} 个枪包（需向管理员请求）:", 'ERROR')
                        for n in missing[:10]:
                            self.log.log(f"    ✖ {n}", 'ERROR')
                        if len(missing) > 10:
                            self.log.log(f"    ... 还有 {len(missing)-10} 个", 'ERROR')
                    if modified:
                        self.log.log(f"  内容已被修改 {len(modified)} 个枪包:", 'ERROR')
                        for n in modified[:10]:
                            self.log.log(f"    ⚡ {n}", 'ERROR')
                        if len(modified) > 10:
                            self.log.log(f"    ... 还有 {len(modified)-10} 个", 'ERROR')

                    lines = ["增量更新无法应用：本地枪包状态与增量包要求的原始状态不匹配。\n"]
                    if missing:
                        lines.append(f"缺失的枪包（{len(missing)} 个，需向管理员请求）：")
                        for n in missing[:10]:
                            lines.append(f"  ✖ {n}")
                        if len(missing) > 10:
                            lines.append(f"  ... 还有 {len(missing)-10} 个")
                        lines.append("")
                    if modified:
                        lines.append(f"内容已被修改的枪包（{len(modified)} 个）：")
                        for n in modified[:10]:
                            lines.append(f"  ⚡ {n}")
                        if len(modified) > 10:
                            lines.append(f"  ... 还有 {len(modified)-10} 个")
                        lines.append("")
                    lines.append("请先恢复这些枪包到原始状态后再重试。")

                    shutil.rmtree(temp_dir)
                    messagebox.showerror("增量更新校验失败", "\n".join(lines))
                    return False
                else:
                    self.log.log("✅ 本地枪包与原始状态匹配", 'SUCCESS')
            else:
                self.log.log("提示：此增量包未包含原始校验数据，跳过兼容性校验", 'WARNING')

            added = changes.get('added', [])
            removed = changes.get('removed', [])
            modified = changes.get('modified', [])
            self.log.log(f"增量更新: 新增 {len(added)} / 移除 {len(removed)} / 修改 {len(modified)}", 'INFO')

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
class SettingsDialog:
    def __init__(self, parent, settings: AppSettings, on_save_callback=None,
                 on_db_action=None):
        self.parent = parent
        self.settings = settings
        self.on_save_callback = on_save_callback
        self.on_db_action = on_db_action

        self.dialog = ctk.CTkToplevel(parent)
        self.dialog.title("设置")
        dlg_w, dlg_h = DLG_SETTINGS
        self.dialog.geometry(f"{dlg_w}x{dlg_h}")
        self.dialog.minsize(dlg_w - 60, 620)
        self.dialog.resizable(True, True)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.configure(fg_color=C_WINDOW_BG)
        try:
            self.dialog.attributes('-alpha', 1.0)
            self.dialog.attributes('-transparentcolor', '')
        except Exception:
            pass

        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - dlg_w) // 2
        y = parent.winfo_y() + (parent.winfo_height() - dlg_h) // 2
        self.dialog.geometry(f"+{x}+{y}")

        self.dialog.grid_rowconfigure(0, weight=1)
        self.dialog.grid_columnconfigure(0, weight=1)

        content = ctk.CTkScrollableFrame(
            self.dialog, fg_color=C_WINDOW_BG, corner_radius=0,
            scrollbar_button_color=C_BORDER_SOFT,
            scrollbar_button_hover_color=C_ACCENT)
        content.grid(row=0, column=0, sticky="nsew")

        inner = ctk.CTkFrame(content, fg_color="transparent")
        inner.pack(fill=BOTH, expand=True, padx=PAD_DIALOG, pady=PAD_DIALOG)

        make_label(inner, text="数据库位置", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, pady=(0, PAD_TIGHT))
        db_card = ctk.CTkFrame(inner, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                border_width=BORDER_W, border_color=C_BORDER_SOFT)
        db_card.pack(fill=X, pady=(0, PAD_DIALOG))
        db_str = str(self.settings._settings_file.parent) if self.settings._settings_file else "未绑定"
        dl = make_label(db_card, text=db_str, fg=C_TEXT_MAIN, font_size=FS_SMALL)
        dl.configure(wraplength=dlg_w - 2 * PAD_DIALOG - 2 * PAD_CARD_X)
        dl.pack(anchor=W, padx=PAD_CARD_X, pady=PAD_CARD_Y)

        make_label(inner, text="数据库存储模式", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, pady=(0, PAD_TIGHT))
        mode_card = ctk.CTkFrame(inner, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                  border_width=BORDER_W, border_color=C_BORDER_SOFT)
        mode_card.pack(fill=X, pady=(0, PAD_DIALOG))

        self.storage_var = StringVar(value=settings.storage_mode)
        ctk.CTkRadioButton(mode_card, text="隔离存储（推荐，每个整合包独立预设）",
                            variable=self.storage_var, value="isolated",
                            text_color=C_TEXT_MAIN, font=(FONT_FAMILY, FS_SMALL),
                            fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER,
                            border_color=C_BORDER).pack(
                                anchor=W, padx=PAD_CARD_X,
                                pady=(PAD_CARD_Y, PAD_MICRO))
        make_label(mode_card, text="  数据库保存在各整合包目录下，避免文件重名",
                    fg=C_TEXT_MUTED, font_size=FS_TINY).pack(
                        anchor=W, padx=PAD_INDENT, pady=(0, PAD_TIGHT))
        ctk.CTkRadioButton(mode_card, text="合并存储（所有整合包共用预设）",
                            variable=self.storage_var, value="merged",
                            text_color=C_TEXT_MAIN, font=(FONT_FAMILY, FS_SMALL),
                            fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER,
                            border_color=C_BORDER).pack(
                                anchor=W, padx=PAD_CARD_X,
                                pady=(PAD_TIGHT, PAD_MICRO))
        make_label(mode_card, text="  数据库保存在指定位置，所有整合包共享预设列表\n"
                                    "  ⚠ 不同整合包的同名枪包可能互相覆盖",
                    fg=C_TEXT_MUTED, font_size=FS_TINY, justify=LEFT).pack(
                        anchor=W, padx=PAD_INDENT, pady=(0, PAD_CARD_Y))

        make_label(inner, text="用户身份", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, pady=(0, PAD_TIGHT))
        role_card = ctk.CTkFrame(inner, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                  border_width=BORDER_W, border_color=C_BORDER_SOFT)
        role_card.pack(fill=X, pady=(0, PAD_DIALOG))

        self.role_var = StringVar(value=settings.role)
        ctk.CTkRadioButton(role_card, text="玩家（默认）",
                            variable=self.role_var, value="player",
                            text_color=C_TEXT_MAIN, font=(FONT_FAMILY, FS_SMALL),
                            fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER,
                            border_color=C_BORDER).pack(
                                anchor=W, padx=PAD_CARD_X,
                                pady=(PAD_CARD_Y, PAD_MICRO))
        make_label(role_card, text="  检测到变更时提示检查枪包",
                    fg=C_TEXT_MUTED, font_size=FS_TINY).pack(
                        anchor=W, padx=PAD_INDENT, pady=(0, PAD_TIGHT))
        ctk.CTkRadioButton(role_card, text="开发者",
                            variable=self.role_var, value="developer",
                            text_color=C_TEXT_MAIN, font=(FONT_FAMILY, FS_SMALL),
                            fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER,
                            border_color=C_BORDER).pack(
                                anchor=W, padx=PAD_CARD_X,
                                pady=(PAD_TIGHT, PAD_MICRO))
        make_label(role_card, text="  检测到变更时提示导出增量更新",
                    fg=C_TEXT_MUTED, font_size=FS_TINY).pack(
                        anchor=W, padx=PAD_INDENT, pady=(0, PAD_CARD_Y))

        make_label(inner, text="数据库管理", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, pady=(0, PAD_TIGHT))
        db_mgr_card = ctk.CTkFrame(inner, fg_color=C_CARD_BG, corner_radius=R_CARD,
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
        btn_row2.pack(fill=X, padx=PAD_CARD_X, pady=(0, PAD_CARD_Y))
        make_button(btn_row2, "打开数据库文件夹", command=self.on_open_db).pack(
            side=LEFT, padx=(0, PAD_TIGHT))
        make_label(db_mgr_card,
            text="提示：右键预设可迁移到其他整合包/数据库。",
            fg=C_TEXT_MUTED, font_size=FS_TINY).pack(
                anchor=W, padx=PAD_CARD_X, pady=(0, PAD_CARD_Y))

        btn_bar = ctk.CTkFrame(self.dialog, fg_color=C_CARD_BG,
                                corner_radius=0, height=H_BTN_BAR,
                                border_width=BORDER_W, border_color=C_BORDER_SOFT)
        btn_bar.grid(row=1, column=0, sticky="ew")
        btn_bar.grid_propagate(False)
        make_button(btn_bar, "保存", command=self.save, accent=True,
                     width=90).pack(side=RIGHT, padx=(PAD_TIGHT, PAD_DIALOG),
                                    pady=(H_BTN_BAR - H_CONTROL) // 2)
        make_button(btn_bar, "取消", command=self.dialog.destroy,
                     width=90).pack(side=RIGHT, padx=(0, PAD_TIGHT),
                                    pady=(H_BTN_BAR - H_CONTROL) // 2)

    def on_switch_db(self):
        messagebox.showinfo("切换数据库",
            "切换数据库后需要重新打开整合包。\n\n"
            "原数据库不会被删除，可随时切回。", parent=self.dialog)
        self.dialog.destroy()
        if self.on_db_action:
            self.on_db_action('switch')

    def on_merge_db(self):
        self.dialog.destroy()
        if self.on_db_action:
            self.on_db_action('merge')

    def on_migrate_legacy(self):
        self.dialog.destroy()
        if self.on_db_action:
            self.on_db_action('migrate_legacy')

    def on_open_db(self):
        db = self.settings._settings_file.parent if self.settings._settings_file else None
        if db and db.exists():
            try:
                os.startfile(str(db))
            except Exception:
                pass

    def save(self):
        old_mode = self.settings.storage_mode
        self.settings.storage_mode = self.storage_var.get()
        self.settings.role = self.role_var.get()
        if not self.settings.save():
            messagebox.showerror("错误",
                "保存设置失败，请检查数据库文件夹是否可写",
                parent=self.dialog)
            return
        if old_mode != self.settings.storage_mode:
            if self.settings.storage_mode == "merged":
                messagebox.showwarning("提示",
                    "已切换到合并存储。\n\n"
                    "所有整合包将共用同一套预设。\n"
                    "不同整合包的同名枪包可能互相覆盖。\n\n"
                    "重新打开整合包后生效。",
                    parent=self.dialog)
            else:
                messagebox.showinfo("提示",
                    "已切换到隔离存储。\n\n"
                    "每个整合包使用独立数据库。\n"
                    "重新打开整合包后生效。",
                    parent=self.dialog)
        if self.on_save_callback:
            self.on_save_callback()
        self.dialog.destroy()


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
            if messagebox.askyesno("检测到旧版数据库",
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
        self.log_manager.log(f"数据库位置: {db_path}", 'INFO')
        self.log_manager.log(f"存储模式: {'合并' if self.settings.storage_mode == 'merged' else '隔离'}", 'INFO')
        self.log_manager.log(f"用户身份: {'玩家' if self.settings.role == 'player' else '开发者'}", 'INFO')
        if HAS_WATCHDOG:
            self.log_manager.log("watchdog 已就绪，可实时监控 TACZ 文件变化", 'INFO')
        else:
            self.log_manager.log("watchdog 未安装，文件变更需手动刷新 (pip install watchdog)", 'WARNING')
        if IS_WINDOWS:
            self.log_manager.log("已启用 Windows 原生回收站删除", 'INFO')
        self.log_manager.log("Step 1 · 拖入整合包根目录（或整合包内任意文件）", 'GUIDE')
        self._update_guide()

    # ==================== UI 构建 ====================
    def setup_ui(self):
        main_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        main_frame.pack(fill=BOTH, expand=True, padx=PAD_WINDOW, pady=PAD_WINDOW)

        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=0, minsize=LEFT_COL_W)
        main_frame.grid_columnconfigure(1, weight=1)

        left_panel = ctk.CTkFrame(main_frame, fg_color="transparent")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, PAD_TIGHT))

        right_panel = ctk.CTkFrame(main_frame, fg_color="transparent")
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(PAD_TIGHT, 0))

        # ===== 整合包分组（大拖入框） =====
        pack_group = ctk.CTkFrame(left_panel, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                    border_width=BORDER_W, border_color=C_BORDER_SOFT)
        pack_group.pack(fill=X, pady=(0, PAD_GAP))
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
        self.open_pack_btn = make_button(pack_btn_row, "📂",
                                           command=self.open_pack_folder,
                                           width=32, state="disabled")
        self.open_pack_btn.pack(side=LEFT, padx=(0, PAD_XS))
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

        # 最近打开（折叠）
        self.recent_frame = ctk.CTkFrame(pack_content, fg_color=C_PANEL_ALT_BG,
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
        preset_group.pack(fill=BOTH, expand=True, pady=(0, PAD_GAP))
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
        self.create_preset_btn = make_button(preset_btn_frame, "+ 创建",
                                              command=self.create_preset, state="disabled")
        self.create_preset_btn.pack(side=LEFT, padx=(0, PAD_XS))
        self.export_preset_btn = make_button(preset_btn_frame, "📤 导出",
                                              command=self.export_preset, state="disabled")
        self.export_preset_btn.pack(side=LEFT, padx=PAD_XS)
        self.export_incremental_btn = make_button(preset_btn_frame, "🔄 更新",
                                                   command=self.export_incremental,
                                                   state="disabled")
        self.export_incremental_btn.pack(side=LEFT, padx=PAD_XS)
        self.refresh_preset_btn = make_button(preset_btn_frame, "⟳",
                                               command=self.refresh_presets,
                                               state="disabled", width=40)
        self.refresh_preset_btn.pack(side=LEFT, padx=PAD_XS)
        self.loading_label = make_label(preset_btn_frame, text="", fg=C_ACCENT,
                                        font_size=FS_TINY)
        self.loading_label.pack(side=LEFT, padx=PAD_TIGHT)

        # ===== 预设详情 =====
        info_group = ctk.CTkFrame(left_panel, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                   border_width=BORDER_W, border_color=C_BORDER_SOFT)
        info_group.pack(fill=X)
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
        gunpack_group.pack(fill=BOTH, expand=True, pady=(0, PAD_GAP))
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

        self.refresh_gunpack_btn = make_button(toolbar_frame, "⟳ 刷新",
                                                command=self.refresh_gunpacks,
                                                state="disabled", width=70)
        self.refresh_gunpack_btn.pack(side=RIGHT)

        self.open_tacz_btn = make_button(toolbar_frame, "📂 打开TACZ",
                                          command=self.open_tacz_folder,
                                          state="disabled", width=100)
        self.open_tacz_btn.pack(side=RIGHT, padx=(0, PAD_XS))

        gunpack_list_wrap = ctk.CTkFrame(gunpack_content, fg_color=C_CARD_BG,
                                          corner_radius=R_CONTROL, border_width=BORDER_W,
                                          border_color=C_BORDER_SOFT)
        gunpack_list_wrap.pack(fill=BOTH, expand=True)
        self.gunpack_listbox = Listbox(gunpack_list_wrap, height=10,
                                        bg=C_CARD_BG, fg=C_TEXT_MAIN,
                                        selectbackground=C_ACCENT_SOFT,
                                        selectforeground=C_ACCENT,
                                        relief='flat', highlightthickness=0,
                                        font=(FONT_FAMILY, FS_BODY))
        self.gunpack_listbox.pack(fill=BOTH, expand=True, padx=PAD_XS, pady=PAD_XS)

        # 进度条
        self.progress_bar = ctk.CTkProgressBar(right_panel, height=H_PROGRESS,
                                                 corner_radius=R_PROGRESS,
                                                 fg_color=C_PANEL_ALT_BG,
                                                 progress_color=C_ACCENT)
        self.progress_bar.pack(fill=X, pady=(0, PAD_XS))
        self.progress_bar.pack_forget()
        self.progress_label = make_label(right_panel, text="",
                                          fg=C_TEXT_SECONDARY, font_size=FS_TINY)
        self.progress_label.pack(fill=X, pady=(0, PAD_XS))
        self.progress_label.pack_forget()

        self.apply_btn = make_button(right_panel, "Step 4 · ⚡ 一键替换",
                                      command=self.apply_preset,
                                      state="disabled", accent=True)
        self.apply_btn.pack(fill=X, pady=(0, PAD_GAP))

        # ===== 日志 =====
        log_group = ctk.CTkFrame(right_panel, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                  border_width=BORDER_W, border_color=C_BORDER_SOFT)
        log_group.pack(fill=BOTH, expand=True)
        make_label(log_group, text="日志", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        log_content = ctk.CTkFrame(log_group, fg_color="transparent")
        log_content.pack(fill=BOTH, expand=True, padx=PAD_CARD_X,
                         pady=(0, PAD_CARD_Y))
        log_toolbar = ctk.CTkFrame(log_content, fg_color="transparent")
        log_toolbar.pack(fill=X, pady=(0, PAD_TIGHT))
        self.log_toggle_btn = make_button(log_toolbar, "📋 显示完整日志",
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
            desc="Step 4 · 点击「⚡ 一键替换」启用预设")

    def setup_menu(self):
        menubar = Menu(self.root, bg=C_PANEL_BG, fg=C_TEXT_MAIN,
                        activebackground=C_ACCENT_SOFT, activeforeground=C_ACCENT,
                        font=(FONT_FAMILY, FS_SMALL), tearoff=0)
        self.root.config(menu=menubar)

        file_menu = Menu(menubar, tearoff=0, bg=C_PANEL_BG, fg=C_TEXT_MAIN,
                          activebackground=C_ACCENT_SOFT, activeforeground=C_ACCENT,
                          font=(FONT_FAMILY, FS_SMALL))
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="打开整合包", command=self.select_pack)
        file_menu.add_command(label="打开整合包路径", command=self.open_pack_folder)
        file_menu.add_separator()
        file_menu.add_command(label="关闭整合包", command=self.close_pack)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.root.quit)

        settings_menu = Menu(menubar, tearoff=0, bg=C_PANEL_BG, fg=C_TEXT_MAIN,
                              activebackground=C_ACCENT_SOFT, activeforeground=C_ACCENT,
                              font=(FONT_FAMILY, FS_SMALL))
        menubar.add_cascade(label="设置", menu=settings_menu)
        settings_menu.add_command(label="程序设置", command=self.open_settings)
        settings_menu.add_separator()
        settings_menu.add_command(label="日志显示设置", command=self.toggle_log_mode)

        func_menu = Menu(menubar, tearoff=0, bg=C_PANEL_BG, fg=C_TEXT_MAIN,
                          activebackground=C_ACCENT_SOFT, activeforeground=C_ACCENT,
                          font=(FONT_FAMILY, FS_SMALL))
        menubar.add_cascade(label="功能", menu=func_menu)
        func_menu.add_command(label="预设管理", command=self.open_preset_manager)
        func_menu.add_separator()
        func_menu.add_command(label="刷新所有", command=self.refresh_all)

        more_menu = Menu(menubar, tearoff=0, bg=C_PANEL_BG, fg=C_TEXT_MAIN,
                          activebackground=C_ACCENT_SOFT, activeforeground=C_ACCENT,
                          font=(FONT_FAMILY, FS_SMALL))
        menubar.add_cascade(label="更多", menu=more_menu)
        more_menu.add_command(label="使用教程", command=self.show_tutorial)
        more_menu.add_separator()
        more_menu.add_command(label="⚠ 强制更新校验数据", command=self.force_update_validation)
        more_menu.add_separator()
        more_menu.add_command(label="关于", command=self.show_about)

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
            messagebox.showwarning("提示", "数据库未初始化")
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
            messagebox.showerror("未找到 tacz",
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
            messagebox.showwarning("提示", "请先选择一个整合包")
            return
        try:
            if self.current_pack_path.exists():
                os.startfile(str(self.current_pack_path))
                self.log_manager.log(f"已打开整合包路径: {self.current_pack_path}", 'INFO')
            else:
                messagebox.showerror("错误", f"路径不存在: {self.current_pack_path}")
        except Exception as e:
            self.log_manager.log(f"打开整合包路径失败: {e}", 'ERROR')
            messagebox.showerror("错误", f"打开失败: {e}")

    def open_tacz_folder(self):
        if not self.tacz_path:
            messagebox.showwarning("提示", "请先选择一个整合包")
            return
        if not self.tacz_path.exists():
            messagebox.showerror("错误", f"TACZ 路径不存在: {self.tacz_path}")
            return
        try:
            os.startfile(str(self.tacz_path))
            self.log_manager.log(f"已打开 TACZ 文件夹: {self.tacz_path}", 'INFO')
        except Exception as e:
            self.log_manager.log(f"打开 TACZ 文件夹失败: {e}", 'ERROR')
            messagebox.showerror("错误", f"打开失败: {e}")

    # ==================== 设置 ====================
    def open_settings(self):
        if not self.db_ready:
            messagebox.showwarning("提示", "数据库未初始化，请重启程序")
            return
        SettingsDialog(self.root, self.settings,
                       on_save_callback=self._on_settings_saved,
                       on_db_action=self._on_db_action)

    def _on_settings_saved(self):
        self.log_manager.log(
            f"设置已保存: 存储模式={self.settings.storage_mode}, 身份={self.settings.role}",
            'SUCCESS')
        if self.current_pack_path:
            messagebox.showinfo("提示",
                "设置已保存。\n\n如需让存储模式变更生效，请关闭并重新打开整合包。")

    def _on_db_action(self, action: str):
        if action == 'switch':
            self.switch_database()
        elif action == 'merge':
            self.merge_database()
        elif action == 'migrate_legacy':
            self.migrate_legacy_database()

    # ==================== 数据库管理 ====================
    def switch_database(self):
        if self.is_applying:
            messagebox.showwarning("操作进行中", "请等待当前操作完成")
            return
        folder = filedialog.askdirectory(title="选择新的数据库文件夹",
                                          initialdir=str(PROGRAM_DIR))
        if not folder:
            return
        path = Path(folder)
        if LegacyDatabaseMigrator.is_legacy_database(path):
            if messagebox.askyesno("检测到旧版数据库",
                "该文件夹是旧版 FGC_database。\n\n"
                "是否先适配为新版数据库？"):
                self.migrate_legacy_database(path)
            return
        if (path / LEGACY_MIGRATED_MARKER).exists():
            messagebox.showinfo("提示",
                "该文件夹是已迁移的旧版数据库。\n\n"
                "如需重新适配，请删除旧库根目录下的\n"
                f"{LEGACY_MIGRATED_MARKER} 文件后再试。")
            return
        if not DatabaseLocator.is_valid_database(path):
            if messagebox.askyesno("新建数据库",
                "该文件夹不是有效数据库，是否初始化为新数据库？"):
                DatabaseLocator.init_database(path)
            else:
                return
        DatabaseLocator.save_db_path(path)
        self.settings.bind_database(path)
        if self.recent_manager:
            self.recent_manager = RecentPacksManager(path / ".global.json")
        self.log_manager.log(f"数据库已切换: {path}", 'SUCCESS')
        messagebox.showinfo("完成", "数据库已切换，请重新打开整合包。")
        self.close_pack()

    def merge_database(self):
        if not self.db_ready:
            messagebox.showwarning("提示", "数据库未初始化")
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
            messagebox.showwarning("提示", "不能合并到自身")
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
            messagebox.showwarning("部分失败", "\n".join(stats['errors'][:10]))
        else:
            messagebox.showinfo("完成", "数据库合并完成。")
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
                if not messagebox.askyesno("已迁移过",
                    f"该数据库已被标记为「已迁移」:\n{legacy_path}\n\n"
                    f"是否仍要再次适配？（可能产生重复预设）"):
                    return
            else:
                messagebox.showerror("错误", "所选文件夹不是旧版数据库")
                return

        dst = (self.settings._settings_file.parent
               if self.settings._settings_file else DEFAULT_DB_DIR)

        if self.settings.storage_mode == 'isolated':
            if messagebox.askyesno("选择目标数据库",
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
                    if messagebox.askyesno("新建数据库",
                        "目标不是有效数据库，是否初始化为新数据库？"):
                        DatabaseLocator.init_database(dst)
                    else:
                        return

        if not messagebox.askyesno("确认适配",
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
            self.root.after(0, lambda: self.root.update())

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
            messagebox.showwarning("部分失败",
                f"旧版数据库适配完成，部分预设失败:\n\n{err_text}")
        else:
            self.log_manager.log(
                f"旧版数据库适配完成: 迁移 {stats['migrated']}, "
                f"重命名 {stats['renamed']}, 跳过 {stats['skipped']}",
                'SUCCESS')
            messagebox.showinfo("完成",
                f"旧版数据库适配完成。\n\n"
                f"迁移预设: {stats['migrated']}\n"
                f"重命名: {stats['renamed']}\n"
                f"跳过: {stats['skipped']}\n\n"
                f"{disposed_text}")

        self.refresh_presets()
        self._update_guide()

    def _ask_after_migrate(self) -> str | None:
        dlg_w, dlg_h = DLG_CHOICE
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("迁移后处理")
        dialog.geometry(f"{dlg_w}x{dlg_h}")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(fg_color=C_WINDOW_BG)
        try:
            dialog.attributes('-alpha', 1.0)
            dialog.attributes('-transparentcolor', '')
        except Exception:
            pass
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dlg_w) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dlg_h) // 2
        dialog.geometry(f"+{x}+{y}")

        frame = ctk.CTkFrame(dialog, fg_color="transparent")
        frame.pack(fill=BOTH, expand=True, padx=PAD_DIALOG, pady=PAD_DIALOG)

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
            ctk.CTkRadioButton(frame, text=text, variable=mode_var, value=val,
                                text_color=C_TEXT_MAIN, font=(FONT_FAMILY, FS_SMALL),
                                fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER,
                                border_color=C_BORDER).pack(anchor=W,
                                                            pady=(PAD_MICRO, 0))
            make_label(frame, text=tip, fg=C_TEXT_MUTED, font_size=FS_TINY).pack(
                anchor=W, padx=PAD_INDENT, pady=(0, PAD_XS))

        result = {'mode': None}

        def on_ok():
            result['mode'] = mode_var.get()
            self.last_after_migrate_mode = result['mode']
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill=X, side=BOTTOM, pady=(PAD_GAP, 0))
        make_button(btn_frame, "确定", command=on_ok, accent=True).pack(
            side=RIGHT, padx=PAD_XS)
        make_button(btn_frame, "取消", command=on_cancel).pack(side=RIGHT)
        self.root.wait_window(dialog)
        return result['mode']

    def _ask_conflict_mode(self, message: str) -> str | None:
        dlg_w, dlg_h = DLG_CHOICE
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("冲突处理")
        dialog.geometry(f"{dlg_w}x{dlg_h}")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(fg_color=C_WINDOW_BG)
        try:
            dialog.attributes('-alpha', 1.0)
            dialog.attributes('-transparentcolor', '')
        except Exception:
            pass
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dlg_w) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dlg_h) // 2
        dialog.geometry(f"+{x}+{y}")

        frame = ctk.CTkFrame(dialog, fg_color="transparent")
        frame.pack(fill=BOTH, expand=True, padx=PAD_DIALOG, pady=PAD_DIALOG)
        lbl = make_label(frame, text=message, fg=C_TEXT_MAIN, font_size=FS_BODY)
        lbl.configure(wraplength=dlg_w - 2 * PAD_DIALOG, justify=LEFT, anchor=W)
        lbl.pack(anchor=W, fill=X, pady=(0, PAD_GAP))

        mode_var = StringVar(value="rename")
        for text, val in [
            ("重命名冲突预设（推荐，不丢数据）", "rename"),
            ("跳过冲突预设（保留现有）", "skip"),
            ("覆盖冲突预设（危险，会删除现有）", "overwrite"),
        ]:
            ctk.CTkRadioButton(frame, text=text, variable=mode_var, value=val,
                                text_color=C_TEXT_MAIN, font=(FONT_FAMILY, FS_SMALL),
                                fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER,
                                border_color=C_BORDER).pack(anchor=W, pady=PAD_MICRO)

        result = {'mode': None}

        def on_ok():
            result['mode'] = mode_var.get()
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill=X, side=BOTTOM, pady=(10, 0))
        make_button(btn_frame, "确定", command=on_ok, accent=True).pack(
            side=RIGHT, padx=5)
        make_button(btn_frame, "取消", command=on_cancel).pack(side=RIGHT)
        self.root.wait_window(dialog)
        return result['mode']

    def force_update_validation(self):
        if not self.preset_manager:
            messagebox.showwarning("提示", "请先加载整合包")
            return
        if not self.current_selected_preset:
            messagebox.showwarning("提示", "请先选择一个预设")
            return
        if not messagebox.askyesno("⚠ 危险操作警告",
            "⚠ 强制更新校验数据是危险操作！\n\n"
            "确定要继续吗？", icon='warning'):
            return
        name = self.current_selected_preset
        info = self.preset_manager.presets.get(name)
        if not info:
            return
        from_tacz = info.get('applied', False)
        if self.preset_manager.update_preset_index(name, from_tacz=from_tacz):
            self.refresh_gunpacks(use_cache=False)
            self.log_manager.log(f"⚠ 已强制更新预设 '{name}' 的校验数据", 'WARNING')
            messagebox.showinfo("完成", f"预设 '{name}' 的校验数据已强制更新。")
        else:
            messagebox.showerror("错误", "强制更新失败，请查看日志")

    # ==================== 身份提示 ====================
    def _show_role_dialog(self, title, message) -> str:
        dlg_w, dlg_h = DLG_CHOICE
        dialog = ctk.CTkToplevel(self.root)
        dialog.title(title)
        dialog.geometry(f"{dlg_w}x{dlg_h}")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(fg_color=C_WINDOW_BG)
        try:
            dialog.attributes('-alpha', 1.0)
            dialog.attributes('-transparentcolor', '')
        except Exception:
            pass
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dlg_w) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dlg_h) // 2
        dialog.geometry(f"+{x}+{y}")

        frame = ctk.CTkFrame(dialog, fg_color="transparent")
        frame.pack(fill=BOTH, expand=True, padx=PAD_DIALOG, pady=PAD_DIALOG)
        msg_label = make_label(frame, text=message, fg=C_TEXT_MAIN, font_size=FS_BODY)
        msg_label.configure(wraplength=dlg_w - 2 * PAD_DIALOG, justify=LEFT, anchor=W)
        msg_label.pack(anchor=W, fill=X, pady=(0, PAD_GAP))

        dont_remind_var = BooleanVar(value=False)
        ctk.CTkCheckBox(frame, text="本次启动不再提醒",
                        variable=dont_remind_var,
                        text_color=C_TEXT_MAIN, font=(FONT_FAMILY, FS_SMALL),
                        fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER,
                        border_color=C_BORDER).pack(anchor=W,
                                                    pady=(PAD_XS, PAD_GAP))

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill=X, side=BOTTOM, pady=(PAD_GAP, 0))
        result = {'action': 'ok'}

        def on_ok():
            if dont_remind_var.get():
                self.dont_remind_this_session = True
            result['action'] = 'ok'
            dialog.destroy()

        def on_export():
            if dont_remind_var.get():
                self.dont_remind_this_session = True
            result['action'] = 'export'
            dialog.destroy()

        if self.settings.role == "developer":
            make_button(btn_frame, "导出增量更新", command=on_export,
                         accent=True).pack(side=RIGHT, padx=PAD_XS)
        make_button(btn_frame, "确定", command=on_ok).pack(side=RIGHT)
        self.root.wait_window(dialog)
        return result['action']

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
    def toggle_recent(self):
        if self.recent_visible:
            self.recent_frame.pack_forget()
            self.recent_toggle_btn.configure(text="▼ 最近")
            self.recent_visible = False
        else:
            self.recent_frame.pack(fill=X, pady=(6, 0))
            self.recent_toggle_btn.configure(text="▲ 最近")
            self.recent_visible = True
            self.update_recent_list()

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
            messagebox.showerror("错误", f"路径不存在: {path}")
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
            messagebox.showwarning("提示", "请先选择整合包")
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
            messagebox.showwarning("提示", "请先选择整合包")
            return
        if self.is_applying:
            messagebox.showwarning("操作进行中", "请等待当前操作完成")
            return
        if not file_path.exists():
            messagebox.showerror("错误", f"文件不存在: {file_path}")
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
                messagebox.showerror("错误", f"无法识别文件: {e}")

    # ==================== 整合包管理 ====================
    def select_pack(self):
        if not self.db_ready:
            messagebox.showwarning("提示", "数据库未初始化，请重启程序")
            return
        if self.is_applying:
            messagebox.showwarning("操作进行中", "请等待当前操作完成")
            return
        if self.loading_presets:
            messagebox.showinfo("加载中", "预设列表正在加载，请稍候...")
            return
        folder = filedialog.askdirectory(title="选择整合包根目录")
        if not folder:
            return
        self.load_pack(Path(folder))

    def load_pack(self, pack_path: Path):
        if not self.db_ready:
            messagebox.showwarning("提示", "数据库未初始化")
            return
        tacz_path = pack_path / 'tacz'
        if not tacz_path.exists() or not tacz_path.is_dir():
            messagebox.showerror("错误", "未找到tacz文件夹，请选择正确的整合包根目录")
            return

        legacy_dirs = LegacyDatabaseMigrator.find_legacy_databases(pack_path)
        if legacy_dirs:
            if messagebox.askyesno("检测到旧版数据库",
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
        self.loading_label.configure(text="⏳ 加载中...")
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
        self.loading_label.configure(text="")
        self._disable_buttons(False)
        self._update_preset_list()
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
        except Exception:
            pass

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
            messagebox.showwarning("操作进行中", "请等待当前操作完成")
            return
        if self.loading_presets:
            messagebox.showinfo("加载中", "预设列表正在加载，请稍候...")
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
        self.log_manager.log("已关闭整合包", 'INFO')
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

    def refresh_presets(self):
        if not self.preset_manager or self.loading_presets:
            return
        self.loading_presets = True
        self.loading_label.configure(text="⏳ 刷新中...")
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
        self.loading_label.configure(text="")
        self._disable_buttons(False)
        self._update_preset_list()
        self.log_manager.log("预设列表刷新完成", 'INFO')
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
        version = info.get('version', 'v1.0.0')
        self.preset_version_label.configure(text=f"版本号: {version}")
        status = "已应用 ✓" if info.get('applied', False) else "未应用"
        self.preset_status_label.configure(text=f"状态: {status}")
        self.preset_status_label.configure(
            text_color=C_SUCCESS if info.get('applied') else C_WARNING)
        self.version_entry.delete(0, END)
        self.version_entry.insert(0, version)
        if info.get('applied', False):
            self.apply_btn.configure(state="disabled", text="已应用 ✓")
            self.export_incremental_btn.configure(state="normal")
        else:
            self.apply_btn.configure(state="normal", text="Step 4 · ⚡ 一键替换")
            self.export_incremental_btn.configure(state="disabled")
        self.export_preset_btn.configure(state="normal")
        self.refresh_gunpacks(use_cache=False)
        self.log_manager.log(f"选择预设: {name}", 'INFO')
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
            messagebox.showwarning("操作进行中", "请等待当前操作完成")
            return

        info = self.preset_manager.presets.get(preset_name)
        if not info:
            return
        if info.get('applied', False):
            messagebox.showwarning("提示",
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
                messagebox.showerror("错误",
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
                messagebox.showerror("错误", f"目标数据库不存在: {target_db}")
                return
            if not DatabaseLocator.is_valid_database(target_db):
                if messagebox.askyesno("新建数据库",
                    "目标文件夹不是有效数据库，是否初始化为新数据库？"):
                    DatabaseLocator.init_database(target_db)
                else:
                    return

        target_db.mkdir(parents=True, exist_ok=True)

        conflict_mode = 'rename'
        if (target_db / preset_name).exists():
            if not messagebox.askyesno("预设已存在",
                f"目标数据库中已存在预设 '{preset_name}'。\n\n"
                f"是否覆盖？（原预设会被移入回收站）"):
                return
            conflict_mode = 'overwrite'

        src_path = Path(info['path'])
        target_path = target_db / preset_name

        if not messagebox.askyesno("确认迁移",
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
        dlg_w, dlg_h = DLG_SMALL
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("迁移预设")
        dialog.geometry(f"{dlg_w}x{dlg_h}")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(fg_color=C_WINDOW_BG)
        try:
            dialog.attributes('-alpha', 1.0)
            dialog.attributes('-transparentcolor', '')
        except Exception:
            pass
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dlg_w) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dlg_h) // 2
        dialog.geometry(f"+{x}+{y}")

        frame = ctk.CTkFrame(dialog, fg_color="transparent")
        frame.pack(fill=BOTH, expand=True, padx=PAD_DIALOG, pady=PAD_DIALOG)

        make_label(frame, text="迁移预设到：",
                    fg=C_TEXT_MAIN, font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, pady=(0, PAD_GAP))

        mode_var = StringVar(value="pack")
        ctk.CTkRadioButton(frame, text="另一个整合包（使用其数据库）",
                            variable=mode_var, value="pack",
                            text_color=C_TEXT_MAIN, font=(FONT_FAMILY, FS_SMALL),
                            fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER,
                            border_color=C_BORDER).pack(anchor=W,
                                                        pady=(PAD_MICRO, 0))
        make_label(frame, text="  选择整合包根目录，预设会迁移到该整合包的数据库",
                    fg=C_TEXT_MUTED, font_size=FS_TINY).pack(
                        anchor=W, padx=PAD_INDENT, pady=(0, PAD_TIGHT))

        ctk.CTkRadioButton(frame, text="另一个数据库（直接选择数据库文件夹）",
                            variable=mode_var, value="db",
                            text_color=C_TEXT_MAIN, font=(FONT_FAMILY, FS_SMALL),
                            fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER,
                            border_color=C_BORDER).pack(anchor=W,
                                                        pady=(PAD_MICRO, 0))
        make_label(frame, text="  选择已存在的数据库，或新建一个空数据库",
                    fg=C_TEXT_MUTED, font_size=FS_TINY).pack(
                        anchor=W, padx=PAD_INDENT, pady=(0, PAD_TIGHT))

        result = {'mode': None}

        def on_ok():
            result['mode'] = mode_var.get()
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill=X, side=BOTTOM, pady=(PAD_GAP, 0))
        make_button(btn_frame, "下一步", command=on_ok, accent=True).pack(
            side=RIGHT, padx=PAD_XS)
        make_button(btn_frame, "取消", command=on_cancel).pack(side=RIGHT)
        self.root.wait_window(dialog)
        return result['mode']

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
            messagebox.showinfo("迁移成功",
                f"预设 '{preset_name}' 已迁移到:\n{target_db}\n\n"
                f"源预设已{'移入回收站' if src_removed else '保留'}。")
            self.refresh_presets()
        else:
            messagebox.showerror("迁移失败", "预设迁移失败，请查看日志")

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
            messagebox.showerror("错误", f"预设 '{new_name}' 已存在")
            return
        for char in r'\/:*?"<>|':
            if char in new_name:
                messagebox.showerror("错误", f"预设名称不能包含非法字符: {char}")
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
                messagebox.showinfo("成功", f"预设已重命名为: {new_name}")
            else:
                messagebox.showerror("错误", "预设重命名失败")
        finally:
            self.root.config(cursor="")

    def delete_preset(self, preset_name):
        if not self.preset_manager or self.loading_presets:
            return
        if preset_name == "default":
            messagebox.showwarning("提示", "不能删除默认预设")
            return
        info = self.preset_manager.presets.get(preset_name)
        if not info:
            return
        if info.get('applied', False):
            messagebox.showwarning("提示",
                f"预设 '{preset_name}' 已应用，请先切换到其他预设再删除")
            return
        if not messagebox.askyesno("确认删除",
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
                    self.apply_btn.configure(state="disabled", text="Step 4 · ⚡ 一键替换")
                    self.export_preset_btn.configure(state="disabled")
                    self.export_incremental_btn.configure(state="disabled")
                    self.gunpack_listbox.delete(0, END)
                    self.gunpack_count_label.configure(text="共 0 个枪包")
                self._update_preset_list()
                messagebox.showinfo("成功", f"预设 '{preset_name}' 已删除")
                self._update_guide()
            else:
                messagebox.showerror("错误", "删除预设失败")
        except Exception as e:
            messagebox.showerror("错误", f"删除失败: {e}")

    def create_preset(self):
        if not self.preset_manager or self.loading_presets:
            return
        from tkinter import simpledialog
        name = simpledialog.askstring("创建预设", "请输入预设名称:")
        if not name or not name.strip():
            return
        name = name.strip()
        if name in self.preset_manager.presets:
            messagebox.showerror("错误", f"预设 '{name}' 已存在")
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
            messagebox.showinfo("创建成功",
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
            messagebox.showwarning("提示", "请先选择一个预设")
            return
        if self.is_applying:
            messagebox.showwarning("操作进行中", "请等待当前操作完成")
            return

        name = self.current_selected_preset
        info = self.preset_manager.presets.get(name)
        if not info:
            return

        if name == "default":
            messagebox.showwarning("无法导出",
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
            messagebox.showwarning("提示", "请先选择一个预设")
            return
        if self.is_applying:
            messagebox.showwarning("操作进行中", "请等待当前操作完成")
            return
        name = self.current_selected_preset
        info = self.preset_manager.presets.get(name)
        if not info:
            return
        if not info.get('applied', False):
            messagebox.showwarning("提示", "只能对已应用的预设导出增量更新")
            return
        changes = self.preset_manager.detect_changes(name)
        total = len(changes['added']) + len(changes['removed']) + len(changes['modified'])
        if total == 0:
            messagebox.showinfo("提示", "未检测到任何变更，无需导出")
            return
        if not messagebox.askyesno("确认导出增量包",
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
            messagebox.showinfo("导出成功", f"预设已导出到:\n{export_path}")
        else:
            messagebox.showerror("导出失败", "预设导出失败，请查看日志")
        self._update_preset_list()

    def _on_export_inc_finished(self, success, export_path):
        self.hide_progress()
        self.set_busy_state(False, "")
        if success:
            messagebox.showinfo("导出成功",
                f"增量更新包已导出到:\n{export_path}\n\n"
                f"✅ 校验数据已自动同步为最新")
        else:
            messagebox.showerror("导出失败", "增量包导出失败，请查看日志")
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
            messagebox.showerror("导入失败", "预设导入失败，请查看日志")
            return
        self._update_preset_list()
        self.refresh_gunpacks(use_cache=False)
        self._update_guide()
        self._ask_delete_source_package(import_path, "预设导入成功！")

    def _on_import_inc_finished(self, success, import_path: Path):
        self.hide_progress()
        self.set_busy_state(False, "")
        if not success:
            messagebox.showerror("更新失败", "增量更新失败，请查看日志")
            return
        self.refresh_gunpacks(use_cache=False)
        self._update_preset_list()
        self._update_guide()
        self._ask_delete_source_package(import_path, "增量更新已成功应用！")

    def _ask_delete_source_package(self, import_path: Path, success_msg: str):
        try:
            if not import_path.exists():
                messagebox.showinfo("导入完成", success_msg)
                return
            try:
                size_str = format_size(import_path.stat().st_size)
            except Exception:
                size_str = "未知"
            reply = messagebox.askyesno(
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
                messagebox.showwarning("警告",
                    f"删除源压缩包失败，请手动处理。\n\n错误: {e}")
        except Exception as e:
            self.log_manager.log(f"处理源压缩包时出错: {e}", 'WARNING')
            messagebox.showinfo("导入完成", success_msg)

    # ==================== 进度条 ====================
    def show_progress(self, current, total, message=""):
        if total > 0:
            pct = current / total
            self.root.after(0, lambda: self.progress_bar.set(pct))
            self.root.after(0, lambda: self.progress_label.configure(
                text=f"{message} ({current}/{total})"))
        self.root.after(0, lambda: self.root.update())

    def hide_progress(self):
        self.root.after(0, lambda: self.progress_bar.pack_forget())
        self.root.after(0, lambda: self.progress_label.pack_forget())
        self.root.after(0, lambda: self.root.update())

    def set_busy_state(self, busy, operation=""):
        if busy:
            self.is_applying = True
            self.apply_btn.configure(state="disabled", text=f"⏳ {operation}中...")
            self.export_preset_btn.configure(state="disabled")
            self.export_incremental_btn.configure(state="disabled")
            self.create_preset_btn.configure(state="disabled")
            self.refresh_preset_btn.configure(state="disabled")
            self.refresh_gunpack_btn.configure(state="disabled")
            self.select_pack_btn.configure(state="disabled")
            self.open_pack_btn.configure(state="disabled")
            self.open_tacz_btn.configure(state="disabled")
            self.save_version_btn.configure(state="disabled")
            self.preset_listbox.config(state=DISABLED)
        else:
            self.is_applying = False
            self.apply_btn.configure(state="normal", text="Step 4 · ⚡ 一键替换")
            self.export_preset_btn.configure(state="normal")
            self.create_preset_btn.configure(state="normal")
            self.refresh_preset_btn.configure(state="normal")
            self.refresh_gunpack_btn.configure(state="normal")
            self.select_pack_btn.configure(state="normal")
            self.save_version_btn.configure(state="normal")
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
            info_d = indexed.get(name, {})
            icon = "📦" if info_d.get('type', 'zip') == 'zip' else "📁"
            self.gunpack_listbox.insert(END, f"✖ {icon} {name}")
            i = self.gunpack_listbox.size() - 1
            self.gunpack_listbox.itemconfig(i, fg=C_STATUS_MISSING, bg=C_STATUS_MISSING_BG)

        for name in extra:
            info_d = current.get(name, {})
            icon = "📦" if info_d.get('type', 'zip') == 'zip' else "📁"
            self.gunpack_listbox.insert(END, f"⊙ {icon} {name}")
            i = self.gunpack_listbox.size() - 1
            self.gunpack_listbox.itemconfig(i, fg=C_STATUS_EXTRA, bg=C_STATUS_EXTRA_BG)

        for name in modified:
            info_d = current.get(name, {})
            icon = "📦" if info_d.get('type', 'zip') == 'zip' else "📁"
            self.gunpack_listbox.insert(END, f"⚡ {icon} {name}")
            i = self.gunpack_listbox.size() - 1
            self.gunpack_listbox.itemconfig(i, fg=C_STATUS_MODIFIED, bg=C_STATUS_MODIFIED_BG)

        for name in normal:
            info_d = current.get(name, {})
            icon = "📦" if info_d.get('type', 'zip') == 'zip' else "📁"
            self.gunpack_listbox.insert(END, f"✓ {icon} {name}")
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
                lines.append(f"  ✖ 缺失: {len(missing)} 个 ({pv})")
            if extra:
                pv = ', '.join(extra[:5]) + (" ..." if len(extra) > 5 else "")
                lines.append(f"  ⊙ 多余: {len(extra)} 个 ({pv})")
            if modified:
                pv = ', '.join(modified[:5]) + (" ..." if len(modified) > 5 else "")
                lines.append(f"  ⚡ 变更: {len(modified)} 个 ({pv})")
            self.log_manager.log("\n".join(lines), 'WARNING')
        else:
            self.log_manager.log(f"预设 '{preset_name}' 所有枪包校验通过 ✓ (共 {total} 个)", 'SUCCESS')

    # ==================== 预设应用 ====================
    def apply_preset(self):
        if not self.preset_manager or not self.tacz_path or self.loading_presets:
            return
        if self.is_applying:
            messagebox.showwarning("操作进行中", "请等待当前操作完成")
            return
        if not self.current_selected_preset:
            messagebox.showwarning("提示", "请先选择一个预设")
            return
        name = self.current_selected_preset
        if name not in self.preset_manager.presets:
            return
        if self.preset_manager.presets[name].get('applied', False):
            messagebox.showinfo("提示", f"预设 '{name}' 已经应用")
            return
        if not messagebox.askyesno("确认替换",
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
            messagebox.showerror("错误", "预设应用失败，请查看日志")
        self._start_watcher()
        self._update_guide()

    # ==================== 通用功能 ====================
    def toggle_log_mode(self):
        if self.log_manager:
            self.show_full_log = not self.show_full_log
            self.log_manager.set_show_full(self.show_full_log)
            self.log_toggle_btn.configure(
                text="📋 显示单条日志" if self.show_full_log else "📋 显示完整日志")

    def clear_log(self):
        if self.log_manager:
            self.log_manager.clear()

    def refresh_all(self):
        if self.loading_presets:
            messagebox.showinfo("加载中", "预设列表正在加载，请稍候...")
            return
        self.refresh_presets()
        if self.current_selected_preset:
            self.refresh_gunpacks(use_cache=False)
        self.log_manager.log("所有数据已刷新", 'INFO')

    def open_preset_manager(self):
        if not self.preset_manager:
            messagebox.showwarning("提示", "请先加载整合包")
            return
        try:
            os.startfile(str(self.preset_manager.database_path))
        except Exception as e:
            self.log_manager.log(f"打开文件夹失败: {e}", 'ERROR')

    def show_tutorial(self):
        messagebox.showinfo("使用教程",
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
            "枪包列表右上角「📂 打开TACZ」按钮")

    def show_about(self):
        db_str = "未初始化"
        if self.settings._settings_file:
            db_str = str(self.settings._settings_file.parent)
        messagebox.showinfo("关于",
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
def main():
    if HAS_DND:
        try:
            root = TkinterDnD.Tk()
            root.configure(bg=C_WINDOW_BG)
        except Exception:
            root = ctk.CTk()
    else:
        root = ctk.CTk()

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
        if app.is_applying:
            if messagebox.askyesno("操作进行中",
                    "正在操作中，确定要退出吗？\n\n程序将在任务完成后自动退出。"):
                app._stop_watcher()
                root.quit()
        else:
            app._stop_watcher()
            root.quit()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()