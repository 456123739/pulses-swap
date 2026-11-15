#!/usr/bin/env python3
"""把本地文件发到这个仓库某个 Release 上，并回读 sha256 校验。

为什么不直接 `gh release upload`：这台机器到 GitHub 只有 api / uploads 域名通，
而且会间歇性超时；gh 走 GraphQL，一超时就没法重试。这里用 REST 上传接口 +
指数退避重试，传完再拿 API 回读 digest 比对。

用法：
    export GITHUB_TOKEN=...            # 或者先 gh auth login
    python archive/tools/publish_asset.py --tag archive-2026-11 --file 某文件.zst
    python archive/tools/publish_asset.py --tag bundle-3.2.0 --file x.tar.zst --name 别名.tar.zst
    python archive/tools/publish_asset.py --tag archive-2026-11 --list
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.github.com"
UPLOAD = "https://uploads.github.com"
ATTEMPTS = 8


def token() -> str:
    env = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if env:
        return env.strip()
    try:
        return subprocess.check_output(["gh", "auth", "token"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        raise SystemExit("没有 token：export GITHUB_TOKEN=... 或先 gh auth login")


def call(method: str, url: str, payload: dict | None = None, *,
         raw: bytes | None = None, content_type: str = "application/json",
         allow: tuple[int, ...] = ()):
    """带重试的 API 调用；这里是这台机器网络的补丁，不是业务逻辑。"""
    last: Exception | None = None
    for attempt in range(1, ATTEMPTS + 1):
        data = raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": content_type,
            "User-Agent": "pulses-swap-archive",
        })
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                body = resp.read()
                return json.loads(body.decode() or "{}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:300]
            if exc.code in allow:
                return {}
            if exc.code in (401, 403, 404, 422):
                raise SystemExit(f"HTTP {exc.code} {url}\n{detail}")
            last = RuntimeError(f"HTTP {exc.code} {detail}")
        except Exception as exc:                        # 超时 / 连接被重置
            last = exc
        wait = min(2 ** attempt, 30)
        print(f"  重试 {attempt}/{ATTEMPTS}（{wait}s）：{last}")
        time.sleep(wait)
    raise SystemExit(f"放弃：{last}")


def release_by_tag(repo: str, tag: str) -> dict | None:
    return call("GET", f"{API}/repos/{repo}/releases/tags/{tag}", allow=(404,)) or None


def ensure_release(repo: str, tag: str, *, title: str, notes: str,
                   target: str | None = None, prerelease: bool = True) -> dict:
    """没有就建一个；target 决定新 tag 落到哪个 commit/branch。"""
    existing = release_by_tag(repo, tag)
    if existing:
        return existing
    payload = {"tag_name": tag, "name": title, "body": notes,
               "prerelease": prerelease, "draft": False}
    if target:
        payload["target_commitish"] = target
    release = call("POST", f"{API}/repos/{repo}/releases", payload)
    print(f"[建 Release] {tag} -> {release.get('html_url')}")
    return release


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def upload(repo: str, tag: str, path: Path, name: str, *, replace: bool) -> dict:
    release = release_by_tag(repo, tag)
    if not release:
        raise SystemExit(f"没有 release {tag}，先加 --create-release")
    for asset in release.get("assets", []):
        if asset["name"] == name:
            if not replace:
                if asset.get("digest") == f"sha256:{sha256_of(path)}":
                    print(f"[已存在] {name}  digest 一致，跳过")
                    return asset
                raise SystemExit(f"{name} 已存在且内容不同，加 --replace 覆盖")
            call("DELETE", f"{API}/repos/{repo}/releases/assets/{asset['id']}")
            print(f"[删除旧资产] {name}")

    size = path.stat().st_size
    print(f"[上传] {name}  {size / 1048576:.1f} MB -> {tag}")
    url = f"{UPLOAD}/repos/{repo}/releases/{release['id']}/assets?name={urllib.parse.quote(name)}"
    asset = call("POST", url, raw=path.read_bytes(),
                 content_type="application/octet-stream")
    print(f"[完成] id={asset['id']}  digest={asset.get('digest')}")
    return asset


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="上传 Release 资产并校验 digest")
    ap.add_argument("--repo", default=None, help="默认取 archive/manifest.json 里的 repo")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--file", type=Path)
    ap.add_argument("--name", default=None)
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--list", action="store_true", help="只列出该 release 的资产")
    ap.add_argument("--create-release", action="store_true", help="release 不存在时创建")
    ap.add_argument("--title", default=None)
    ap.add_argument("--notes", default="")
    ap.add_argument("--target", default=None, help="新 Release 的 tag 指向哪个 commit/branch")
    args = ap.parse_args(argv)

    repo = args.repo
    if not repo:
        manifest = Path(__file__).resolve().parents[1] / "manifest.json"
        repo = json.loads(manifest.read_text(encoding="utf-8"))["repo"]

    if args.create_release:
        ensure_release(repo, args.tag, title=args.title or args.tag,
                       notes=args.notes, target=args.target)

    if args.list:
        release = release_by_tag(repo, args.tag)
        if not release:
            raise SystemExit(f"没有 release {args.tag}")
        for asset in release.get("assets", []):
            print(f"{asset['name']:48s} {asset['size'] / 1048576:7.1f} MB  "
                  f"{asset.get('digest') or '-'}")
        return 0

    if not args.file:
        raise SystemExit("需要 --file")
    if not args.file.exists():
        raise SystemExit(f"找不到 {args.file}")

    asset = upload(repo, args.tag, args.file, args.name or args.file.name,
                   replace=args.replace)
    expected = f"sha256:{sha256_of(args.file)}"
    got = asset.get("digest")
    if got and got != expected:
        raise SystemExit(f"digest 不一致：{got} != {expected}")
    print(f"[校验] {args.name or args.file.name}  {expected}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
