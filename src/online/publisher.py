"""
发布器：把本地预设同步到云端。

顺序很重要——**manifest 永远最后传**：

    ① 逐级确保文件夹存在
    ② 删除云端多余（可选）
    ③ 逐个上传变化的文件（文件夹型先打包）
    ④ 全部成功后才上传新 manifest（generation + 1）
    ⑤ 取分享链接

任何一步失败都不传 manifest，线上仍然是完整的旧版本；玩家不会看到半新半旧。
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field

from . import diff, packing
from .errors import CancelledError, OnlineError, SourceError
from .manifest import normalize
from .provider_lanzou import MANIFEST_NAME, format_size
from .provider_lanzou_account import is_allowed_upload


@dataclass
class PublishResult:
    ok: bool = False
    version: str = ""
    generation: int = 0
    uploaded: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    bytes_uploaded: int = 0
    share_url: str = ""
    share_password: str = ""
    cancelled: bool = False
    manifest: dict = field(default_factory=dict)

    def summary(self) -> str:
        bits = []
        if self.uploaded:
            bits.append(f"上传 {len(self.uploaded)}")
        if self.deleted:
            bits.append(f"删除云端 {len(self.deleted)}")
        if self.failed:
            bits.append(f"失败 {len(self.failed)}")
        return " · ".join(bits) or "没有变化"


class Publisher:
    """用已登录的账号把差异推到云端。"""

    def __init__(self, account, staging_dir: str, local_root: str, *,
                 log=None, cancel=None):
        self.account = account
        self.staging_dir = os.path.abspath(staging_dir)
        self.local_root = os.path.abspath(local_root)
        self.log = log
        self.cancel = cancel

    # ------------------------------------------------------------------
    def _log(self, message: str, level: str = "INFO", **kwargs) -> None:
        if not self.log:
            return
        try:
            self.log(message, level, **kwargs)
            return
        except TypeError:
            pass
        try:
            self.log(message, level)
            return
        except TypeError:
            pass
        try:
            self.log(message)
        except Exception:
            pass

    def _cancelled(self) -> bool:
        return bool(self.cancel and self.cancel())

    def _check_cancel(self) -> None:
        if self._cancelled():
            raise CancelledError("发布已取消")

    # ------------------------------------------------------------------
    def publish(self, *, folder_id: int, plan: diff.Plan, entries: list[dict],
                selection, version: str, notes: str = "", min_app: str = "",
                previous_generation: int = 0, name: str = "",
                on_item=None, on_progress=None) -> PublishResult:
        """执行发布。entries 是本地全量条目（不是只有变化的那些）。"""
        result = PublishResult(version=str(version or ""),
                               generation=int(previous_generation) + 1)
        items = plan.selected_items(selection)
        uploads = [i for i in items if i.action == diff.UPLOAD]
        deletes = [i for i in items if i.action == diff.DELETE_CLOUD]

        os.makedirs(self.staging_dir, exist_ok=True)
        pack_dir = os.path.join(self.staging_dir, "pack")
        shutil.rmtree(pack_dir, ignore_errors=True)
        os.makedirs(pack_dir, exist_ok=True)

        try:
            cloud_files = {f["name"].lower(): f
                           for f in self.account.list_files(folder_id)}
        except OnlineError as exc:
            result.failed.append(("", str(exc)))
            return result

        total_bytes = sum(int(i.size or 0) for i in uploads)
        done_bytes = 0
        packed: dict[str, int] = {}

        # ---------- ① 删除云端多余 ----------
        for item in deletes:
            self._check_cancel()
            existing = cloud_files.get(item.path.lower())
            if existing is None:
                result.deleted.append(item.path)
                continue
            try:
                if self.account.delete_file(existing["id"]):
                    result.deleted.append(item.path)
                    cloud_files.pop(item.path.lower(), None)
                else:
                    result.failed.append((item.path, "网盘拒绝删除"))
            except OnlineError as exc:
                result.failed.append((item.path, str(exc)))

        # ---------- ② 上传 ----------
        for index, item in enumerate(uploads, start=1):
            self._check_cancel()
            if on_item is not None:
                on_item(index, len(uploads), item.path, "start")
            try:
                uploaded = self._upload_one(item, folder_id, pack_dir,
                                            cloud_files, done_bytes,
                                            total_bytes, on_progress)
                packed[item.path] = uploaded["size"]
                result.uploaded.append(item.path)
                result.bytes_uploaded += uploaded["size"]
                cloud_files[item.path.lower()] = uploaded
                self._log(f"已上传 {item.path}（{format_size(uploaded['size'])}）",
                          "SUCCESS")
                phase = "done"
            except CancelledError:
                raise
            except OnlineError as exc:
                result.failed.append((item.path, str(exc)))
                self._log(f"上传失败 {item.path}：{exc}", "ERROR")
                phase = "error"
            done_bytes += int(item.size or 0)
            if on_item is not None:
                on_item(index, len(uploads), item.path, phase)
            if on_progress is not None:
                on_progress(done_bytes, total_bytes, item.path)

        # 有失败就不换 manifest：线上保持完整旧版
        if result.failed:
            self._log("有文件上传失败，本次不更新云端 manifest", "WARNING")
            return result

        # ---------- ③ manifest ----------
        self._check_cancel()
        try:
            files = self._build_files(entries, plan, packed)
            manifest = normalize({
                "name": name or plan.cloud_name,
                "version": result.version,
                "generation": result.generation,
                "min_app": min_app,
                "notes": notes,
                "files": files,
            })
        except OnlineError as exc:
            result.failed.append((MANIFEST_NAME, str(exc)))
            return result

        try:
            self._upload_manifest(manifest, folder_id, pack_dir, cloud_files)
        except CancelledError:
            raise
        except OnlineError as exc:
            result.failed.append((MANIFEST_NAME, str(exc)))
            self._log(f"上传 manifest 失败：{exc}", "ERROR")
            return result

        # ---------- ④ 分享 ----------
        try:
            share = self.account.folder_share(folder_id)
            result.share_url = share.get("url", "")
            result.share_password = share.get("password", "")
        except OnlineError as exc:
            self._log(f"取分享链接失败：{exc}", "WARNING")

        result.manifest = manifest
        result.ok = True
        self._log(f"发布完成：v{result.version}（generation "
                  f"{result.generation}，{len(files)} 个文件）", "SUCCESS")
        return result

    # ------------------------------------------------------------------
    def _upload_one(self, item: diff.DiffItem, folder_id: int, pack_dir: str,
                    cloud_files: dict, base_done: int, total_bytes: int,
                    on_progress) -> dict:
        entry = item.local or {}
        name = item.path
        existing = cloud_files.get(name.lower())
        if existing is not None:
            # 蓝奏遇到同名会自动改名成 name(1).zip，必须先删掉旧的
            if not self.account.delete_file(existing["id"]):
                raise SourceError(f"云端同名文件删除失败：{name}",
                                  hint="去网页版手动删掉同名文件后重试。")
            cloud_files.pop(name.lower(), None)

        path = self._prepare_upload(entry, pack_dir)

        def progress(done: int, _total: int) -> None:
            if on_progress is not None:
                on_progress(base_done + min(done, item.size or done),
                            total_bytes, name)

        info = self.account.upload(path, folder_id, progress=progress,
                                   cancel=self.cancel)
        returned = str(info.get("name") or "")
        if returned and returned.lower() != name.lower():
            try:
                if info.get("id"):
                    self.account.delete_file(info["id"])
            except OnlineError:
                pass
            raise SourceError(
                f"网盘把 {name} 改名成了 {returned}",
                hint="云端已有同名文件没删干净，刷新后重试。")
        return {"id": info.get("id"), "name": name,
                "size": os.path.getsize(path)}

    def _prepare_upload(self, entry: dict, pack_dir: str) -> str:
        """文件夹型先确定性打包，返回可上传的文件路径。"""
        if entry.get("type") == "folder":
            source = os.path.join(self.local_root,
                                  entry.get("target") or "")
            if not os.path.isdir(source):
                raise SourceError(f"找不到本地文件夹：{entry.get('target')}")
            archive = os.path.join(pack_dir, entry["path"])
            self._log(f"打包 {entry.get('target')} …", "PROCESS")
            packing.pack_folder(source, archive, should_stop=self.cancel)
            return archive
        source = os.path.join(self.local_root, entry.get("path") or "")
        if not os.path.isfile(source):
            raise SourceError(f"找不到本地文件：{entry.get('path')}")
        if not is_allowed_upload(entry.get("path") or ""):
            raise SourceError(
                f"网盘不接受这个扩展名：{entry.get('path')}",
                hint="把这个文件放进一个 .zip，或改成 .txt 再发布。")
        return source

    def _build_files(self, entries: list[dict], plan: diff.Plan,
                     packed: dict[str, int]) -> list[dict]:
        """拼出要写进 manifest 的 files 数组。

        没上传的文件夹（内容没变）沿用云端已有的 packed_size，
        否则用逻辑体积兜底——总比显示 0 强。
        """
        cloud_index = {i.path.lower(): (i.cloud or {}) for i in plan.items}
        out = []
        for entry in entries:
            item = {k: v for k, v in entry.items() if not k.startswith("_")}
            path = item["path"]
            if path in packed:
                item["packed_size"] = packed[path]
            else:
                previous = cloud_index.get(path.lower(), {})
                if previous.get("sha256") == item.get("sha256") \
                        and previous.get("packed_size"):
                    item["packed_size"] = int(previous["packed_size"])
            out.append(item)
        return out

    def _upload_manifest(self, manifest: dict, folder_id: int, pack_dir: str,
                         cloud_files: dict) -> None:
        from .manifest import save
        target = os.path.join(pack_dir, MANIFEST_NAME)
        save(manifest, target)
        existing = cloud_files.get(MANIFEST_NAME.lower())
        if existing is not None:
            if not self.account.delete_file(existing["id"]):
                raise SourceError("旧 manifest 删除失败")
        info = self.account.upload(target, folder_id)
        returned = str(info.get("name") or "")
        if returned and returned.lower() != MANIFEST_NAME.lower():
            try:
                if info.get("id"):
                    self.account.delete_file(info["id"])
            except OnlineError:
                pass
            raise SourceError("manifest 上传后被改名，云端可能残留同名文件")
        self._log("云端 manifest 已更新", "SUCCESS")
