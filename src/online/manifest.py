"""
manifest 读写与规范化。

一份 manifest 描述「一个预设里有哪些东西」：

    {"schema":1, "name":"SSR预设包", "version":"2026.10.18", "generation":7,
     "min_app":"2.5.0", "generated_at":"…", "notes":"…", "files":[…]}

每条文件：

    {"path":"gun_alpha.zip", "type":"zip",    "size":41943040,
     "sha256":"9f2c…", "packed_size":41943040}
    {"path":"gun_beta.zip",  "type":"folder", "target":"gun_beta",
     "size":52428800, "files":42, "sha256":"7d1a…", "packed_size":39800000}

  type=zip     原生 zip 枪包，下载后原样放入
  type=folder  文件夹型枪包（上传时打包），下载后解压到 target
  type=file    其他单文件

字段含义：

  path         上传到网盘的文件名，也是比对的唯一键
  size         逻辑体积（folder 为解压后总字节数）
  packed_size  实际传输体积（folder 为打包后 zip 大小）
  sha256       内容摘要（folder 为树摘要），唯一可信标识
"""
from __future__ import annotations

import json
import os
import re
import time

from .errors import ManifestError

SCHEMA = 1
VALID_TYPES = ("zip", "folder", "file")
MAX_PATH_LEN = 180

# Windows 不允许出现在文件名里的字符（网盘也吃不下）
_BAD_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def empty_manifest(name: str = "", version: str = "") -> dict:
    return {"schema": SCHEMA, "name": name, "version": version,
            "generation": 0, "min_app": "", "generated_at": "",
            "notes": "", "files": []}


def check_path(path: str) -> str:
    """校验并规范化一条相对路径，非法就抛 ManifestError。"""
    text = str(path or "").replace("\\", "/").strip()
    text = text.lstrip("/")
    if not text:
        raise ManifestError("文件条目缺少 path")
    if len(text) > MAX_PATH_LEN:
        raise ManifestError(f"路径过长（>{MAX_PATH_LEN}）: {text[:40]}…")
    parts = text.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ManifestError(f"非法路径: {text}")
    if _BAD_CHARS.search(text):
        raise ManifestError(f"路径含非法字符: {text}")
    if re.match(r"^[A-Za-z]:", text):
        raise ManifestError(f"路径不能是绝对路径: {text}")
    return text


def _as_int(value, default: int = 0) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number >= 0 else default


def _norm_entry(entry: dict) -> dict:
    if not isinstance(entry, dict):
        raise ManifestError(f"文件条目不是对象: {entry!r}")
    path = check_path(entry.get("path"))
    kind = str(entry.get("type") or "file").strip().lower()
    if kind not in VALID_TYPES:
        raise ManifestError(f"未知文件类型 {kind!r}（path={path}）")

    digest = str(entry.get("sha256") or "").strip().lower()
    if digest and not _HEX64.match(digest):
        raise ManifestError(f"sha256 格式不对（path={path}）")

    out = {"path": path, "type": kind,
           "size": _as_int(entry.get("size")),
           "sha256": digest}
    packed = _as_int(entry.get("packed_size"))
    if kind == "folder":
        target = check_path(entry.get("target") or _strip_zip(path))
        if "/" in target:
            raise ManifestError(f"folder 类型的 target 只能是单层目录: {target}")
        out["target"] = target
        out["files"] = _as_int(entry.get("files"))
        # 传输体积未知时退回逻辑体积，避免界面显示 0
        out["packed_size"] = packed or out["size"]
    else:
        out["packed_size"] = packed or out["size"]
    return out


def _strip_zip(path: str) -> str:
    lower = path.lower()
    if lower.endswith(".folder.zip"):
        return path[:-len(".folder.zip")]
    if lower.endswith(".zip"):
        return path[:-len(".zip")]
    return path


def normalize(data: dict) -> dict:
    """校验并规范化一份 manifest，返回新字典。"""
    if not isinstance(data, dict):
        raise ManifestError("manifest 不是对象")
    schema = _as_int(data.get("schema"))
    if schema > SCHEMA:
        raise ManifestError(
            f"manifest 版本 {schema} 高于本程序支持的 {SCHEMA}",
            hint="请先把 Pulses Swap 升级到最新版。")
    files = data.get("files")
    if not isinstance(files, list):
        raise ManifestError("manifest 缺少 files 数组")

    entries = [_norm_entry(e) for e in files]
    counter: dict[str, int] = {}
    for entry in entries:
        key = entry["path"].lower()
        counter[key] = counter.get(key, 0) + 1
    dup = sorted(key for key, count in counter.items() if count > 1)
    if dup:
        raise ManifestError(f"manifest 里有重复路径: {dup[:3]}")

    return {
        "schema": SCHEMA,
        "name": str(data.get("name") or ""),
        "version": str(data.get("version") or ""),
        "generation": _as_int(data.get("generation")),
        "min_app": str(data.get("min_app") or ""),
        "generated_at": str(data.get("generated_at") or ""),
        "notes": str(data.get("notes") or ""),
        "files": sorted(entries, key=lambda e: e["path"].lower()),
    }


def load(path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise
    except (OSError, ValueError) as exc:
        raise ManifestError(f"manifest 读取失败: {os.path.basename(str(path))}",
                            detail=str(exc)) from exc
    return normalize(data)


def save(manifest: dict, path, *, generation: int | None = None) -> dict:
    data = normalize(manifest)
    if generation is not None:
        data["generation"] = _as_int(generation)
    if not data["generated_at"]:
        data["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    target = str(path)
    os.makedirs(os.path.dirname(os.path.abspath(target)) or ".", exist_ok=True)
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, target)
    return data


def index_by_path(manifest: dict) -> dict[str, dict]:
    return {e["path"].lower(): e for e in manifest.get("files", [])}


def version_tuple(text: str) -> tuple:
    """把 ``2.5.0`` / ``2026.10.18`` 变成可比较的元组。"""
    parts = []
    for chunk in str(text or "").replace("-", ".").split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            parts.append(0)
    while parts and parts[-1] == 0:
        parts.pop()
    return tuple(parts) or (0,)


def is_newer(candidate: str, current: str) -> bool:
    """candidate 版本是否高于 current。"""
    return version_tuple(candidate) > version_tuple(current)


def total_size(manifest: dict, *, packed: bool = False) -> int:
    key = "packed_size" if packed else "size"
    return sum(int(e.get(key) or 0) for e in manifest.get("files", []))
