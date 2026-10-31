"""一键更新 / 一键发布的共享业务逻辑。

UI（CTk 或 WebView）只负责收集参数、显示进度和收尾刷新；真正的
「收回已应用预设 → 检查/计划 → 下载/上传 → 自动替换」都在这里，
避免两个前端各写一套、行为慢慢分叉。
"""
from __future__ import annotations

import re
from typing import Any, Callable

from online import diff


def next_version(value: str) -> str:
    """把 v1.0.4 递增为 v1.0.5；无法解析时给一个安全的新版本。"""
    match = re.match(r"^[vV]?(\d+)\.(\d+)\.(\d+)", str(value or ""))
    if not match:
        return "v1.0.1"
    major, minor, patch = (int(x) for x in match.groups())
    return f"v{major}.{minor}.{patch + 1}"


class AutoActions:
    """无 UI 的一键操作执行器。

    service / preset_manager / settings 与两个前端共用；ref_for/apply
    由调用方注入（Tk 需要处理 watcher 和界面状态）。
    """

    def __init__(
        self,
        service,
        preset_manager,
        settings,
        *,
        ref_for: Callable[[str], Any],
        apply_preset: Callable[[str], bool],
        log: Callable[..., None] | None = None,
        cancel: Callable[[], bool] | None = None,
        progress: Callable[[float | None, str], None] | None = None,
    ):
        self.service = service
        self.manager = preset_manager
        self.settings = settings
        self.ref_for = ref_for
        self.apply_preset = apply_preset
        self.log = log or (lambda *a, **k: None)
        self.cancel = cancel or (lambda: False)
        self.progress = progress or (lambda _p, _m: None)

    # ------------------------------------------------------------------
    def bound_names(self, role: str) -> list[str]:
        if not self.service or not self.manager:
            return []
        names = []
        for name in self.manager.presets:
            try:
                bound = self.service.is_bound(name)
                cloud = bool(self.service.cloud_path_of(name))
            except Exception:
                bound, cloud = False, False
            if bound or (role == "developer" and cloud):
                names.append(name)
        return names

    def sync_one(self, name: str) -> dict:
        if self.cancel():
            raise RuntimeError("操作已取消")
        info = (self.manager.presets.get(name) or {})
        was_applied = bool(info.get("applied"))
        detached = False
        try:
            if was_applied:
                self.progress(None, f"收回已应用预设「{name}」…")
                if not self.manager.detach_preset(name):
                    raise RuntimeError("无法收回当前已应用的预设，已停止更新")
                detached = True
                info["applied"] = False
            ref = self.ref_for(name)
            if ref is None:
                raise ValueError("预设路径不可用")
            self.progress(None, f"{name} · 检查云端…")
            plan = self.service.check(
                ref, role="player",
                on_phase=lambda text: self.progress(None, f"{name} · {text}"))
            if getattr(plan, "offline", False):
                raise ValueError("云端暂时不可用，已保留本地预设，请稍后重试")
            actions = {diff.DOWNLOAD, diff.REPAIR}
            if bool(getattr(self.settings, "online_sync_clean", True)):
                actions.add(diff.ASK_DELETE_LOCAL)
            selection = [i.path for i in plan.items if i.action in actions]
            blocked = [i for i in plan.items if i.action == diff.BLOCKED]
            if blocked:
                self.log(f"一键更新：{len(blocked)} 个文件无法自动处理，已跳过",
                         "WARNING")
            if not selection:
                message = ("当前预设已是最新" if not plan.has_changes
                           else "没有可自动处理的安全项")
                self.log(f"一键更新：{message}", "SUCCESS", verbose=False)
                if detached:
                    self._restore(name)
                return {"name": name, "changed": 0, "message": message}

            self.progress(None, f"{name} · 下载 {len(selection)} 项…")

            def on_progress(done, total, index, count, entry):
                pct = (done / total * 100.0) if total else None
                label = str((entry or {}).get("path") or "")
                self.progress(pct, f"{name} · {index}/{count}  {label}")

            out = self.service.sync(
                ref, plan, selection,
                on_progress=on_progress,
                cancel=self.cancel)
            if getattr(out, "cancelled", False):
                raise RuntimeError("操作已取消")
            if was_applied:
                self.progress(None, f"重新应用「{name}」…")
                self._restore(name, required=True)
            failed = len(getattr(out, "failed", []) or [])
            message = (f"更新完成 · {len(selection)} 项"
                       + (" · 已重新替换" if was_applied else "")
                       + (f" · 失败 {failed} 项" if failed else ""))
            return {"name": name, "changed": len(selection),
                    "failed": failed, "message": message}
        except Exception:
            if detached:
                # 中途失败也要把 tacz 恢复成可用状态（可能包含已下载的部分）
                try:
                    self._restore(name)
                except Exception as exc:
                    self.log(f"更新失败后恢复 tacz 也失败：{exc}", "ERROR")
            raise

    def publish_one(self, name: str) -> dict:
        if self.cancel():
            raise RuntimeError("操作已取消")
        info = (self.manager.presets.get(name) or {})
        was_applied = bool(info.get("applied"))
        detached = False
        try:
            if was_applied:
                self.progress(None, f"收回已应用预设「{name}」…")
                if not self.manager.detach_preset(name):
                    raise RuntimeError("无法收回当前已应用的预设，已停止发布")
                detached = True
                info["applied"] = False
            ref = self.ref_for(name)
            if ref is None:
                raise ValueError("预设路径不可用")
            self.progress(None, f"{name} · 检查云端…")
            plan = self.service.publish_plan(
                ref, on_phase=lambda text: self.progress(None, f"{name} · {text}"))
            if getattr(plan, "offline", False):
                raise ValueError("云端读取失败，已拒绝用缓存计划发布")
            selection = [i.path for i in plan.items if i.action == diff.UPLOAD]
            extras = [i for i in plan.items if i.action == diff.DELETE_CLOUD]
            if extras:
                self.log(f"一键发布：云端多余 {len(extras)} 项已保留", "INFO")
            if not selection:
                message = ("已是最新，无需发布" if not extras
                           else "云端多余文件已保留，没有需要上传的内容")
                self.log(f"一键发布：{message}", "SUCCESS", verbose=False)
                if detached:
                    self._restore(name)
                return {"name": name, "changed": 0, "message": message}

            base = (getattr(plan, "cloud_version", "")
                    or (info.get("version") or ""))
            version = next_version(base)
            self.progress(None, f"{name} · 上传 {len(selection)} 项 · {version}")

            def on_progress(done, total, entry_name=""):
                pct = (done / total * 100.0) if total else None
                self.progress(pct, f"{name} · {entry_name or version}")

            out = self.service.publish(
                ref, plan, selection,
                version=version,
                notes=f"一键发布 · 上传 {len(selection)} 项",
                min_app="", role="developer",
                on_progress=on_progress,
                cancel=self.cancel)
            if not getattr(out, "ok", True):
                raise RuntimeError("发布未完成，请查看日志")
            if was_applied:
                self.progress(None, f"重新应用「{name}」…")
                self._restore(name, required=True)
            return {"name": name, "changed": len(selection),
                    "version": version,
                    "message": f"发布完成 · {version} · {len(selection)} 项"}
        except Exception:
            if detached:
                try:
                    self._restore(name)
                except Exception as exc:
                    self.log(f"发布失败后恢复 tacz 也失败：{exc}", "ERROR")
            raise

    def _restore(self, name: str, required: bool = False) -> None:
        try:
            ok = bool(self.apply_preset(name))
        except Exception:
            if required:
                raise
            ok = False
        if not ok and required:
            raise RuntimeError("无法重新应用预设，请查看日志")

    def run_all(self, kind: str, names: list[str]) -> dict:
        """kind = sync / publish；单个失败不阻塞其他预设。"""
        names = list(names)
        total = len(names)
        changed, unchanged, failed = [], [], []
        for index, name in enumerate(names, 1):
            if self.cancel():
                break
            self.progress((index - 1) / max(1, total) * 100.0,
                          f"{index}/{total} · {name}")
            try:
                out = self.sync_one(name) if kind == "sync" else self.publish_one(name)
                if out.get("changed"):
                    changed.append(name)
                else:
                    unchanged.append(name)
            except Exception as exc:
                failed.append((name, str(exc)))
                self.log(f"一键{'更新' if kind == 'sync' else '发布'}失败："
                         f"{name} · {exc}", "ERROR")
        self.progress(100.0, "完成")
        verb = "更新" if kind == "sync" else "发布"
        message = (f"{verb}完成 · {len(changed)} 个"
                   + (f" · 无变更 {len(unchanged)} 个" if unchanged else "")
                   + (f" · 失败 {len(failed)} 个" if failed else ""))
        return {"changed": changed, "unchanged": unchanged,
                "failed": failed, "message": message}
