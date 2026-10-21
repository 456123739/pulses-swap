"""
下载器：把云端缺的文件拉进暂存区，并当场校验。

约定：
  · 只下载，不碰正式目录 —— 正式目录的改动全部交给 :mod:`updater`
  · 每个文件下载完立刻校验（zip/file 比 sha256，folder 比树摘要）
  · 单个文件失败不影响其它文件，最后汇总
  · 蓝奏不支持断点续传，失败就整包重来（换一条链路）
"""
from __future__ import annotations

import os
import shutil
import time

from .errors import (CancelledError, DiskSpaceError, IntegrityError,
                     OnlineError, SourceError)
from .hashing import sha256_file, tree_digest
from .packing import unpack_to
from .provider_lanzou import format_size

RESERVE_BYTES = 64 * 1024 * 1024


class ItemResult:
    """一个条目的下载结果。"""

    __slots__ = ("entry", "ok", "staged", "bytes", "error", "error_obj")

    def __init__(self, entry: dict, *, ok: bool = False, staged: str = "",
                 bytes_: int = 0, error: str = "",
                 error_obj: OnlineError | None = None):
        self.entry = entry
        self.ok = ok
        self.staged = staged
        self.bytes = bytes_
        self.error = error
        self.error_obj = error_obj

    def __repr__(self) -> str:                       # pragma: no cover
        state = "ok" if self.ok else "fail"
        return f"<ItemResult {state} {self.entry.get('path')} {self.error}>"


def free_space(path: str) -> int:
    """目录所在卷的剩余字节数。"""
    probe = os.path.abspath(path)
    while not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    try:
        return shutil.disk_usage(probe).free
    except OSError:
        return 0


def ensure_space(path: str, needed: int) -> None:
    """空间不够直接拒绝，别让用户下到一半失败。"""
    available = free_space(path)
    if not available:
        return
    if needed + RESERVE_BYTES > available:
        raise DiskSpaceError(
            f"磁盘空间不足：需要 {format_size(needed + RESERVE_BYTES)}，"
            f"只剩 {format_size(available)}",
            hint="清理磁盘或换一个数据目录后重试。")


