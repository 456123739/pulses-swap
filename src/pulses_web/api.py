"""js_api 桥：只做校验、任务提交和结果信封，不直接做重活。"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .controller import AppController
from .events import EventBus, JobRunner


class ApiError(Exception):
    def __init__(self, code: str, message: str, detail: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail


def find_pack_root(paths) -> Path | None:
    """从拖入的文件/文件夹一路向上找包含 tacz 的整合包根目录。

    支持：整合包根、tacz 本身、tacz 内文件、整合包任意深层子文件/子目录。
    不做“拖入目录下必须有 tacz”的限制。
    """
    for raw in paths or []:
        try:
            path = Path(str(raw)).expanduser()
            if not path.exists():
                continue
            start = path if path.is_dir() else path.parent
            for candidate in (start, *start.parents):
                if (candidate / "tacz").is_dir():
                    return candidate
        except Exception:
            continue
    return None


class Api:
    """pywebview 只暴露 invoke / pick_folder / handle_drop 等少量方法。"""

    def __init__(self, controller: AppController, bus: EventBus,
                 jobs: JobRunner):
        self._controller = controller
        self._bus = bus
        self._jobs = jobs
        self._window = None
        self._lock = threading.RLock()
        self._methods: dict[str, Callable[[dict], Any]] = {
            "app.bootstrap": lambda p: self._controller.state(),
            "app.state": lambda p: self._controller.state(),
            "app.settings.update": lambda p: self._controller.update_settings(p),
            "app.recent": lambda p: self._controller.recent_packs(),
            "app.recent.open": lambda p: self._controller.open_recent(p["path"]),
            "app.role.switch": lambda p: self._controller.switch_role(p.get("role", "player")),
            "db.open": self._job("db.open"),
            "account.login": lambda p: self._controller.login(
                p.get("username", ""), p.get("password", ""),
                bool(p.get("remember", True))),
            "account.logout": lambda p: self._controller.logout(
                bool(p.get("forget", True))),
            "pack.open": self._job("pack.open"),
            "pack.close": self._job("pack.close"),
            "preset.select": lambda p: self._controller.select_preset(p["name"]),
            "preset.create": lambda p: self._controller.create_preset(
                p["name"], p.get("version", "v1.0.0")),
            "preset.rename": lambda p: self._controller.rename_preset(
                p["old"], p["new"]),
            "preset.delete": lambda p: self._controller.delete_preset(p["name"]),
            "preset.version": lambda p: self._controller.save_version(
                p["name"], p["version"]),
            "preset.details": lambda p: self._controller.preset_details(
                p["name"]),
            "preset.apply": self._job("preset.apply"),
            "preset.gunpacks": lambda p: {"gunpacks": self._controller.gunpacks()},
            "online.bind": lambda p: self._controller.bind_source(
                p["name"], p.get("url", ""), p.get("password", ""),
                p.get("cloud_path", "")),
            "online.add": self._job("online.add"),
            "pack.open_folder": lambda p: self._controller.open_folder(p["path"]),
            "pack.open_tacz": lambda p: self._controller.open_tacz(),
            "online.clear_cache": lambda p: self._controller.clear_cache(),
            "app.logs.clear": lambda p: self._clear_logs(),
            "app.selftest.report": lambda p: self.report_selftest(p),
            "online.test": lambda p: self._controller.test_source(
                p.get("url", ""), p.get("password", "")),
            "online.cloud.browse": lambda p: self._controller.cloud_browse(
                p.get("path", "")),
            "online.cloud.mkdir": lambda p: self._controller.cloud_mkdir(
                p.get("parent", ""), p.get("name", "")),
            "online.cloud.quota": lambda p: self._controller.cloud_quota(),
            "online.account.state": lambda p: self._controller.account_state(),
            "online.unbind": lambda p: self._controller.unbind_source(p["name"]),
            "online.check": self._job("online.check"),
            "online.auto.check": self._job("online.auto.check"),
            "online.sync": self._job("online.sync"),
            "online.sync.auto": self._job("online.sync.auto"),
            "online.publish.auto": self._job("online.publish.auto"),
            "online.sync.all": self._job("online.sync.all"),
            "online.publish.all": self._job("online.publish.all"),
            "online.publish.new": self._job("online.publish.new"),
            "online.publish.plan": self._job("online.publish.plan"),
            "online.publish.run": self._job("online.publish.run"),
            "job.cancel": lambda p: {"cancelled": self._jobs.cancel(p["jobId"])},
        }

    def bind_window(self, window):
        self._window = window

    # ------------------------------------------------------------------
    def invoke(self, method: str, params: dict | None = None) -> dict:
        handler = self._methods.get(str(method))
        if handler is None:
            return {"ok": False, "error": {
                "code": "UNKNOWN_METHOD", "message": f"未知操作: {method}",
                "detail": ""}}
        params = params if isinstance(params, dict) else {}
        try:
            data = handler(params)
            return {"ok": True, "data": data}
        except ApiError as exc:
            return {"ok": False, "error": {
                "code": exc.code, "message": exc.message, "detail": exc.detail}}
        except PermissionError as exc:
            return {"ok": False, "error": {
                "code": "FORBIDDEN", "message": str(exc), "detail": ""}}
        except (ValueError, FileNotFoundError) as exc:
            return {"ok": False, "error": {
                "code": "INVALID_INPUT", "message": str(exc), "detail": ""}}
        except Exception as exc:
            try:
                self._controller.add_log(
                    f"API {method} 失败: {exc}", "ERROR", verbose=True)
            except Exception:
                pass
            return {"ok": False, "error": {
                "code": getattr(exc, "code", "INTERNAL"),
                "message": str(exc) or "操作失败",
                "detail": ""}}

    def pick_folder(self) -> dict:
        if self._window is None:
            return {"ok": False, "error": {"code": "NO_WINDOW",
                                           "message": "窗口尚未就绪"}}
        try:
            import webview
            result = self._window.create_file_dialog(
                webview.FileDialog.FOLDER, allow_multiple=False)
            path = str(result[0]) if result else ""
            return {"ok": True, "data": {"path": path}}
        except Exception as exc:
            return {"ok": False, "error": {
                "code": "DIALOG_ERROR", "message": str(exc)}}

    def report_selftest(self, result: dict) -> dict:
        """CI 自测报告入口，只在 PULSES_WEB_SELFTEST 环境变量存在时生效。"""
        path = os.environ.get("PULSES_WEB_SELFTEST", "").strip()
        if not path:
            return {"ok": False, "error": {"code": "NO_SELFTEST",
                                           "message": "未启用自测"}}
        try:
            Path(path).write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        except Exception as exc:
            return {"ok": False, "error": {"code": "REPORT_ERROR",
                                           "message": str(exc)}}
        # 给报告写入留一点时间，然后关闭窗口，让 webview.start() 返回。
        threading.Timer(0.4, self._window.destroy).start()
        return {"ok": True}

    def handle_drop_pending(self) -> dict:
        """WebView2 原生文件拖入兜底：读取 pywebview 暂存的文件路径。

        某些 WebView2 冷启动时 DOM drop 事件没有绑定成功，前端会直接把
        dataTransfer.files 交给 chrome.webview，再调用这里。等待消息到达后
        统一走 handle_drop；没有路径时静默返回，避免和 DOM 正常路径重复报错。
        """
        import time
        try:
            from webview.dom import _dnd_state
        except Exception:
            return {"ok": False, "silent": True, "error": {
                "code": "NO_DND", "message": "当前后端没有拖入支持"}}
        paths = []
        for _ in range(24):
            if _dnd_state.get("paths"):
                paths = [p[1] for p in _dnd_state["paths"]]
                _dnd_state["paths"] = []
                break
            time.sleep(0.05)
        if not paths:
            return {"ok": False, "silent": True, "error": {
                "code": "NO_PATH", "message": "没有拿到可用的文件路径"}}
        return self.handle_drop(paths)

    def handle_drop(self, paths) -> dict:
        """由 Python DOM drop handler 调用；路径来自 pywebviewFullPath。"""
        if isinstance(paths, str):
            paths = [paths]
        clean = []
        for raw in paths or []:
            try:
                p = Path(str(raw)).expanduser()
                if p.exists():
                    clean.append(str(p.resolve()))
            except Exception:
                continue
        if not clean:
            self._bus.emit("dnd.error", {"message": "没有拿到可用的文件路径"})
            return {"ok": False, "error": {
                "code": "NO_PATH", "message": "没有拿到可用的文件路径"}}
        # 任意文件/文件夹拖入：向上找到包含 tacz 的整合包根目录
        pack = find_pack_root(clean)
        if pack is None:
            self._bus.emit("dnd.error", {"message": "拖入的路径里没有 tacz 文件夹"})
            return {"ok": False, "error": {
                "code": "NO_TACZ", "message": "拖入的路径里没有 tacz 文件夹"}}
        job = self._jobs.submit("pack.open",
                               lambda ctx: self._open_pack_job(str(pack), ctx),
                               cancelable=False)
        report = os.environ.get("PULSES_WEB_DROP_REPORT", "").strip()
        if report:
            threading.Thread(target=self._report_drop, args=(report,),
                             daemon=True).start()
        self._bus.emit("dnd.consumed", {"jobId": job, "path": str(pack)})
        return {"ok": True, "data": {"jobId": job, "path": str(pack)}}

    def _report_drop(self, path: str) -> None:
        """CI 拖入实测：等整合包真正加载后写结果；失败也写，便于 CI 定位。"""
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                state = self._controller.state()
                if state.get("pack", {}).get("loaded"):
                    Path(path).write_text(json.dumps({
                        "ok": True,
                        "pack": state.get("pack"),
                        "presets": [p.get("name") for p in state.get("presets", [])],
                    }, ensure_ascii=False, indent=2), encoding="utf-8")
                    return
            except Exception:
                pass
            time.sleep(0.25)
        try:
            Path(path).write_text(json.dumps({
                "ok": False, "error": "拖入后 20 秒内没有加载整合包",
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _clear_logs(self):
        with self._controller.lock:
            self._controller.logs.clear()
            self._controller._rev += 1
            return self._controller.state()

    # ------------------------------------------------------------------
    # Job wrappers
    # ------------------------------------------------------------------
    def _job(self, method: str):
        def run(params: dict):
            if method == "pack.open":
                path = params.get("path", "")
                if not path:
                    raise ValueError("缺少整合包路径")
                job = self._jobs.submit("打开整合包",
                                       lambda ctx: self._open_pack_job(path, ctx),
                                       cancelable=False)
            elif method == "pack.close":
                job = self._jobs.submit("关闭整合包",
                                       lambda ctx: self._controller.close_pack())
            elif method == "online.add":
                job = self._jobs.submit("从云端添加",
                                       lambda ctx: self._controller.add_from_cloud(
                                           params.get("url", ""),
                                           params.get("password", ""),
                                           params.get("name", ""), ctx))
            elif method == "preset.apply":
                name = params.get("name", "")
                job = self._jobs.submit("应用预设",
                                       lambda ctx: self._controller.apply_preset(name, ctx),
                                       cancelable=False)
            elif method == "online.check":
                name = params.get("name", "")
                job = self._jobs.submit("检查更新",
                                       lambda ctx: self._controller.check(name, ctx))
            elif method == "online.auto.check":
                job = self._jobs.submit("启动检查",
                                       lambda ctx: self._controller.auto_check(ctx))
            elif method == "online.sync":
                name = params.get("name", "")
                selection = params.get("selection") or []
                job = self._jobs.submit("同步预设",
                                       lambda ctx: self._controller.sync(
                                           name, selection, ctx))
            elif method == "online.sync.auto":
                name = params.get("name", "")
                job = self._jobs.submit("一键更新",
                                       lambda ctx: self._controller.sync_auto(
                                           name, ctx))
            elif method == "online.publish.auto":
                name = params.get("name", "")
                job = self._jobs.submit("一键发布",
                                       lambda ctx: self._controller.publish_auto(
                                           name, ctx))
            elif method == "online.sync.all":
                job = self._jobs.submit("一键更新全部",
                                       lambda ctx: self._controller.sync_all_auto(ctx))
            elif method == "online.publish.all":
                job = self._jobs.submit("一键发布全部",
                                       lambda ctx: self._controller.publish_all_auto(ctx))
            elif method == "online.publish.new":
                name = params.get("name", "")
                job = self._jobs.submit("上传到云端",
                                       lambda ctx: self._controller.publish_new(
                                           name, ctx))
            elif method == "online.publish.plan":
                name = params.get("name", "")
                job = self._jobs.submit("生成发布计划",
                                       lambda ctx: self._controller.publish_plan(name, ctx))
            elif method == "db.open":
                path = params.get("path", "")
                if not path:
                    raise ValueError("缺少数据库路径")
                job = self._jobs.submit("打开数据库",
                                       lambda ctx: {"state": self._controller.set_database(path)},
                                       cancelable=False)
            elif method == "online.publish.run":
                name = params.get("name", "")
                job = self._jobs.submit("发布预设",
                                       lambda ctx: self._controller.publish(
                                           name, params.get("version", ""),
                                           params.get("notes", ""),
                                           params.get("min_app", ""),
                                           params.get("selection") or [], ctx))
            else:
                raise ValueError("不支持的任务")
            return {"jobId": job, "cancelable": self._jobs.cancelable(job)}
        return run

    def _open_pack_job(self, path, ctx):
        ctx.progress(None, phase="pack", message="正在扫描整合包…")
        state = self._controller.open_pack(path)
        ctx.progress(100, phase="pack", message="整合包已加载", force=True)
        self._bus.emit("state.changed", {"state": state})
        return {"state": state}
