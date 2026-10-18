"""
manifest 读写与规范化

一份 manifest 描述「一个预设里有哪些文件」：
  {"schema":1, "name":…, "version":…, "generation":…, "files":[…],
   "min_app":…, "generated_at":…, "notes":…}

每条文件：
  {"path": "gun_alpha.zip", "type": "zip", "size": 123, "sha256": "…"}
  {"path": "gun_beta.zip",  "type": "folder", "target": "gun_beta",
   "size": 456, "sha256": "…"}

  type=zip    原生 zip 枪包，下载后原样放入
  type=folder 文件夹型枪包（已打包），下载后解压到 target 目录
"""
from __future__ import annotations

import json
import time

SCHEMA = 1
VALID_TYPES = ("zip", "folder", "file")


class ManifestError(Exception):
    pass


def empty_manifest(name: str = "", version: str = "") -> dict:
    return {"schema": SCHEMA, "name": name, "version": version,
            "generation": 0, "min_app": "", "generated_at": "",
            "notes": "", "files": []}


def _norm_entry(entry: dict) -> dict:
    path = str(entry.get("path") or "").replace("\\", "/").lstrip("/")
    if not path:
        raise ManifestError(f"文件条目缺少 path: {entry}")
    kind = str(entry.get("type") or "file")
    if kind not in VALID_TYPES:
        raise ManifestError(f"未知文件类型 {kind!r}（path={path}）")
    out = {"path": path, "type": kind,
           "size": int(entry.get("size") or 0),
           "sha256": str(entry.get("sha256") or "").lower()}
    if kind == "folder":
        target = str(entry.get("target") or "").replace("\\", "/").strip("/")
        if not target:
            # 没写 target 就用去掉 .zip 的名字
            target = path[:-4] if path.lower().endswith(".zip") else path
        out["target"] = target
    return out


def normalize(data: dict) -> dict:
    """校验并规范化一份 manifest，返回新字典。"""
    if not isinstance(data, dict):
        raise ManifestError("manifest 不是对象")
    schema = int(data.get("schema") or 0)
    if schema > SCHEMA:
        raise ManifestError(f"manifest schema {schema} 高于本程序支持的 {SCHEMA}，请升级软件")
    files = data.get("files")
    if not isinstance(files, list):
        raise ManifestError("manifest 缺少 files 数组")
    entries = [_norm_entry(e) for e in files]
    paths = [e["path"] for e in entries]
    dup = {p for p in paths if paths.count(p) > 1}
    if dup:
        raise ManifestError(f"manifest 里有重复路径: {sorted(dup)[:3]}")
    return {
        "schema": SCHEMA,
        "name": str(data.get("name") or ""),
        "version": str(data.get("version") or ""),
        "generation": int(data.get("generation") or 0),
        "min_app": str(data.get("min_app") or ""),
        "generated_at": str(data.get("generated_at") or ""),
        "notes": str(data.get("notes") or ""),
        "files": sorted(entries, key=lambda e: e["path"]),
    }


def load(path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return normalize(json.load(fh))


def save(manifest: dict, path, *, generation: int | None = None) -> dict:
    data = normalize(manifest)
    if generation is not None:
        data["generation"] = int(generation)
    if not data["generated_at"]:
        data["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1, sort_keys=True)
    return data


def index_by_path(manifest: dict) -> dict[str, dict]:
    return {e["path"]: e for e in manifest.get("files", [])}


def version_tuple(text: str) -> tuple:
    """把 '2.5.0' / '2026.10.18' 变成可比较的元组。"""
    parts = []
    for chunk in str(text or "").replace("-", ".").split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            parts.append(0)
    return tuple(parts) or (0,)
