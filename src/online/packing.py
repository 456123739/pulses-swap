"""
打包 / 解包

文件夹型枪包上传前要打包成 .zip（蓝奏不接受奇怪扩展名），
下载后再解压回去。打包必须**确定性**：
  · 条目按相对路径排序
  · 时间戳统一归零（1980-01-01）
  · 压缩级别固定
这样同一份内容每次打包得到同一个 sha256，否则每次发布都会被判成"全变了"。
"""
from __future__ import annotations

import os
import zipfile

FIXED_DATE = (1980, 1, 1, 0, 0, 0)
COMPRESS_LEVEL = 6


class PackError(Exception):
    pass


def pack_folder(folder: str, zip_path: str) -> int:
    """把文件夹确定性打包成 zip，返回字节数。"""
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        raise PackError(f"不是文件夹: {folder}")
    entries: list[tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, folder).replace("\\", "/")
            entries.append((rel, full))
    entries.sort(key=lambda item: item[0])
    if not entries:
        raise PackError(f"文件夹是空的: {folder}")
    os.makedirs(os.path.dirname(os.path.abspath(zip_path)) or ".", exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=COMPRESS_LEVEL) as zf:
        for rel, full in entries:
            info = zipfile.ZipInfo(rel, date_time=FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            with open(full, "rb") as fh:
                zf.writestr(info, fh.read())
    return os.path.getsize(zip_path)


def unpack_to(zip_path: str, dest_dir: str) -> int:
    """解压到 dest_dir，返回解出的文件数。防目录穿越。"""
    dest_root = os.path.abspath(dest_dir)
    os.makedirs(dest_root, exist_ok=True)
    count = 0
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                raise PackError(f"压缩包里有非法路径: {info.filename}")
            target = os.path.abspath(os.path.join(dest_root, name))
            if not (target == dest_root
                    or target.startswith(dest_root + os.sep)):
                raise PackError(f"压缩包里有非法路径: {info.filename}")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                while True:
                    block = src.read(1024 * 1024)
                    if not block:
                        break
                    out.write(block)
            count += 1
    return count


def folder_zip_name(folder_name: str, taken: set[str]) -> str:
    """给文件夹型枪包选一个不冲突的 zip 名。

    预设里可能同时有 X/ 和 X.zip，此时文件夹用 X.folder.zip 避免云端重名。
    """
    base = folder_name.rstrip("/")
    candidate = f"{base}.zip"
    if candidate.lower() not in {t.lower() for t in taken}:
        return candidate
    candidate = f"{base}.folder.zip"
    index = 2
    while candidate.lower() in {t.lower() for t in taken}:
        candidate = f"{base}.folder{index}.zip"
        index += 1
    return candidate


def target_of(zip_name: str) -> str:
    """X.zip → X；X.folder.zip → X。"""
    name = zip_name
    if name.lower().endswith(".folder.zip"):
        return name[:-len(".folder.zip")]
    if name.lower().endswith(".zip"):
        return name[:-len(".zip")]
    return name
