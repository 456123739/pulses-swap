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
                previous_manifest: dict | None = None,
                on_item=None, on_progress=None) -> PublishResult:
        """安全发布：只上传 → 换 manifest → 最后清理不再引用的旧文件。

        蓝奏遇到同名文件会自动改名，所以上传后把**实际文件名**写进 manifest
        的 ``cloud`` 字段。这样上传失败/取消时旧 manifest 和旧文件都完好，
        玩家不会看到“manifest 引用了已被删掉的文件”这种线上事故。
        """
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
            cloud_list = self.account.list_files(folder_id)
            cloud_files = {f["name"].lower(): f for f in cloud_list}
        except OnlineError as exc:
            result.failed.append(("", str(exc)))
            return result

        total_bytes = sum(int(i.size or 0) for i in uploads)
        done_bytes = 0
        packed: dict[str, int] = {}
        uploaded_names: dict[str, str] = {}
        uploaded_ids: list = []

        try:
            for index, item in enumerate(uploads, start=1):
                self._check_cancel()
                if on_item is not None:
                    on_item(index, len(uploads), item.path, "start")
                try:
                    uploaded = self._upload_one(item, folder_id, pack_dir,
                                                done_bytes, total_bytes,
                                                on_progress)
                    key = item.path.lower()
                    uploaded_names[key] = uploaded["name"]
                    packed[key] = uploaded["size"]
                    if uploaded.get("id"):
                        uploaded_ids.append(uploaded["id"])
                    result.uploaded.append(item.path)
                    result.bytes_uploaded += uploaded["size"]
                    cloud_files[str(uploaded["name"]).lower()] = uploaded
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
        except CancelledError:
            # 取消：已经传上去的新文件没人引用，删掉，旧版本原样保留
            self._drop_uploads(uploaded_ids)
            raise

        if result.failed:
            # 不换 manifest；把这次新传的文件清掉，线上保持完整旧版
            self._drop_uploads(uploaded_ids)
            self._log("有文件上传失败，本次不更新云端 manifest（线上保持旧版）",
                      "WARNING")
            return result

        self._check_cancel()
        try:
            files = self._build_files(entries, plan, packed, uploaded_names,
                                      {i.path.lower() for i in deletes})
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
            self._drop_uploads(uploaded_ids)
            return result

        try:
            self._upload_manifest(manifest, folder_id, pack_dir, cloud_files,
                                  previous_manifest=previous_manifest,
                                  cloud_list=cloud_list)
        except OnlineError as exc:
            result.failed.append((MANIFEST_NAME, str(exc)))
            self._log(f"上传 manifest 失败，已尝试恢复旧 manifest：{exc}", "ERROR")
            self._drop_uploads(uploaded_ids)
            return result

        # manifest 已提交：现在可以安全清理不再被引用的旧文件
        self._delete_stale(cloud_list, uploaded_ids, previous_manifest,
                           files, deletes, result)

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

    def _drop_uploads(self, ids) -> None:
        """清掉本次已上传但还没被 manifest 引用的文件（失败/取消时）。"""
        for file_id in ids:
            try:
                self.account.delete_file(file_id)
            except OnlineError as exc:
                self._log(f"清理未引用的上传文件失败：{exc}", "WARNING")

    def _delete_stale(self, cloud_list: list[dict], uploaded_ids,
                      previous_manifest, files: list[dict], deletes,
                      result) -> None:
        """manifest 提交后，删掉旧版本留下的文件（按 id 删，能清掉同名重复）。

        只动「旧 manifest 引用过的名字 / 本次删掉的名字 / 本次上传的原始名字」，
        用户在文件夹里放的其它文件不会被误删。
        """
        keep = {str(f.get("cloud") or f.get("path") or "").lower()
                for f in files}
        keep.add(MANIFEST_NAME.lower())
        old_names = set()
        for old in (previous_manifest or {}).get("files") or []:
            old_names.add(str(old.get("cloud") or old.get("path") or "").lower())
        for item in deletes:
            entry = item.cloud or {}
            old_names.add(str(entry.get("cloud") or entry.get("path")
                              or item.path).lower())
        uploaded_ids = set(uploaded_ids or [])
        seen = set()
        for f in cloud_list:
            file_id = f.get("id")
            name = str(f.get("name") or "")
            low = name.lower()
            if file_id in uploaded_ids or low in keep or low not in old_names:
                continue
            if file_id in seen:
                continue
            seen.add(file_id)
            try:
                if self.account.delete_file(file_id):
                    result.deleted.append(name)
            except OnlineError as exc:
                self._log(f"清理旧文件 {name} 失败：{exc}", "WARNING")

    # ------------------------------------------------------------------
    def _cloud_name_for(self, entry: dict, name: str) -> str:
        """给每次上传一个带内容指纹的唯一云端文件名。

        蓝奏对同名文件既可能改名、也可能直接存成两条同名记录；只用原文件名
        会让玩家下到旧的那一条。带 sha 的名字永远唯一，manifest 指向它。
        """
        digest = str(entry.get("sha256") or "")[:8].lower()
        stem, ext = os.path.splitext(name)
        if digest:
            return f"{stem}.{digest}{ext}"
        return f"{stem}.pulses{ext}"

    def _upload_one(self, item: diff.DiffItem, folder_id: int, pack_dir: str,
                    base_done: int, total_bytes: int, on_progress) -> dict:
        entry = item.local or {}
        name = item.path
        cloud_name = self._cloud_name_for(entry, name)
        path = self._prepare_upload(entry, pack_dir, cloud_name)

        def progress(done: int, _total: int) -> None:
            if on_progress is not None:
                on_progress(base_done + min(done, item.size or done),
                            total_bytes, name)

        info = self.account.upload(path, folder_id, progress=progress,
                                   cancel=self.cancel)
        returned = str(info.get("name") or cloud_name)
        return {"id": info.get("id"), "name": returned,
                "size": os.path.getsize(path)}

    def _prepare_upload(self, entry: dict, pack_dir: str,
                        cloud_name: str | None = None) -> str:
        """文件夹型先确定性打包，返回可上传的文件路径。

        cloud_name 是这次要用的云端文件名（带内容指纹），保证同名旧文件不会
        让玩家下错版本。
        """
        cloud_name = cloud_name or entry.get("path") or "upload.bin"
        if entry.get("type") == "folder":
            source = os.path.join(self.local_root,
                                  entry.get("target") or "")
            if not os.path.isdir(source):
                raise SourceError(f"找不到本地文件夹：{entry.get('target')}")
            archive = os.path.join(pack_dir, cloud_name)
            self._log(f"打包 {entry.get('target')} …", "PROCESS")
            packing.pack_folder(source, archive, should_stop=self.cancel)
            return archive
        source = os.path.join(self.local_root, entry.get("path") or "")
        if not os.path.isfile(source):
            raise SourceError(f"找不到本地文件：{entry.get('path')}")
        if not is_allowed_upload(cloud_name):
            raise SourceError(
                f"网盘不接受这个扩展名：{entry.get('path')}",
                hint="把这个文件放进一个 .zip，或改成 .txt 再发布。")
        target = os.path.join(pack_dir, cloud_name)
        if os.path.abspath(target) != os.path.abspath(source):
            shutil.copyfile(source, target)
            return target
        return source

    def _build_files(self, entries: list[dict], plan: diff.Plan,
                     packed: dict[str, int],
                     uploaded_names: dict[str, str],
                     deleted_paths: set[str] | None = None) -> list[dict]:
        """按“发布完成时云端真实有什么”拼 files 数组。

        - 本次上传成功的：用本地条目 + 网盘实际文件名（cloud）
        - 没上传/没勾选的：沿用旧 manifest 里的云端条目
        - 云端没有、这次也没上传的：不写进 manifest
        """
        local_by = {str(e.get("path", "")).lower(): e for e in entries}
        deleted_paths = deleted_paths or set()
        out: list[dict] = []
        for item in plan.items:
            key = item.path.lower()
            if key in deleted_paths:
                continue                      # 这次明确删掉的，不能再写进 manifest
            if key in uploaded_names:
                entry = dict(local_by.get(key) or item.local or {})
                entry = {k: v for k, v in entry.items() if not k.startswith("_")}
                cloud_name = uploaded_names[key]
                if cloud_name.lower() != str(entry.get("path", "")).lower():
                    entry["cloud"] = cloud_name
                if key in packed:
                    entry["packed_size"] = packed[key]
                out.append(entry)
            elif item.cloud:
                out.append({k: v for k, v in item.cloud.items()
                            if not k.startswith("_")})
            # local-only 且未上传 → 不在云端，manifest 里不能宣告它
        return out

    def _upload_manifest(self, manifest: dict, folder_id: int, pack_dir: str,
                         cloud_files: dict,
                         previous_manifest: dict | None = None,
                         cloud_list: list[dict] | None = None) -> None:
        from .manifest import save
        target = os.path.join(pack_dir, MANIFEST_NAME)
        save(manifest, target)
        for entry in cloud_list or []:
            if str(entry.get("name") or "").lower() == MANIFEST_NAME.lower():
                if not self.account.delete_file(entry["id"]):
                    raise SourceError("旧 manifest 删除失败")
        cloud_files.pop(MANIFEST_NAME.lower(), None)
        try:
            info = self.account.upload(target, folder_id)
            returned = str(info.get("name") or "")
            if returned and returned.lower() != MANIFEST_NAME.lower():
                try:
                    if info.get("id"):
                        self.account.delete_file(info["id"])
                except OnlineError:
                    pass
                raise SourceError("manifest 上传后被改名，云端可能残留同名文件")
        except OnlineError:
            # 新 manifest 没上去：把旧的原样传回去，别让云端“没有 manifest”
            if previous_manifest is not None:
                self._restore_manifest(previous_manifest, folder_id, pack_dir,
                                       cloud_files)
            raise
        self._log("云端 manifest 已更新", "SUCCESS")

    def _restore_manifest(self, previous: dict, folder_id: int, pack_dir: str,
                          cloud_files: dict) -> None:
        """发布失败时恢复旧 manifest（旧文件还在，玩家仍可下载旧版）。"""
        try:
            from .manifest import save
            target = os.path.join(pack_dir, MANIFEST_NAME)
            save(previous, target)
            info = self.account.upload(target, folder_id)
            cloud_files[str(info.get("name") or MANIFEST_NAME).lower()] = info
            self._log("已恢复旧 manifest", "WARNING")
        except Exception as exc:                    # noqa: BLE001
            self._log(f"恢复旧 manifest 失败：{exc}", "ERROR")
