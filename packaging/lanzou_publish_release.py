"""
把发布产物传到蓝奏云（下载站）。

凭据只从环境变量读，**不落盘、不打印、不进日志**：

    export PULSES_LANZOU_USER='账号'
    export PULSES_LANZOU_PASS='密码'

    # 先干跑一遍，确认要传什么、传到哪
    python packaging/lanzou_publish_release.py dist/*.zip --dry-run

    # 真传
    python packaging/lanzou_publish_release.py dist/*.zip --folder PulsesSwap

做的事：

    ① 登录（失败直接退出，不动任何文件）
    ② 在根目录找到目标文件夹；没有就建一个 —— 全程只在这个文件夹里操作
    ③ 逐个上传；同名同大小的默认跳过（`--force` 强制再传一份）
    ④ 传完列一遍文件夹核对，打印分享链接与提取码

`--base` 只给自动化测试用（指到本地 mock 服务），平时不要传。

退出码：0 成功；1 失败。
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from online.errors import OnlineError                       # noqa: E402
from online.provider_lanzou_account import (                # noqa: E402
    LanzouAccount, is_allowed_upload)


def human(num) -> str:
    value = float(num or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} GB"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="把发布产物传到蓝奏云的指定文件夹")
    parser.add_argument("files", nargs="+", help="要上传的文件")
    parser.add_argument("--folder", default="PulsesSwap",
                        help="根目录下的目标文件夹（默认 PulsesSwap）")
    parser.add_argument("--force", action="store_true",
                        help="同名同大小也重传")
    parser.add_argument("--dry-run", action="store_true",
                        help="只检查文件和凭据，不真的上传")
    parser.add_argument("--base", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    paths = [Path(p) for p in args.files]
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        print("找不到这些文件：")
        for item in missing:
            print("  -", item)
        return 1
    blocked = [p.name for p in paths if not is_allowed_upload(p.name)]
    if blocked:
        print("网盘不接受这些扩展名（先压成 .zip）：", ", ".join(blocked))
        return 1

    user = os.environ.get("PULSES_LANZOU_USER", "").strip()
    password = os.environ.get("PULSES_LANZOU_PASS", "")
    if not user or not password:
        print("缺少凭据：请先 export PULSES_LANZOU_USER / PULSES_LANZOU_PASS")
        return 1

    total = sum(p.stat().st_size for p in paths)
    print(f"目标文件夹：{args.folder}（根目录下）")
    for path in paths:
        print(f"  · {path.name}  {human(path.stat().st_size)}")
    print(f"合计 {len(paths)} 个文件 / {human(total)}")

    if args.dry_run:
        print("\n--dry-run：只做了本地检查，没有登录、没有上传。")
        return 0

    try:
        account = LanzouAccount(base=args.base) if args.base else LanzouAccount()
        print("\n[1/4] 登录…")
        account.login(user, password)
        print("      登录成功")

        print(f"[2/4] 定位文件夹「{args.folder}」…")
        folder_id = account.ensure_folder(args.folder, -1)
        print(f"      folder_id = {folder_id}")

        # 网盘返回的 size 是格式化过的字符串（"1.2 M"），拿来比对不可靠；
        # 这里按文件名判断：同名就跳过，确实要覆盖再传 --force。
        existing = {str(row.get("name") or "")
                    for row in account.list_files(folder_id)}

        print("[3/4] 上传…")
        uploaded = 0
        for path in paths:
            size = path.stat().st_size
            if path.name in existing and not args.force:
                print(f"      跳过（文件夹里已有同名文件，要覆盖加 --force）：{path.name}")
                continue
            started = time.time()
            result = account.upload(str(path), folder_id)
            cost = time.time() - started
            uploaded += 1
            print(f"      ✓ {path.name}  {human(size)}  {cost:.1f}s  "
                  f"id={result.get('id')}")

        print("[4/4] 核对文件夹…")
        rows = account.list_files(folder_id)
        for row in sorted(rows, key=lambda r: str(r.get("name") or "")):
            print(f"      - {row.get('name')}  {row.get('size')}")

        share = account.folder_share(folder_id)
        print("\n文件夹分享链接：", share.get("url"))
        if share.get("password"):
            print("提取码：", share.get("password"))
        print(f"\n完成：本次上传 {uploaded} 个文件。")
        return 0
    except OnlineError as exc:
        print(f"\n失败：{exc}")
        detail = getattr(exc, "detail", "")
        if detail:
            print("详情：", str(detail)[:300])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
