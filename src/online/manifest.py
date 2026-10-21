"""
manifest 读写与规范化。

云端 manifest 的文件名是 ``_pulses_manifest.cfg``，**内容仍然是 JSON**：

    {
      "format": "pulses-manifest",
      "schema": 2,
      "name": "SSR预设包",
      "version": "2026.10.18",
      "generation": 7,
      "min_app": "2.5.0",
      "generated_at": "…",
      "notes": "…",
      "manifest_sha256": "…",
      "files": [
        {"path": "gun_alpha.zip", "type": "zip", "size": 41943040,
         "sha256": "9f2c…", "packed_size": 41943040,
         "packed_sha256": "9f2c…"},
        {"path": "gun_beta.zip", "type": "folder", "target": "gun_beta",
         "size": 52428800, "files": 42, "sha256": "7d1a…",
         "packed_size": 39800000, "packed_sha256": "…"}
      ]
    }

为什么后缀不是 .json：蓝奏云对扩展名有白名单，真实账号实测
``.json`` / ``.yaml`` / ``.toml`` / ``.ini`` / ``.xml`` 都会被拒绝；
``.cfg`` 可以上传。所以只改后缀，内容保持 JSON——json 解析是 C 实现，
比 INI/CFG 解析更快，也不会引入第二套结构。本地缓存仍用 .json。

旧版 ``_pulses_manifest.txt``（同样 JSON 内容）仍然兼容读取；发布一次后
会自动换成 ``_pulses_manifest.cfg``。

每条文件：

    type=zip     原生 zip 枪包，下载后原样放入
    type=folder  文件夹型枪包（上传时打包），下载后解压到 target
    type=file    其他单文件

字段含义：

  path          上传到网盘的文件名，也是比对的唯一键
  size          逻辑体积（folder 为解压后总字节数）
  packed_size   实际传输体积（folder 为打包后 zip 大小）
  sha256        内容摘要（folder 为树摘要），唯一可信标识
  packed_sha256 传输包摘要（folder 为 zip 的 sha256），下载后先验包再解压
  manifest_sha256 整份 manifest 的规范化摘要，用来发现损坏/误改
                 （完整性校验，不是数字签名）
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time

from .errors import ManifestError

SCHEMA = 2
FORMAT = "pulses-manifest"
VALID_TYPES = ("zip", "folder", "file")
MAX_PATH_LEN = 180

# Windows 不允许出现在文件名里的字符（网盘也吃不下）
_BAD_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def empty_manifest(name: str = "", version: str = "") -> dict:
    return {"format": FORMAT, "schema": SCHEMA, "name": name,
            "version": version, "generation": 0, "min_app": "",
            "generated_at": "", "notes": "", "files": []}


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


def _norm_entry(entry: dict, *, require_digest: bool = False) -> dict:
    if not isinstance(entry, dict):
        raise ManifestError(f"文件条目不是对象: {entry!r}")
    path = check_path(entry.get("path"))
    kind = str(entry.get("type") or "file").strip().lower()
    if kind not in VALID_TYPES:
        raise ManifestError(f"未知文件类型 {kind!r}（path={path}）")

    digest = str(entry.get("sha256") or "").strip().lower()
    if digest and not _HEX64.match(digest):
        raise ManifestError(f"sha256 格式不对（path={path}）")
    if require_digest and not digest:
        raise ManifestError(f"文件条目缺少 sha256（path={path}）",
                            hint="manifest 已损坏，请发布者重新发布。")

    packed_digest = str(entry.get("packed_sha256") or "").strip().lower()
    if packed_digest and not _HEX64.match(packed_digest):
        raise ManifestError(f"packed_sha256 格式不对（path={path}）")

    out = {"path": path, "type": kind,
           "size": _as_int(entry.get("size")),
           "sha256": digest}
    # 云端实际文件名（同名上传被网盘改名时与 path 不同）；老 manifest 没有这个字段
    cloud = str(entry.get("cloud") or "").strip()
    if cloud:
        if "/" in cloud or "\\" in cloud or cloud in (".", ".."):
            raise ManifestError(f"cloud 字段不是合法文件名: {cloud!r}")
        out["cloud"] = cloud
    packed = _as_int(entry.get("packed_size"))
    if kind == "folder":
        target = check_path(entry.get("target") or _strip_zip(path))
        if "/" in target:
            raise ManifestError(f"folder 类型的 target 只能是单层目录: {target}")
        out["target"] = target
        out["files"] = _as_int(entry.get("files"))
        # 传输体积未知时退回逻辑体积，避免界面显示 0
        out["packed_size"] = packed or out["size"]
        if packed_digest:
            out["packed_sha256"] = packed_digest
    else:
        out["packed_size"] = packed or out["size"]
        # 单文件没有"打包"这一步：内容摘要就是传输摘要
        out["packed_sha256"] = packed_digest or digest
    return out


def _strip_zip(path: str) -> str:
    lower = path.lower()
    if lower.endswith(".folder.zip"):
        return path[:-len(".folder.zip")]
    if lower.endswith(".zip"):
        return path[:-len(".zip")]
    return path


def manifest_checksum(data: dict) -> str:
    """对规范化后的 manifest 计算摘要（不包含 manifest_sha256 自身）。"""
    payload = {key: value for key, value in data.items()
               if key != "manifest_sha256"}
    raw = json.dumps(payload, ensure_ascii=True, sort_keys=True,
                     separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize(data: dict, *, verify: bool = True) -> dict:
    """校验并规范化一份 manifest，返回新字典。

    ``verify=False`` 用于保存前重新计算摘要：此时不校验旧的
    ``manifest_sha256``，避免"改了一个字段就再也存不回去"。
    """
    if not isinstance(data, dict):
        raise ManifestError("manifest 不是对象")
    schema_in = _as_int(data.get("schema"))
    if schema_in > SCHEMA:
        raise ManifestError(
            f"manifest 版本 {schema_in} 高于本程序支持的 {SCHEMA}",
            hint="请先把 Pulses Swap 升级到最新版。")
    fmt = str(data.get("format") or FORMAT).strip()
    if fmt != FORMAT:
        raise ManifestError(f"manifest 格式标识不对: {fmt!r}")

    files = data.get("files")
    if not isinstance(files, list):
        raise ManifestError("manifest 缺少 files 数组")

    entries = [_norm_entry(e, require_digest=schema_in != 1) for e in files]
    counter: dict[str, int] = {}
    for entry in entries:
        key = entry["path"].lower()
        counter[key] = counter.get(key, 0) + 1
    dup = sorted(key for key, count in counter.items() if count > 1)
    if dup:
        raise ManifestError(f"manifest 里有重复路径: {dup[:3]}")

    out = {
        "format": FORMAT,
        "schema": SCHEMA,
        "name": str(data.get("name") or ""),
        "version": str(data.get("version") or ""),
        "generation": _as_int(data.get("generation")),
        "min_app": str(data.get("min_app") or ""),
        "generated_at": str(data.get("generated_at") or ""),
        "notes": str(data.get("notes") or ""),
        "files": sorted(entries, key=lambda e: e["path"].lower()),
    }
    checksum = str(data.get("manifest_sha256") or "").strip().lower()
    if checksum:
        if not _HEX64.match(checksum):
            raise ManifestError("manifest_sha256 格式不对")
        out["manifest_sha256"] = checksum
        if verify and checksum != manifest_checksum(out):
            raise ManifestError(
                "manifest 完整性校验失败：内容可能被改动过",
                hint="请发布者重新发布；玩家不要手动改云端文件。")
    return out


def loads(text: str, *, fmt: str = "") -> dict:
    """从字符串读取 manifest。

    ``.cfg`` 只是网盘要求的后缀，内容就是 JSON；``fmt`` 仅用于要求新版
    ``.cfg`` 必须带 ``manifest_sha256``。旧版 ``.txt`` 允许没有摘要。
    """
    raw = str(text or "").lstrip("\ufeff \t\r\n")
    if not raw:
        raise ManifestError("manifest 是空的")
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise ManifestError("manifest 不是合法 JSON",
                            detail=str(exc)) from exc
    normalized = normalize(data)
    fmt = str(fmt or "").lower().lstrip(".")
    if fmt in ("cfg", "conf", "ini") and not normalized.get("manifest_sha256"):
        raise ManifestError("manifest 缺少完整性校验（manifest_sha256）",
                            hint="请发布者重新发布。")
    return normalized


def load(path) -> dict:
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            text = fh.read()
    except FileNotFoundError:
        raise
    except (OSError, UnicodeError) as exc:
        raise ManifestError(f"manifest 读取失败: {os.path.basename(str(path))}",
                            detail=str(exc)) from exc
    suffix = os.path.splitext(str(path))[1].lower()
    fmt = "cfg" if suffix in (".cfg", ".conf", ".ini") else ""
    try:
        return loads(text, fmt=fmt)
    except ManifestError as exc:
        if not exc.detail:
            exc.detail = os.path.basename(str(path))
        raise


def _prepare(manifest: dict, generation: int | None = None) -> dict:
    data = normalize(manifest, verify=False)
    for entry in data["files"]:
        if not entry.get("sha256"):
            raise ManifestError(
                f"manifest 条目缺少 sha256，无法保存为新版格式：{entry['path']}")
    if generation is not None:
        data["generation"] = _as_int(generation)
    if not data["generated_at"]:
        data["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    data["manifest_sha256"] = manifest_checksum(data)
    return data


def _render(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True)


def dumps(manifest: dict, *, fmt: str = "cfg",
          generation: int | None = None) -> str:
    """把 manifest 序列化成 JSON 字符串（后缀/格式名不影响内容）。"""
    return _render(_prepare(manifest, generation))


def save(manifest: dict, path, *, generation: int | None = None) -> dict:
    """原子写入 manifest；所有后缀都写 JSON，内容不随扩展名变化。"""
    data = _prepare(manifest, generation)
    target = str(path)
    os.makedirs(os.path.dirname(os.path.abspath(target)) or ".", exist_ok=True)
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(_render(data))
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
