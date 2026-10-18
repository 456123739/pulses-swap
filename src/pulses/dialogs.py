"""
窗口内覆盖层对话框 + 消息框 + 数据库定位
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
from .widgets import *



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
        ui_call(host.root, _call)
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

        # 注意：这里先不 place 遮罩和卡片。
        # 调用方紧接着才会往 body 里塞内容，如果现在就把遮罩摆上去，
        # 会先看到一张空白卡片、下一帧内容才出现（用户反馈的
        # 「先产生空白，然后才展示窗口」）。改成等当前调用栈跑完
        # （含调用方构建内容）再摆上去，一出现就是完整的。
        self._revealed = False
        self._closed = False
        self.mask = ctk.CTkFrame(host.overlay_host, fg_color=C_PANEL_ALT_BG,
                                  corner_radius=0)
        # height=1 让卡片高度完全由内容决定（CTkFrame 默认 200x200 会撑出空白）
        self.card = ctk.CTkFrame(self.mask, fg_color=C_PANEL_BG,
                                  corner_radius=R_CARD, border_width=BORDER_W,
                                  border_color=C_BORDER_SOFT,
                                  width=width, height=1)
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
        _OVERLAY_STACK.append(self)
        # 等调用方把内容塞完（同一调用栈内）再摆上去
        try:
            self.root.after_idle(self._reveal)
        except Exception:
            self._reveal()

    def _reveal(self):
        """摆上遮罩与卡片：此时 body 里的内容已经建好并算过尺寸。"""
        if self._revealed or self._closed:
            return
        self._revealed = True
        try:
            self.mask.place(relx=0.0, rely=0.0, relwidth=1.0, relheight=1.0)
            self.mask.lift()
            self.card.place(relx=0.5, rely=0.5, anchor="center")
            self.root.update_idletasks()      # 先把内容画出来，再显示
            self.mask.focus_set()
        except Exception:
            pass
        self._play_entrance()

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
        self._closed = True
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
        # 先藏起来：调用方紧接着才往 body 里塞内容，直接显示会先看到空白窗口
        self._revealed = False
        try:
            self.window.withdraw()
        except Exception:
            pass
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
        # 等内容建好再显示（同一调用栈跑完）
        try:
            parent.after_idle(self._reveal)
        except Exception:
            self._reveal()

    def _reveal(self):
        if self._revealed:
            return
        self._revealed = True
        try:
            self.window.update_idletasks()
            self.window.deiconify()
            self.window.lift()
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
        # 需求：这是「选文件夹」的界面，做成独立小窗口（640x520），
        # 而不是铺满主窗口的覆盖层 —— 覆盖层在主窗口最大化时看着像占满全屏。
        dlg_w = DLG_LOCATOR[0]
        card = ToplevelCard(self.parent, width=dlg_w, height=DLG_LOCATOR[1],
                             escape_value=None, title="选择数据库位置")
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
