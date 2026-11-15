#!/usr/bin/env python3
"""拉取 ``archive/webui/manifest.json`` 里登记的存档资源（WebView 线专用），校验 sha256，可选解包。

仓库里只放清单和脚本，大会话原文 / 构建环境包挂在这个仓库的 Release 上，
这样 git 历史不会被二进制撑大，换机器时又能一键取回。

用法：
    python archive/webui/tools/fetch_archive.py --list                 # 清单
    python archive/webui/tools/fetch_archive.py                        # 下载缺的，全部校验
    python archive/webui/tools/fetch_archive.py --check                # 只校验本地已有文件
    python archive/webui/tools/fetch_archive.py --unpack               # 校验后再解包
    python archive/webui/tools/fetch_archive.py --id session-b59b64a4  # 只取一条
    python archive/webui/tools/fetch_archive.py --id web-node_modules --unpack \\
        --dest src/pulses_web/web                                # 还原 node_modules

公开 Release 不需要凭证；草稿/私有 Release 需要：
    export GITHUB_TOKEN=ghp_xxx
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]          # 仓库根（archive/webui/tools → repo）
ARCHIVE = ROOT / "archive" / "webui"
MANIFEST = ARCHIVE / "manifest.json"
CACHE = ARCHIVE / "cache"
API = "https://api.github.com"


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def auth_header() -> dict:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}


def request(url: str, *, accept: str | None = None):
    headers = {"User-Agent": "pulses-swap-archive"}
    if accept:
        headers["Accept"] = accept
    headers.update(auth_header())
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60)


def releases_by_tag(repo: str) -> dict[str, dict]:
    """一次列全 Release（省 API 配额，匿名额度只有 60/小时）。"""
    with request(f"{API}/repos/{repo}/releases?per_page=100") as resp:
        return {rel["tag_name"]: rel for rel in json.load(resp)}


def find_asset(release: dict, name: str) -> dict:
    for asset in release.get("assets", []):
        if asset["name"] == name:
            return asset
    raise SystemExit(f"release {release['tag_name']} 里没有 {name}（先 --list 看看）")


def download(asset: dict, target: Path, *, attempts: int = 6) -> None:
    """下载资产；网络抖了就带 Range 断点续传重试（GitHub 存储偶尔会卡）。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(target.suffix + ".part")
    total = int(asset.get("size") or 0)

    for attempt in range(1, attempts + 1):
        have = part.stat().st_size if part.exists() else 0
        if total and have >= total:
            break
        headers = {"User-Agent": "pulses-swap-archive",
                   "Accept": "application/octet-stream"}
        headers.update(auth_header())
        if have:
            headers["Range"] = f"bytes={have}-"
        req = urllib.request.Request(asset["url"], headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                mode = "ab" if have and resp.status == 206 else "wb"
                with part.open(mode) as fh:
                    while True:
                        chunk = resp.read(1024 * 1024)
                        if not chunk:
                            break
                        fh.write(chunk)
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            got = part.stat().st_size if part.exists() else 0
            print(f"  重试 {attempt}/{attempts}（已下 {got / 1048576:.1f} MB）：{exc}")
            time.sleep(min(2 * attempt, 15))
            continue
        if not total or part.stat().st_size >= total:
            break
    part.replace(target)


def direct_url(repo: str, tag: str, name: str) -> str:
    """公开 release 的直链，不经过 API（避免 60 次/小时的限流）。"""
    return f"https://github.com/{repo}/releases/download/{tag}/{urllib.parse.quote(name)}"


def needs_zstd() -> None:
    if not shutil.which("zstd"):
        raise SystemExit("没有找到 zstd，请先安装（apt install zstd / brew install zstd）")


def unpack(item: dict, target: Path, dest: Path | None = None) -> Path:
    """按 item['unpack'] 解包，返回落地路径。"""
    kind = item.get("unpack") or "none"
    if kind == "none":
        return target

    out_dir = dest or (CACHE / item["id"])
    out_dir.mkdir(parents=True, exist_ok=True)

    if kind == "zstd":                      # 单个 .jsonl.zst -> .jsonl
        needs_zstd()
        out = (dest or target.parent) / target.name[:-len(".zst")]
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["zstd", "-d", "-f", "-q", str(target), "-o", str(out)], check=True)
        return out

    if kind == "tar.zst":                   # 目录打包的 tar.zst
        needs_zstd()
        subprocess.run(f"zstd -dc {str(target)!r} | tar -xf - -C {str(out_dir)!r}",
                       shell=True, check=True)
        return out_dir

    if kind == "zip":
        with zipfile.ZipFile(target) as zf:
            zf.extractall(out_dir)
        return out_dir

    raise SystemExit(f"不认识的 unpack 类型：{kind}")


