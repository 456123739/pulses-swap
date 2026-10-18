"""
本地扫描与哈希缓存。

在线同步的两个性能要求：

1. **启动快**：2GB 预设无改动时也要秒出结果。
   做法是对每个文件只看 ``(相对路径, size, mtime)``，三者都没变就沿用缓存里的
   sha256，只有变了的才真正读盘。缓存落在 ``online/cache/<root>.json``。

2. **比对稳**：文件夹型枪包要能和云端比出"变了没有"。
   做法是给文件夹算一个**树摘要**（tree digest）——把树里每个文件的
   ``相对路径 / 大小 / sha256`` 按路径排序后拼进一个 sha256。
   它只取决于内容，与 zip 打包细节无关，因此：
     · 开发者本地算一次 = 上传前算一次
     · 玩家解压后再算一次，能验证下载是否完整
"""
from __future__ import annotations

import hashlib
import json
import os

from .errors import CancelledError, OnlineError

CHUNK = 1024 * 1024
TREE_DIGEST_PREFIX = b"pulses-tree-v1\n"

IGNORED_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini", ".export-state.json"}
IGNORED_SUFFIX = (".tmp", ".part", ".crdownload", ".swp", ".bak")

# 预设目录里不属于"枪包内容"的东西：程序自己维护的元数据与 TACZ 的配置
EXCLUDED_NAMES = {
    "index.json", "version.txt", "description.txt",
    "tacz-pre.toml", "blacklist.txt",
}
EXCLUDED_DIRS = {"tacz_default_gun", "__pycache__"}


def _is_ignored(name: str) -> bool:
    if name in IGNORED_NAMES or name.startswith("."):
        return True
    return name.lower().endswith(IGNORED_SUFFIX)


def is_metadata_name(name: str) -> bool:
    """这个名字是不是"程序自己维护的、不参与同步"的东西。"""
    return (name in EXCLUDED_NAMES or name in EXCLUDED_DIRS
            or _is_ignored(name))


def sha256_file(path: str, *, chunk: int = CHUNK, should_stop=None) -> str:
    """流式计算文件 sha256。should_stop() 返回真时抛 CancelledError。"""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            if should_stop is not None and should_stop():
                raise CancelledError("扫描已取消")
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def iter_tree(folder: str):
    """按路径排序产出 ``(相对路径, 绝对路径, 大小, mtime)``。"""
    folder = os.path.abspath(folder)
    items = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = sorted(d for d in dirnames if not _is_ignored(d))
        for name in sorted(filenames):
            if _is_ignored(name):
                continue
            full = os.path.join(dirpath, name)
            try:
                st = os.stat(full)
            except OSError:
                continue
            rel = os.path.relpath(full, folder).replace("\\", "/")
            items.append((rel, full, st.st_size, st.st_mtime))
    items.sort(key=lambda item: item[0])
    return items


class HashCache:
    """``(相对路径, size, mtime) → sha256`` 的缓存，存成 JSON。"""

    VERSION = 1

    def __init__(self, path=None, root: str = ""):
        self.path = str(path) if path else ""
        self.root = os.path.abspath(root) if root else ""
        self.entries: dict[str, dict] = {}
        self.dirty = False
        self._touched: set[str] = set()
        self._touching = False
        if self.path:
            self.load()

    # ---------- 持久化 ----------
    def load(self) -> None:
        if not self.path or not os.path.isfile(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            self.entries = {}
            return
        if not isinstance(data, dict) or data.get("version") != self.VERSION:
            self.entries = {}
            return
        if self.root and data.get("root") and data["root"] != self.root:
            # 缓存文件换了主人（预设目录搬家 / 复制），整份作废
            self.entries = {}
            return
        files = data.get("entries")
        self.entries = {k: v for k, v in files.items() if isinstance(v, dict)} \
            if isinstance(files, dict) else {}

    def save(self) -> None:
        if not self.path or not self.dirty:
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"version": self.VERSION, "root": self.root,
                           "entries": self.entries}, fh, ensure_ascii=False)
            os.replace(tmp, self.path)
            self.dirty = False
        except Exception:
            pass

    # ---------- 读写 ----------
    def get(self, relpath: str, size: int, mtime: float) -> str | None:
        rec = self.entries.get(relpath)
        if not rec:
            return None
        if rec.get("size") != size:
            return None
        if abs(float(rec.get("mtime") or 0) - float(mtime)) >= 1e-6:
            return None
        digest = rec.get("sha256")
        if not digest:
            return None
        if self._touching:
            self._touched.add(relpath)
        return digest

    def put(self, relpath: str, size: int, mtime: float, digest: str) -> None:
        old = self.entries.get(relpath)
        self.entries[relpath] = {"size": size, "mtime": mtime, "sha256": digest}
        if old != self.entries[relpath]:
            self.dirty = True
        if self._touching:
            self._touched.add(relpath)

    def forget(self, relpath: str) -> None:
        if relpath in self.entries:
            self.entries.pop(relpath, None)
            self.dirty = True

    # ---------- 一轮扫描 ----------
    def start(self) -> None:
        """标记一轮扫描开始；结束时把没碰到的记录清掉。"""
        self._touched = set()
        self._touching = True

    def finish(self) -> None:
        self._touching = False
        stale = [k for k in self.entries if k not in self._touched]
        for key in stale:
            self.entries.pop(key, None)
            self.dirty = True
        self.save()

    def prune(self, keep: set[str]) -> None:
        for key in [k for k in self.entries if k not in keep]:
            self.entries.pop(key, None)
            self.dirty = True


