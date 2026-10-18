"""
打包 / 解包。

文件夹型枪包上传前要打成 .zip（蓝奏只吃常见扩展名），下载后再解回去。
打包必须**确定性**，否则同一份内容每次打出来的 sha256 都不一样，
发布时会被判成"全变了"：

  · 条目按相对路径排序
  · 时间戳统一 1980-01-01
  · 压缩级别固定
  · 权限位固定
  · 忽略文件（.DS_Store 之类）不进包

条目清单来自 :func:`hashing.iter_tree`，与树摘要用同一份清单，
所以「打包 → 解包 → 再算树摘要」一定对得上。
"""
from __future__ import annotations

import os
import zipfile

from .errors import PackError
from .hashing import folder_zip_name, iter_tree, target_of  # noqa: F401  兼容再导出

FIXED_DATE = (1980, 1, 1, 0, 0, 0)
COMPRESS_LEVEL = 6
UNPACK_CHUNK = 1024 * 1024


def pack_folder(folder: str, zip_path: str, *, progress=None,
                should_stop=None) -> tuple[int, int]:
    """把文件夹确定性打包成 zip，返回 ``(字节数, 文件数)``。"""
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        raise PackError(f"不是文件夹: {folder}")
    entries = iter_tree(folder)
    if not entries:
        raise PackError(f"文件夹是空的: {os.path.basename(folder)}")

    target = os.path.abspath(zip_path)
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    total = sum(item[2] for item in entries)
    done = 0
    try:
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED,
                             compresslevel=COMPRESS_LEVEL) as zf:
            for rel, full, _size, _mtime in entries:
                if should_stop is not None and should_stop():
                    raise PackError("打包已取消")
                info = zipfile.ZipInfo(rel, date_time=FIXED_DATE)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o600 << 16
                with open(full, "rb") as fh:
                    zf.writestr(info, fh.read())
                done += _size
                if progress is not None:
                    progress(done, total, rel)
    except Exception:
        try:
            os.unlink(target)
        except OSError:
            pass
        raise
    return os.path.getsize(target), len(entries)


def verify_zip(zip_path: str) -> None:
    """检查压缩包 CRC；坏包直接抛 PackError。"""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            bad = zf.testzip()
    except zipfile.BadZipFile as exc:
        raise PackError("压缩包已损坏", detail=str(exc)) from exc
    if bad is not None:
        raise PackError(f"压缩包内文件损坏: {bad}")


def unpack_to(zip_path: str, dest_dir: str, *, expected_size: int | None = None,
              progress=None, should_stop=None) -> int:
    """解压到 dest_dir，返回解出的文件数。

    防目录穿越、防 zip 炸弹（解压总量超过 expected_size 太多就中止）。
    """
    dest_root = os.path.abspath(dest_dir)
    os.makedirs(dest_root, exist_ok=True)
    limit = int(expected_size * 1.02 + 4096) if expected_size else 0
    written = 0
    count = 0
    try:
        archive = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise PackError("压缩包已损坏", detail=str(exc)) from exc

    with archive as zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        total = sum(i.file_size for i in infos)
        for info in infos:
            if should_stop is not None and should_stop():
                raise PackError("解压已取消")
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                raise PackError(f"压缩包里有非法路径: {info.filename}")
            target = os.path.abspath(os.path.join(dest_root, name))
            if target != dest_root and not target.startswith(dest_root + os.sep):
                raise PackError(f"压缩包里有非法路径: {info.filename}")
            os.makedirs(os.path.dirname(target) or dest_root, exist_ok=True)
            try:
                with zf.open(info) as src, open(target, "wb") as out:
                    while True:
                        block = src.read(UNPACK_CHUNK)
                        if not block:
                            break
                        out.write(block)
                        written += len(block)
                        if limit and written > limit:
                            raise PackError("压缩包体积异常（可能已损坏）")
            except zipfile.BadZipFile as exc:
                raise PackError(f"解压失败: {name}", detail=str(exc)) from exc
            count += 1
            if progress is not None:
                progress(written, total, name)
    return count
