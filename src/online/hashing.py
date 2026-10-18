"""
本地扫描与哈希缓存

目标：启动时"快速重算"预设目录的 manifest。
做法：对每个文件只看 (相对路径, size, mtime)，三者都没变就沿用缓存里的 sha256，
      只有变了的才真正读文件计算。2GB 预设无改动时基本只有 stat 开销。
"""
from __future__ import annotations

import hashlib
import json
import os

CHUNK = 1024 * 1024
IGNORED_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
IGNORED_SUFFIX = (".tmp", ".part", ".crdownload", ".swp")


def sha256_file(path: str, *, chunk: int = CHUNK, should_stop=None) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            if should_stop is not None and should_stop():
                raise InterruptedError("扫描被中断")
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _ignored(name: str) -> bool:
    if name in IGNORED_NAMES or name.startswith("."):
        return True
    return name.lower().endswith(IGNORED_SUFFIX)


class HashCache:
    """(size, mtime) → sha256 的缓存，存成 JSON。"""

    def __init__(self, path=None):
        self.path = path
        self.entries: dict[str, dict] = {}
        self.dirty = False
        if path:
            self.load()

    def load(self) -> None:
        if not self.path or not os.path.isfile(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                self.entries = {k: v for k, v in data.items()
                                if isinstance(v, dict)}
        except Exception:
            self.entries = {}

    def save(self) -> None:
        if not self.path or not self.dirty:
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump(self.entries, fh, ensure_ascii=False)
            self.dirty = False
        except Exception:
            pass

    def get(self, relpath: str, size: int, mtime: float) -> str | None:
        rec = self.entries.get(relpath)
        if not rec:
            return None
        if rec.get("size") == size and abs(float(rec.get("mtime") or 0) - mtime) < 1e-6:
            return rec.get("sha256")
        return None

    def put(self, relpath: str, size: int, mtime: float, digest: str) -> None:
        self.entries[relpath] = {"size": size, "mtime": mtime, "sha256": digest}
        self.dirty = True

    def forget(self, relpath: str) -> None:
        if relpath in self.entries:
            self.entries.pop(relpath, None)
            self.dirty = True

    def prune(self, keep: set[str]) -> None:
        """删掉已经不存在的文件记录。"""
        for key in [k for k in self.entries if k not in keep]:
            self.entries.pop(key, None)
            self.dirty = True


def scan_preset(root: str, cache: HashCache | None = None, *,
                should_stop=None, progress=None) -> list[dict]:
    """扫描预设目录，返回 manifest 的 files 数组（path/size/sha256）。

    这里不判断 type —— 类型由「云端 manifest」决定（本地只是比对用）。
    """
    root = os.path.abspath(root)
    out: list[dict] = []
    seen: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not _ignored(d))
        for name in sorted(filenames):
            if _ignored(name):
                continue
            full = os.path.join(dirpath, name)
            try:
                st = os.stat(full)
            except OSError:
                continue
            rel = os.path.relpath(full, root).replace("\\", "/")
            seen.add(rel)
            digest = cache.get(rel, st.st_size, st.st_mtime) if cache else None
            if digest is None:
                try:
                    digest = sha256_file(full, should_stop=should_stop)
                except (OSError, InterruptedError):
                    continue
                if cache:
                    cache.put(rel, st.st_size, st.st_mtime, digest)
            out.append({"path": rel, "size": st.st_size, "sha256": digest})
            if progress:
                progress(rel)
    if cache:
        cache.prune(seen)
        cache.save()
    return sorted(out, key=lambda e: e["path"])