class Downloader:
    """把一组 manifest 条目下载到 staging。"""

    def __init__(self, share, staging_dir: str, *, log=None, cancel=None):
        self.share = share
        self.staging_dir = os.path.abspath(staging_dir)
        self.log = log
        self.cancel = cancel
        self.new_dir = os.path.join(self.staging_dir, "new")
        self.archive_dir = os.path.join(self.staging_dir, "archive")
        self._listing: dict[str, dict] = {}

    # ------------------------------------------------------------------
    def _is_cancelled(self) -> bool:
        return bool(self.cancel and self.cancel())

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

    @staticmethod
    def _as_entry(item) -> dict:
        """既接受 manifest 条目，也接受 diff.DiffItem（取它的 cloud 侧）。"""
        if isinstance(item, dict):
            return item
        entry = getattr(item, "cloud", None)
        if isinstance(entry, dict):
            return entry
        raise TypeError(f"无法识别的条目: {item!r}")

    def prepare(self, entries) -> None:
        """列一次云端文件，建立 name → 文件信息 的索引。"""
        listing = self.share.list_files()
        self._listing = {str(f["name"]).lower(): f for f in listing}
        missing = [e["path"] for e in entries
                   if self._cloud_name(e) not in self._listing]
        if missing:
            raise SourceError(
                f"云端缺少 {len(missing)} 个文件",
                detail=", ".join(missing[:5]),
                hint="云端文件被改动过，请发布者重新发布。")

    @staticmethod
    def _cloud_name(entry: dict) -> str:
        """云端实际文件名（同名被改名时 manifest 会带 cloud 字段）。"""
        return str(entry.get("cloud") or entry.get("path") or "").lower()

    def _target_of(self, entry: dict) -> str:
        if entry.get("type") == "folder":
            return os.path.join(self.new_dir, entry["target"])
        return os.path.join(self.new_dir, entry["path"])

    def _archive_of(self, entry: dict) -> str:
        return os.path.join(self.archive_dir, entry["path"])

    def _verify(self, entry: dict) -> None:
        """校验暂存内容与 manifest 是否一致。"""
        expect = str(entry.get("sha256") or "").lower()
        if not expect:
            raise IntegrityError("manifest 里没有 sha256，无法校验",
                                 detail=entry.get("path", ""))
        if entry.get("type") == "folder":
            actual, _size, _count = tree_digest(self._target_of(entry))
        else:
            actual = sha256_file(self._target_of(entry))
        if actual != expect:
            raise IntegrityError(
                f"校验不通过：{entry.get('path')}",
                detail=f"期望 {expect[:16]}…，实际 {actual[:16]}…",
                hint="已自动重下一次；仍失败说明云端文件损坏。")

    def _fetch_one(self, entry: dict, index: int, total: int,
                   on_progress=None, base_done: int = 0,
                   total_bytes: int = 0) -> ItemResult:
        path = str(entry["path"])
        info = self._listing.get(self._cloud_name(entry))
        if info is None:
            return ItemResult(entry, error=f"云端缺少 {path}")

        expected = int(entry.get("packed_size") or 0) or int(info["size_bytes"])
        dest = self._target_of(entry)
        is_folder = entry.get("type") == "folder"
        download_target = self._archive_of(entry) if is_folder else dest
        os.makedirs(os.path.dirname(download_target), exist_ok=True)

        def progress(done: int, _total: int) -> None:
            if on_progress is not None:
                on_progress(base_done + min(done, expected or done),
                            total_bytes, index, total, entry)

        attempt = 0
        last: OnlineError | None = None
        while attempt < 2:
            attempt += 1
            try:
                written = self.share.download(
                    info["file_id"], download_target,
                    raw_id=info.get("raw_id"),
                    progress=progress, cancel=self.cancel,
                    expected_size=expected)
                packed_expect = str(entry.get("packed_sha256") or "").lower()
                if packed_expect:
                    packed_actual = sha256_file(download_target)
                    if packed_actual != packed_expect:
                        raise IntegrityError(
                            f"传输包校验不通过：{path}",
                            detail=f"期望 {packed_expect[:16]}…，"
                                   f"实际 {packed_actual[:16]}…",
                            hint="已自动重下一次；仍失败说明云端文件损坏。")
                if is_folder:
                    if os.path.isdir(dest):
                        shutil.rmtree(dest, ignore_errors=True)
                    unpack_to(download_target, dest,
                              expected_size=int(entry.get("size") or 0),
                              should_stop=self.cancel)
                    try:
                        os.unlink(download_target)
                    except OSError:
                        pass
                self._verify(entry)
                return ItemResult(entry, ok=True, staged=dest, bytes_=written)
            except CancelledError:
                raise
            except IntegrityError as exc:
                last = exc
                self._log(f"校验失败，重下：{path}", "WARNING")
                for candidate in (download_target, dest):
                    _remove(candidate)
                if attempt >= 2:
                    break
            except OnlineError as exc:
                last = exc
                _remove(download_target)
                if attempt >= 2 or not exc.retryable:
                    break
                time.sleep(0.6)
        return ItemResult(entry, error=str(last or "下载失败"), error_obj=last)

    # ------------------------------------------------------------------
    def run(self, entries, *, on_item=None, on_progress=None) -> list[ItemResult]:
        """下载全部条目。entries 里的 packed_size / size 用于进度与空间预估。"""
        entries = [self._as_entry(item) for item in entries]
        if not entries:
            return []
        self.prepare(entries)
        os.makedirs(self.new_dir, exist_ok=True)
        os.makedirs(self.archive_dir, exist_ok=True)

        total_bytes = sum(int(e.get("packed_size") or e.get("size") or 0)
                          for e in entries)
        ensure_space(self.staging_dir, total_bytes)

        results: list[ItemResult] = []
        done_bytes = 0
        for index, entry in enumerate(entries, start=1):
            if self._is_cancelled():
                raise CancelledError("同步已取消")
            if on_item is not None:
                on_item(index, len(entries), entry, "start")
            result = self._fetch_one(entry, index, len(entries),
                                     on_progress=on_progress,
                                     base_done=done_bytes,
                                     total_bytes=total_bytes)
            results.append(result)
            done_bytes += int(entry.get("packed_size") or entry.get("size") or 0)
            if result.ok:
                self._log(f"已下载 {entry.get('path')}", "SUCCESS")
            else:
                self._log(f"下载失败 {entry.get('path')}：{result.error}", "ERROR")
            if on_item is not None:
                on_item(index, len(entries), entry,
                        "done" if result.ok else "error")
            if on_progress is not None:
                on_progress(done_bytes, total_bytes, index, len(entries), entry)
        return results

    def cleanup(self) -> None:
        """清掉本次暂存（安装成功后调用）。"""
        shutil.rmtree(self.staging_dir, ignore_errors=True)


def _remove(path: str) -> None:
    try:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            os.unlink(path)
    except OSError:
        pass