def tree_digest(folder: str, cache: HashCache | None = None, *,
                should_stop=None, on_file=None,
                key_prefix: str = "") -> tuple[str, int, int]:
    """计算文件夹的树摘要，返回 ``(摘要, 总字节数, 文件数)``。

    ``key_prefix`` 用于给缓存键加命名空间：不同文件夹里可能有同名的
    ``b.txt``，缓存键必须能区分，否则会串味算出错误的摘要。

    空文件夹也有确定的摘要，不会抛异常——由调用方决定要不要当成错误。
    """
    h = hashlib.sha256(TREE_DIGEST_PREFIX)
    total = 0
    count = 0
    for rel, full, size, mtime in iter_tree(folder):
        if should_stop is not None and should_stop():
            raise CancelledError("扫描已取消")
        key = f"{key_prefix}{rel}"
        digest = cache.get(key, size, mtime) if cache is not None else None
        if digest is None:
            try:
                digest = sha256_file(full, should_stop=should_stop)
            except OSError as exc:
                raise OnlineError(f"读取失败: {rel}", detail=str(exc)) from exc
            if cache is not None:
                cache.put(key, size, mtime, digest)
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(str(size).encode("ascii"))
        h.update(b"\0")
        h.update(digest.encode("ascii"))
        h.update(b"\n")
        total += size
        count += 1
        if on_file is not None:
            on_file(rel)
    return h.hexdigest(), total, count


def folder_zip_name(folder_name: str, taken: set[str]) -> str:
    """给文件夹型枪包选一个不与现有文件重名的 zip 名。

    预设里可能同时存在 ``X/`` 和 ``X.zip``，此时文件夹用 ``X.folder.zip``，
    解压目标仍然是 ``X``。
    """
    base = folder_name.rstrip("/")
    lowered = {t.lower() for t in taken}
    candidate = f"{base}.zip"
    if candidate.lower() not in lowered:
        return candidate
    candidate = f"{base}.folder.zip"
    index = 2
    while candidate.lower() in lowered:
        candidate = f"{base}.folder{index}.zip"
        index += 1
    return candidate


def target_of(zip_name: str) -> str:
    """``X.zip`` → ``X``；``X.folder.zip`` → ``X``。"""
    name = zip_name
    if name.lower().endswith(".folder.zip"):
        return name[:-len(".folder.zip")]
    if name.lower().endswith(".zip"):
        return name[:-len(".zip")]
    return name


def item_fingerprint(path) -> dict:
    """给 index.json 用的枪包指纹（与主程序 ``get_item_fingerprint`` 同义）。"""
    path = str(path)
    if not os.path.exists(path):
        return {}
    if os.path.isfile(path):
        try:
            return {"type": "zip", "size": os.path.getsize(path), "file_count": 1}
        except OSError:
            return {}
    total = 0
    count = 0
    try:
        for _rel, _full, size, _mtime in iter_tree(path):
            total += size
            count += 1
    except OSError:
        pass
    return {"type": "folder", "size": total, "file_count": count}


def scan_local(root: str, cache: HashCache | None = None, *,
               should_stop=None, progress=None) -> list[dict]:
    """扫描一个预设目录（或已应用时的 TACZ 目录），产出 manifest 的 files 数组。

    产出的条目已经是可以直接比对/发布的形状：
      · 文件夹 → ``{"path": "X.zip", "type": "folder", "target": "X", ...}``
      · 文件   → ``{"path": "X.zip", "type": "zip", ...}``
      · 其他   → ``{"path": "readme.txt", "type": "file", ...}``

    ``index.json`` / ``version.txt`` 等程序自维护的元数据不进入 manifest。
    """
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        return []
    if cache is not None:
        cache.start()
    try:
        names = sorted(os.listdir(root))
    except OSError as exc:
        raise OnlineError(f"无法读取目录: {root}", detail=str(exc)) from exc

    taken = set(names)
    entries: list[dict] = []
    for name in names:
        if should_stop is not None and should_stop():
            raise CancelledError("扫描已取消")
        if name in EXCLUDED_NAMES or name in EXCLUDED_DIRS or _is_ignored(name):
            continue
        full = os.path.join(root, name)
        if os.path.isdir(full):
            digest, size, count = tree_digest(
                full, cache, should_stop=should_stop, on_file=progress,
                key_prefix=f"{name}/")
            zip_name = folder_zip_name(name, taken)
            taken.add(zip_name)
            entries.append({"path": zip_name, "type": "folder", "target": name,
                            "size": size, "files": count, "sha256": digest,
                            "packed_size": 0})
            if progress is not None:
                progress(name)
        elif os.path.isfile(full):
            try:
                st = os.stat(full)
            except OSError:
                continue
            digest = cache.get(name, st.st_size, st.st_mtime) \
                if cache is not None else None
            if digest is None:
                try:
                    digest = sha256_file(full, should_stop=should_stop)
                except OSError as exc:
                    raise OnlineError(f"读取失败: {name}",
                                      detail=str(exc)) from exc
                if cache is not None:
                    cache.put(name, st.st_size, st.st_mtime, digest)
            entries.append({"path": name,
                            "type": "zip" if name.lower().endswith(".zip")
                            else "file",
                            "size": st.st_size, "sha256": digest,
                            "packed_size": st.st_size})
            if progress is not None:
                progress(name)
    if cache is not None:
        cache.finish()
    return sorted(entries, key=lambda e: e["path"].lower())