def item_line(index: int, item: dict) -> str:
    size = int(item.get("size") or 0) / 1048576
    return (f"{index:2d}. {item['id']:26s} {item.get('kind', '-'):8s} "
            f"{size:7.1f} MB  {item.get('release_tag', '-')}")


def select_items(manifest: dict, ids: list[str]) -> list[dict]:
    items = manifest["items"]
    if not ids:
        return items
    wanted = set(ids)
    picked = [it for it in items if it["id"] in wanted or it["name"] in wanted]
    missing = wanted - {it["id"] for it in picked} - {it["name"] for it in picked}
    if missing:
        raise SystemExit(f"清单里没有：{', '.join(sorted(missing))}")
    return picked


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="拉取并校验 Pulses Swap 存档资源")
    ap.add_argument("--list", action="store_true", help="只列清单")
    ap.add_argument("--check", action="store_true", help="只校验本地已有文件")
    ap.add_argument("--unpack", action="store_true", help="校验后解包")
    ap.add_argument("--id", action="append", default=[], help="只处理指定 id（可重复）")
    ap.add_argument("--dest", type=Path, default=None, help="解包目标目录（默认 archive/cache/<id>）")
    args = ap.parse_args(argv)

    manifest = load_manifest()
    repo = manifest["repo"]
    items = select_items(manifest, args.id)

    if args.list:
        print(f"{manifest.get('batch', '')} 批次 · {repo} · manifest schema {manifest.get('schema')}")
        for index, item in enumerate(manifest["items"], 1):
            print(item_line(index, item))
        return 0

    releases: dict[str, dict] = {}
    failed = 0
    for item in items:
        target = CACHE / item["name"]
        expected = item["sha256"]
        size = int(item.get("size") or 0)

        if target.exists():
            digest = sha256_of(target)
            if digest == expected:
                print(f"[OK  ] {item['name']}  {digest[:12]}…")
                if args.unpack:
                    print(f"[解包] {unpack(item, target, args.dest)}")
                continue
            if args.check:
                print(f"[坏  ] {item['name']}  {digest[:12]}… != {expected[:12]}…")
                failed += 1
                continue
            target.unlink()
        elif args.check:
            print(f"[缺失] {item['name']}（--check 不下载）")
            failed += 1
            continue

        tag = item["release_tag"]
        print(f"[下载] {item['name']}  {size / 1048576:.1f} MB  <- {tag}")
        try:
            # 公开 release 直接走下载直链，不碰 API（限流 60 次/小时）
            download({"url": direct_url(repo, tag, item["name"]), "size": size}, target)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            # 草稿 / 私有 release 只能走 API（需要 token）
            if tag not in releases:
                releases = releases_by_tag(repo)
            if tag not in releases:
                raise SystemExit(f"仓库里没有 release {tag}（草稿需要 GITHUB_TOKEN）") from exc
            asset = find_asset(releases[tag], item["name"])
            download(asset, target)
        digest = sha256_of(target)
        if digest != expected:
            target.unlink(missing_ok=True)
            raise SystemExit(f"校验失败：{digest} != {expected}")
        print(f"[OK  ] {target}  sha256 {digest[:16]}…")

        if args.unpack:
            print(f"[解包] {unpack(item, target, args.dest)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
