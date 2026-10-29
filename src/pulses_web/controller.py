"""无 UI 的应用控制器。

只调用现有核心（PresetManager / OnlineService / Installer / diff / settings），
不包含任何 tkinter / customtkinter 逻辑。
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
import traceback
from collections import deque
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from pulses import config
from pulses.core import paths
from pulses.managers import (
    AppSettings, PresetManager, RecentPacksManager, TaczWatcher,
)
from pulses.utils import safe_print

try:
    from online.service import OnlineService, PresetRef
    from online import diff
    HAS_ONLINE = True
except Exception:                       # 打包缺 online 时仍允许只读功能
    HAS_ONLINE = False
    OnlineService = None
    PresetRef = None
    diff = None


def _locked(fn):
    """串行化会改状态的 controller 入口（RLock 允许内部递归调用）。"""
    from functools import wraps

    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        with self.lock:
            return fn(self, *args, **kwargs)
    return wrapper


class LogBus:
    """核心类需要的 `.log(message, level, verbose=...)` 接口。"""

    def __init__(self, controller):
        self.controller = controller

    def log(self, message, level="INFO", verbose=True):
        self.controller.add_log(message, level, verbose=verbose)


class AppController:
    def __init__(self, base_dir: Path | None = None, bus=None):
        self.bus = bus
        self.lock = threading.RLock()
        self.logs = deque(maxlen=1200)
        self.base_dir = Path(base_dir or self._load_database_path())
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.settings = AppSettings()
        self.settings.bind_database(self.base_dir)
        self.recent = RecentPacksManager(self.base_dir / ".global.json")
        self.pack_path: Path | None = None
        self.tacz_path: Path | None = None
        self.db_path: Path = self.base_dir
        self.preset_manager: PresetManager | None = None
        self.online = None
        self.watcher = None
        self.selected: str | None = None
        self.last_plan = None
        self.last_publish_plan = None
        self._rev = 0
        self._init_online()
        self.add_log(f"Pulses Swap Web {getattr(config, 'VERSION', '')}",
                     "SUCCESS", verbose=False)

    @staticmethod
    def _load_database_path() -> Path:
        for cfg in (paths.BOOTSTRAP_FILE, paths.LEGACY_BOOTSTRAP_FILE):
            try:
                if cfg.exists():
                    data = json.loads(cfg.read_text(encoding="utf-8"))
                    raw = data.get("database_path")
                    if raw:
                        candidate = Path(raw).expanduser()
                        if candidate.exists() and candidate.is_dir():
                            return candidate
            except Exception:
                pass
        return paths.DEFAULT_DB_DIR

    # ------------------------------------------------------------------
    # 基础状态
    # ------------------------------------------------------------------
    @property
    def role(self):
        return "developer" if str(getattr(self.settings, "role", "player")) == "developer" else "player"

    def revision(self):
        with self.lock:
            self._rev += 1
            return self._rev

    def emit(self, kind, data=None, **kwargs):
        if self.bus is not None:
            self.bus.emit(kind, data, **kwargs)

    def add_log(self, message, level="INFO", verbose=True):
        entry = {"time": time.strftime("%H:%M:%S"), "message": str(message),
                 "level": str(level), "verbose": bool(verbose)}
        with self.lock:
            self.logs.append(entry)
        self.emit("log.append", entry)

    def _init_online(self, db_path=None):
        self.online = None
        if not HAS_ONLINE:
            return
        try:
            self.online = OnlineService(
                db_path or self.db_path, log=LogBus(self).log,
                app_version=getattr(config, "VERSION", ""),
                account_db=str(paths.DEFAULT_DB_DIR))
            for note in self.online.recover_all():
                self.add_log("在线：" + note, "INFO", verbose=True)
        except Exception as exc:
            self.add_log(f"在线模块初始化失败: {exc}", "ERROR")
            self.online = None

    def state(self):
        with self.lock:
            presets = []
            if self.preset_manager:
                for name, info in self.preset_manager.presets.items():
                    presets.append({
                        "name": name,
                        "version": info.get("version", ""),
                        "applied": bool(info.get("applied")),
                        "count": len(info.get("gunpacks") or {}),
                        "path": info.get("path", ""),
                    })
            account = self.online.account_info() if self.online else {}
            if account:
                account.pop("uid", None)
            plan = self._plan_summary(self.last_plan) if self.last_plan else None
            return {
                "revision": self._rev,
                "version": getattr(config, "VERSION", ""),
                "role": self.role,
                "database": str(self.db_path),
                "pack": {
                    "path": str(self.pack_path) if self.pack_path else "",
                    "name": self.pack_path.name if self.pack_path else "",
                    "tacz": str(self.tacz_path) if self.tacz_path else "",
                    "loaded": bool(self.preset_manager),
                },
                "presets": presets,
                "selected": self.selected,
                "gunpacks": self.gunpacks(),
                "online": {
                    "available": self.online is not None,
                    "account": account,
                    "binding": self._binding_state(),
                },
                "plan": plan,
                "publish_ready": bool(self.last_publish_plan),
                "recent": self.recent.get_all()[:8],
                "logs": list(self.logs)[-300:],
                "settings": self._settings_state(),
                "capabilities": {
                    "developer": self.role == "developer",
                    "online": self.online is not None,
                },
            }

    def _settings_state(self):
        s = self.settings
        return {
            "storage_mode": s.storage_mode,
            "role": s.role,
            "animations": bool(s.animations),
            "online_auto_check": bool(s.online_auto_check),
            "online_sync_clean": bool(s.online_sync_clean),
            "online_publish_preview": bool(s.online_publish_preview),
            "online_confirm_full": bool(s.online_confirm_full),
        }

    def _binding_state(self):
        if not self.online or not self.selected:
            return {}
        try:
            data = self.online.source_of(self.selected) or {}
            lanzou = data.get("lanzou") or {}
            return {
                "url": lanzou.get("url", ""),
                "password": lanzou.get("password", ""),
                "cloud_path": data.get("cloud_path", ""),
                "last_version": data.get("last_version", ""),
                "history": list(data.get("history") or [])[:10],
            }
        except Exception:
            return {}

    def gunpacks(self):
        if not self.preset_manager or not self.selected:
            return []
        try:
            raw = self.preset_manager.get_current_gunpacks_for_preset(self.selected)
        except Exception:
            return []
        out = []
        for name, info in (raw or {}).items():
            if isinstance(info, dict):
                out.append({"name": name, "type": info.get("type", ""),
                            "size": info.get("size", 0),
                            "file_count": info.get("file_count", 1),
                            "target": info.get("target", "")})
            else:
                out.append({"name": name, "type": "zip", "size": 0,
                            "file_count": 1, "target": ""})
        return out

    # ------------------------------------------------------------------
    # 整合包 / 预设
    # ------------------------------------------------------------------
    @_locked
    def open_pack(self, pack_path: str):
        root = Path(pack_path).expanduser().resolve()
        tacz = root / "tacz"
        if not tacz.is_dir():
            raise ValueError("未找到 tacz 文件夹，请选择整合包根目录")
        with self.lock:
            self.close_pack()
            self.pack_path = root
            self.tacz_path = tacz
            self.db_path = self.settings.get_db_path(root)
            self.db_path.mkdir(parents=True, exist_ok=True)
            self.preset_manager = PresetManager(
                self.db_path, LogBus(self), tacz, pack_name=root.name)
            self.recent.add(str(root), root.name)
            self._init_online(self.db_path)
            self.preset_manager.load_all_presets(use_cache=True)
            if not self.preset_manager.presets:
                self._create_default_preset()
            if not self.selected:
                applied = [n for n, i in self.preset_manager.presets.items()
                           if i.get("applied")]
                self.selected = applied[0] if applied else next(
                    iter(self.preset_manager.presets), None)
            self._start_watcher()
            self._rev += 1
            self.add_log(f"整合包已加载：{root.name}", "SUCCESS")
            return self.state()

    def _create_default_preset(self):
        pm = self.preset_manager
        if not pm or "default" in pm.presets:
            return
        if not pm.create_preset("default", "v1.0.0"):
            return
        gunpacks = pm._get_gunpacks_from_folder(self.tacz_path)
        pm.presets["default"]["gunpacks"] = gunpacks
        pm.presets["default"]["applied"] = True
        pm.current_preset = "default"
        dp = Path(pm.presets["default"]["path"])
        with open(dp / "index.json", "w", encoding="utf-8") as f:
            json.dump({"name": "default", "version": "v1.0.0",
                       "gunpacks": gunpacks, "applied": True,
                       "incremental_count": 0}, f, indent=2, ensure_ascii=False)
        pm.save_cache()

    @_locked
    def close_pack(self):
        self._stop_watcher()
        self.pack_path = None
        self.tacz_path = None
        self.preset_manager = None
        self.selected = None
        self.last_plan = None
        self._init_online(paths.DEFAULT_DB_DIR)

    @_locked
    def select_preset(self, name: str):
        if not self.preset_manager or name not in self.preset_manager.presets:
            raise ValueError("预设不存在")
        self.selected = name
        self._rev += 1
        return self.state()

    def _refresh_after_mutation(self):
        self._rev += 1
        return self.state()

    @_locked
    def create_preset(self, name: str, version: str = "v1.0.0"):
        if not self.preset_manager:
            raise ValueError("请先加载整合包")
        if not self.preset_manager.create_preset(name, version):
            raise ValueError("创建预设失败，名称可能已存在或不合法")
        self.selected = name
        return self._refresh_after_mutation()

    @_locked
    def rename_preset(self, old: str, new: str):
        if not self.preset_manager:
            raise ValueError("请先加载整合包")
        if not self.preset_manager.rename_preset(old, new):
            raise ValueError("重命名失败")
        if self.online:
            try:
                self.online.rename_preset(old, new)
            except Exception:
                pass
        if self.selected == old:
            self.selected = new
        return self._refresh_after_mutation()

    @_locked
    def delete_preset(self, name: str):
        if not self.preset_manager:
            raise ValueError("请先加载整合包")
        if not self.preset_manager.delete_preset(name):
            raise ValueError("删除预设失败")
        if self.online:
            try:
                self.online.forget_preset(name)
            except Exception:
                pass
        if self.selected == name:
            self.selected = next(iter(self.preset_manager.presets), None)
        return self._refresh_after_mutation()

    @_locked
    def save_version(self, name: str, version: str):
        if not self.preset_manager or not self.preset_manager.update_preset_version(name, version):
            raise ValueError("版本保存失败")
        return self._refresh_after_mutation()

    @_locked
    def apply_preset(self, name: str, ctx=None):
        pm = self.preset_manager
        if not pm:
            raise ValueError("请先加载整合包")
        if not name or name not in pm.presets:
            raise ValueError("请选择预设")

        def progress(current, total, message=""):
            if ctx is not None:
                pct = (current / total * 100.0) if total else None
                ctx.progress(pct, phase="apply", message=message,
                             current=current, total=total)

        self._stop_watcher()
        try:
            ok = pm.apply_preset(name, progress)
        finally:
            self._start_watcher()
        if not ok:
            raise RuntimeError("预设应用失败，请查看日志")
        try:
            pm.update_preset_index(pm.current_preset or name, from_tacz=True)
        except Exception:
            pass
        self.selected = name
        self._rev += 1
        return {"ok": True, "state": self.state()}

    # ------------------------------------------------------------------
    # 监视器
    # ------------------------------------------------------------------
    def _start_watcher(self):
        if not self.tacz_path or self.watcher is not None:
            return
        try:
            self.watcher = TaczWatcher(
                self.tacz_path,
                lambda: self.emit("watchdog.changed", {"tacz": str(self.tacz_path)}),
                log_manager=None)
            self.watcher.start()
        except Exception as exc:
            self.watcher = None
            self.add_log(f"启动监视器失败: {exc}", "WARNING")

    def _stop_watcher(self):
        try:
            if self.watcher:
                self.watcher.stop()
        except Exception:
            pass
        self.watcher = None

    # ------------------------------------------------------------------
    # 在线
    # ------------------------------------------------------------------
    def _require_online(self):
        if not self.online:
            raise RuntimeError("在线模块不可用")
        return self.online

    @_locked
    def login(self, username: str, password: str, remember=True):
        data = self._require_online().login(username, password, remember=remember)
        self.settings.role = "developer"
        self.settings.save()
        self._rev += 1
        return {"account": data, "state": self.state()}

    @_locked
    def logout(self, forget=True):
        if self.online:
            self.online.logout(forget=forget)
        self.settings.role = "player"
        self.settings.save()
        self._rev += 1
        return self.state()

    @_locked
    def switch_role(self, role: str):
        target = "developer" if str(role).startswith("dev") else "player"
        if target == "developer" and self.online and not self.online.has_account():
            raise ValueError("需要先登录蓝奏账号")
        self.settings.role = target
        self.settings.save()
        self._rev += 1
        return self.state()

    def test_source(self, url: str, password: str = ""):
        return self._require_online().test_source(url, password)

    def cloud_browse(self, path: str = ""):
        return self._require_online().cloud_browse(path)

    def cloud_mkdir(self, parent: str, name: str):
        return self._require_online().cloud_mkdir(parent, name)

    def cloud_path(self, name: str):
        return {"path": self._require_online().cloud_path_of(name)
                if self.preset_manager else ""}

    def cloud_quota(self):
        data = self._require_online().account_quota()
        return {"quota": data}

    def account_state(self):
        if not self.online:
            return {"available": False, "account": {}}
        info = self.online.account_info()
        info.pop("uid", None)
        return {"available": True, "account": info}

    @_locked
    def bind_source(self, name: str, url: str, password: str = "", cloud_path=""):
        data = self._require_online().bind(
            name, url, password, cloud_path=cloud_path)
        self._rev += 1
        return {"source": data, "state": self.state()}

    @_locked
    def unbind_source(self, name: str):
        self._require_online().unbind(name)
        self._rev += 1
        return self.state()

    def _ref(self, name: str):
        info = self.preset_manager.presets[name]
        return PresetRef(name=name, path=info["path"],
                         root=info["path"], applied=bool(info.get("applied")))

    @_locked
    def check(self, name: str, ctx=None):
        online = self._require_online()
        if not self.preset_manager or name not in self.preset_manager.presets:
            raise ValueError("预设不存在")
        self.last_publish_plan = None
        plan = online.check(
            self._ref(name), role=self.role,
            on_phase=lambda text: ctx.progress(None, phase="check", message=text)
            if ctx else None)
        self.last_plan = plan
        self._rev += 1
        return {"plan": self._plan_summary(plan), "state": self.state()}

    def _plan_summary(self, plan):
        if plan is None:
            return None
        items = []
        for item in plan.items:
            items.append({
                "path": item.path,
                "name": item.display_name,
                "action": item.action,
                "label": diff.ACTION_LABELS.get(item.action, item.action),
                "size": item.size,
                "reason": item.reason,
                "checked": item.default_checked,
                "is_folder": item.is_folder,
            })
        return {
            "role": plan.role,
            "items": items,
            "counts": plan.counts(),
            "summary": plan.summary(),
            "version": plan.cloud_version,
            "generation": plan.cloud_generation,
            "offline": plan.offline,
            "source_error": plan.source_error,
            "clean": plan.is_clean,
        }

    @_locked
    def sync(self, name: str, selection=None, ctx=None):
        online = self._require_online()
        plan = self.last_plan
        if plan is None or not selection:
            if plan is None:
                raise ValueError("请先检查差异")
            selection = [i.path for i in plan.items
                         if i.action not in ("skip", "blocked")]
        if ctx:
            def on_progress(done, total, index, count, entry):
                pct = (done / total * 100.0) if total else None
                name = str((entry or {}).get("path") or "")
                ctx.progress(pct, phase="sync",
                             message=f"下载 {index}/{count}  {name}",
                             current=index, total=count)

            def on_item(index, count, entry, status):
                name = str((entry or {}).get("path") or "")
                ctx.progress(None, phase="sync",
                             message=f"{status} · {name}",
                             current=index, total=count)
        else:
            on_progress = on_item = None
        result = online.sync(self._ref(name), plan, selection,
                             on_item=on_item, on_progress=on_progress,
                             cancel=(lambda: ctx.cancelled) if ctx else None)
        self._rev += 1
        return {"result": self._serialize(result), "state": self.state()}

    @_locked
    def publish_plan(self, name: str, ctx=None):
        online = self._require_online()
        if self.role != "developer":
            raise PermissionError("只有开发者可以发布")
        plan = online.publish_plan(
            self._ref(name),
            on_phase=lambda text: ctx.progress(None, phase="publish", message=text)
            if ctx else None)
        self.last_publish_plan = plan
        self.last_plan = plan
        self._rev += 1
        return {"plan": self._plan_summary(plan), "state": self.state()}

    @_locked
    def publish(self, name: str, version: str, notes="", min_app="",
                selection=None, ctx=None):
        online = self._require_online()
        if self.role != "developer":
            raise PermissionError("只有开发者可以发布")
        plan = getattr(self, "last_publish_plan", None)
        if plan is None:
            raise ValueError("请先预览发布差异")
        if not selection:
            selection = [i.path for i in plan.items
                         if i.action not in ("skip", "blocked")]
        result = online.publish(
            self._ref(name), plan, selection, version=version,
            notes=notes, min_app=min_app,
            cancel=(lambda: ctx.cancelled) if ctx else None,
            on_progress=(lambda current, total, message="": ctx.progress(
                current / total * 100 if total else None, phase="publish",
                message=message, current=current, total=total))
            if ctx else None,
            role=self.role)
        self._rev += 1
        return {"result": self._serialize(result), "state": self.state()}

    @staticmethod
    def _serialize(value):
        if is_dataclass(value):
            return asdict(value)
        if hasattr(value, "__dict__"):
            return {k: v for k, v in value.__dict__.items()
                    if not k.startswith("_")}
        return value

    @_locked
    def set_database(self, path: str):
        target = Path(path).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        with self.lock:
            self.base_dir = target
            self.settings.bind_database(target)
            self.db_path = target
            if self.pack_path is not None:
                self.open_pack(str(self.pack_path))
            else:
                self._init_online(target)
            self._rev += 1
            self.add_log(f"数据库已切换：{target}", "SUCCESS")
            return self.state()

    def update_settings(self, patch: dict):
        allowed = {"animations", "online_auto_check", "online_sync_clean",
                   "online_publish_preview", "online_confirm_full",
                   "storage_mode"}
        for key, value in (patch or {}).items():
            if key in allowed:
                setattr(self.settings, key, value)
        self.settings.save()
        self._rev += 1
        return self.state()

    def recent_packs(self):
        return self.recent.get_all()[:12]

    def open_recent(self, path: str):
        return self.open_pack(path)
