"""
在线功能的状态目录。

    PulsesSwap_database/.online/
    ├── sources.json            每个预设绑定的源
    ├── cloud/<preset>.json     上次拉到的云端 manifest（离线可用）
    ├── local/<preset>.json     上次算出的本地 manifest（仅作展示缓存）
    ├── cache/<root-hash>.json  哈希缓存（按内容目录区分）
    └── staging/<preset>/       下载暂存 + 安装日志
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

ONLINE_DIRNAME = ".online"   # 前面加点是必须的：预设扫描会跳过隐藏目录
SOURCES_FILE = "sources.json"


def online_dir(db_path) -> Path:
    return Path(db_path) / ONLINE_DIRNAME


def sources_path(db_path) -> Path:
    return online_dir(db_path) / SOURCES_FILE


def cloud_dir(db_path) -> Path:
    return online_dir(db_path) / "cloud"


def local_dir(db_path) -> Path:
    return online_dir(db_path) / "local"


def cache_dir(db_path) -> Path:
    return online_dir(db_path) / "cache"


def staging_root(db_path) -> Path:
    return online_dir(db_path) / "staging"


def cloud_manifest_path(db_path, preset: str) -> Path:
    return cloud_dir(db_path) / f"{slugify(preset)}.json"


def local_manifest_path(db_path, preset: str) -> Path:
    return local_dir(db_path) / f"{slugify(preset)}.json"


def staging_dir(db_path, preset: str) -> Path:
    return staging_root(db_path) / slugify(preset)


def cache_path(db_path, root) -> Path:
    key = hashlib.sha1(_normalize_root(root).encode("utf-8")).hexdigest()[:16]
    return cache_dir(db_path) / f"{key}.json"


def _normalize_root(root) -> str:
    text = os.path.normpath(os.path.abspath(str(root)))
    return text.lower() if os.name == "nt" else text


_SLUG_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def slugify(name: str) -> str:
    """预设名 → 安全的文件名。中文保留，非法字符换下划线。

    末尾再拼一个短哈希：``A:B`` 和 ``A?B`` 都会被换成 ``A_B``，
    不加哈希就会共用同一份状态文件（云端缓存 / 暂存目录会串）。
    """
    raw = str(name or "")
    text = _SLUG_RE.sub("_", raw).strip(" .") or "preset"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    return f"{text}-{digest}"


def ensure_dirs(db_path) -> None:
    for path in (online_dir(db_path), cloud_dir(db_path), local_dir(db_path),
                 cache_dir(db_path), staging_root(db_path)):
        path.mkdir(parents=True, exist_ok=True)
