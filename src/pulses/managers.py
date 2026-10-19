"""
数据层：设置 / 日志 / 引导 / 最近 / 监控 / 预设
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
from .animation import apply_animations_setting
from . import config
from .utils import *



# ==================== 设置管理 ====================
class AppSettings:
    def __init__(self):
        self.storage_mode = "isolated"
        self.animations = True
        self.role = "player"
        self.online_auto_check = True
        # 同步时要不要顺手删掉本地多余枪包（默认不删，删了不可逆）
        self.online_sync_clean = False
        # 开发者发布前要不要先看差异清单（默认直接发）
        self.online_publish_preview = False
        self._settings_file: Path | None = None

    def bind_database(self, db_path: Path):
        self._settings_file = db_path / ".settings.json"
        self.load()
        apply_animations_setting(self.animations)

    def load(self):
        if self._settings_file and self._settings_file.exists():
            try:
                with open(self._settings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.storage_mode = data.get('storage_mode', 'isolated')
                self.role = data.get('role', 'player')
                self.animations = bool(data.get('animations', True))
                self.online_auto_check = bool(
                    data.get('online_auto_check', True))
                self.online_sync_clean = bool(
                    data.get('online_sync_clean', False))
                self.online_publish_preview = bool(
                    data.get('online_publish_preview', False))
            except Exception:
                pass

    def save(self) -> bool:
        if not self._settings_file:
            return False
        try:
            self._settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._settings_file, 'w', encoding='utf-8') as f:
                json.dump({'storage_mode': self.storage_mode,
                           'role': self.role,
                           'animations': self.animations,
                           'online_auto_check': self.online_auto_check,
                           'online_sync_clean': self.online_sync_clean,
                           'online_publish_preview': self.online_publish_preview},
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
            ui_call(self.root, self._update_display)

    def set_show_full(self, show_full: bool):
        self.show_full = show_full
        if threading.current_thread() is threading.main_thread():
            self._update_display()
        else:
            ui_call(self.root, self._update_display)

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

    def register(self, step_name: str, widgets: list = None,
                 desc: str = "", colors: tuple = None):
        """只登记步骤与说明文案。

        需求：去掉控件上的绿色描边高亮（Step 1 卡片那圈绿边），
        所以 widgets 不再参与显示 —— 引导只通过日志文案提示当前该做哪步。
        """
        self._steps[step_name] = {
            'widgets': [],
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
        if config.ANIMATIONS_ENABLED:
            tween(widget, "guide", 1100, frame,
                  on_done=lambda: self._pulse(widget, color),
                  easing=ease_linear)

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
PRESET_MARK_APPLIED = "✓ "


def preset_name_of(row_text: str) -> str:
    """列表行文本 → 预设名（「已应用」前缀不算名字）。"""
    if row_text.startswith(PRESET_MARK_APPLIED):
        return row_text[len(PRESET_MARK_APPLIED):]
    return row_text


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

    def reload_preset(self, name: str) -> bool:
        """在线同步改了磁盘内容后，把单个预设从 index.json 重新读一遍。"""
        info = self.presets.get(name)
        if not info:
            return False
        path = Path(info['path'])
        if not path.exists():
            return False
        self._load_preset(path)
        self.save_cache()
        return True

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
            # 预检：tacz 必须可写。只读目录下如果直接搬，会出现「删不掉旧文件、
            # 新枪包却移进去、最后还标记成已应用」的半成品状态。
            probe = self.tacz_path / ".pulses_write_probe"
            try:
                probe.write_bytes(b"x")
                probe.unlink()
            except OSError as exc:
                self.log.log(f"tacz 目录不可写，无法替换：{exc}", 'ERROR')
                return False
            if current_applied and current_applied in self.presets:
                cur_info = self.presets[current_applied]
                cur_path = Path(cur_info['path'])
                moved = self._move_items(self.tacz_path, cur_path, protected_all, progress_callback)
                cur_info['applied'] = False
                self._update_preset_status(cur_path, False)
                self.log.log(f"已回收 {moved} 个枪包到 '{current_applied}'", 'INFO',
                          verbose=True)
            self._clear_dir(self.tacz_path, protected_all)
            leftovers = [p.name for p in Path(self.tacz_path).iterdir()
                         if p.name not in protected_all]
            if leftovers:
                raise OSError(f"tacz 没有被清空（{len(leftovers)} 项删不掉）：{leftovers[:3]}")
            metadata = ('description.txt', 'index.json', 'version.txt')
            moved = self._move_items(target_path, self.tacz_path, list(metadata),
                                     progress_callback)
            remaining = [p.name for p in target_path.iterdir()
                         if p.name not in metadata]
            if remaining:
                raise OSError(f"{len(remaining)} 个枪包没能移入 tacz：{remaining[:3]}")
            target_preset['applied'] = True
            self._update_preset_status(target_path, True)
            self.current_preset = preset_name
            self.save_cache()
            self.log.log(f"成功应用预设 '{preset_name}' (移动了 {moved} 个枪包)", 'SUCCESS')
            return True
        except Exception as e:
            self.log.log(f"应用预设失败: {e}", 'ERROR')
            # 保守收尾：半成品不算任何预设「已应用」，让用户能重试
            try:
                target_preset['applied'] = False
                self._update_preset_status(target_path, False)
                if current_applied and current_applied in self.presets:
                    cur_info = self.presets[current_applied]
                    cur_info['applied'] = False
                    self._update_preset_status(Path(cur_info['path']), False)
                self.current_preset = None
                self.save_cache()
            except Exception:
                pass
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
