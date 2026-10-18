"""
对真实蓝奏分享跑一遍"下载 → 校验 → 安装 → 重扫"。

用途：验证网络链路（分享解析 / 人机校验 / 一次性令牌 / 直链 / 流式下载 /
重试）在真实环境里确实能跑通。发布侧需要真实账号，不在这里测；
manifest 用下载下来的文件现算。

    python packaging/online_smoke.py <分享链接> [密码]

退出码：0 全部通过；1 有失败项。
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from online import diff, hashing, updater                     # noqa: E402
from online.downloader import Downloader                      # noqa: E402
from online.errors import OnlineError                         # noqa: E402
from online.manifest import normalize                         # noqa: E402
from online.provider_lanzou import LanzouShare, format_size   # noqa: E402

DEFAULT_URL = "https://nimshade.lanzoul.com/b0139mgt2j"
DEFAULT_PWD = "28pm"


def step(title: str) -> float:
    print(f"\n=== {title} ===")
    return time.perf_counter()


def done(start: float) -> None:
    print(f"    用时 {time.perf_counter() - start:.2f}s")


def main(argv: list[str]) -> int:
    url = argv[1] if len(argv) > 1 else DEFAULT_URL
    password = argv[2] if len(argv) > 2 else DEFAULT_PWD

    failures: list[str] = []
    temp = Path(tempfile.mkdtemp(prefix="pulses_smoke_"))
    try:
        # ① 解析分享
        start = step(f"解析分享 {url}")
        share = LanzouShare(url, password, retries=3)
        try:
            info = share.probe()
        except OnlineError as exc:
            print(f"    失败：{exc}")
            if exc.hint:
                print(f"    提示：{exc.hint}")
            return 1
        print(f"    域名 {info['host']} · {info['count']} 个文件 · "
              f"{format_size(info['total_bytes'])}")
        for row in info["files"]:
            flag = "（带网页）" if "webpage=" in row["raw_id"] else ""
            print(f"      {row['size']:>8}  {row['name']}{flag}")
        done(start)

        # ② 逐个下载并算哈希
        start = step("下载并计算哈希")
        entries: list[dict] = []
        staged = temp / "probe"
        staged.mkdir(parents=True)
        for row in info["files"]:
            if "webpage=" in row["raw_id"]:
                print(f"    跳过 {row['name']}：带网页文件无法直接下载")
                continue
            target = staged / row["name"]
            try:
                share.download(row["file_id"], str(target),
                               raw_id=row["raw_id"],
                               expected_size=row["size_bytes"])
            except OnlineError as exc:
                print(f"    下载失败 {row['name']}：{exc}")
                failures.append(row["name"])
                continue
            digest = hashing.sha256_file(str(target))
            entries.append({"path": row["name"],
                            "type": "zip" if row["name"].lower().endswith(".zip")
                            else "file",
                            "size": target.stat().st_size, "sha256": digest,
                            "packed_size": target.stat().st_size})
            print(f"    {row['name']}  {format_size(target.stat().st_size)}  "
                  f"sha256 {digest[:12]}…")
        done(start)

        if not entries:
            print("\n没有可下载的文件，无法继续。")
            return 1

        # ③ 只把"参与同步"的文件放进 manifest（元数据文件不进）
        syncable = [e for e in entries
                    if not hashing.is_metadata_name(e["path"].split("/")[0])]
        if not syncable:
            print("\n这个分享里只有元数据文件（description.txt 之类），"
                  "没有可同步的枪包。")
            print("网络链路已验证通过：列表、下载、哈希都正确。")
            return 0 if not failures else 1

        cloud = normalize({"name": "真实分享冒烟", "version": "smoke",
                           "generation": 1, "files": syncable})

        # ④ 差异 + 正式下载器 + 安装器
        start = step("差异 / 下载 / 安装")
        plan = diff.compare([], cloud, role="player", app_version="2.4.16")
        print(f"    {plan.summary()} · 需下载 {format_size(plan.download_bytes)}")
        staging = temp / "staging"
        player = temp / "player"
        player.mkdir()
        downloader = Downloader(share, str(staging))
        results = downloader.run(plan.transfer_items)
        installer = updater.Installer(str(player), str(staging))
        for result in results:
            if not result.ok:
                print(f"    失败 {result.entry['path']}：{result.error}")
                failures.append(result.entry["path"])
                continue
            installer.install(result.entry, result.staged)
            print(f"    安装 {result.entry['path']} "
                  f"({format_size(result.bytes)})")
        done(start)

        # ⑤ 重扫 + 比对
        start = step("重扫校验")
        again = diff.compare(hashing.scan_local(str(player)), cloud,
                             role="player", app_version="2.4.16")
        print(f"    {again.summary()}")
        if not again.is_clean:
            for item in again.items:
                if item.action != diff.SKIP:
                    print(f"    ! {item.path}: {item.action} {item.reason}")
                    failures.append(item.path)
        done(start)

        print("\n=== 结果 ===")
        if failures:
            print(f"失败 {len(failures)} 项：{', '.join(failures[:8])}")
            return 1
        print("全部通过：真实分享的下载、校验、安装、重扫都对得上。")
        print(json.dumps({"files": len(syncable),
                          "bytes": sum(e["size"] for e in syncable)},
                         ensure_ascii=False))
        return 0
    finally:
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
