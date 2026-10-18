"""
真实蓝奏账号的"发布 → 玩家下载"闭环验证（只在 test 文件夹里操作）。

    export PULSES_LANZOU_USER='账号'
    export PULSES_LANZOU_PASS='密码'
    python packaging/lanzou_live_publish.py

做的事：

    ① 登录
    ② 在 test 下建一个临时子目录 test/_pulses_probe
    ③ 造两个"枪包"：一个原生 zip、一个文件夹（先确定性打包）
    ④ 上传两个包 + manifest（generation=1）
    ⑤ 用匿名分享接口：列文件 → 取 manifest → 下载两个包 → 校验
       · zip 比 sha256
       · 文件夹包解压后比树摘要
    ⑥ 删除三个文件与子目录，确认 test 里没有残留

退出码：0 通过；1 失败。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
import traceback
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from online import hashing, packing                              # noqa: E402
from online.errors import OnlineError                            # noqa: E402
from online.manifest import normalize, save                      # noqa: E402
from online.provider_lanzou import MANIFEST_NAME, LanzouShare    # noqa: E402
from online.provider_lanzou_account import LanzouAccount         # noqa: E402

FOLDER_NAME = "test"
SUBFOLDER = "_pulses_probe"


def step(title: str) -> float:
    print(f"\n=== {title} ===")
    return time.perf_counter()


def done(start: float) -> None:
    print(f"    用时 {time.perf_counter() - start:.2f}s")


def build_assets(base: Path) -> tuple[Path, Path, list[dict]]:
    """造两个枪包 + 返回 manifest 的 files 数组。"""
    raw_zip = base / "alpha.zip"
    with zipfile.ZipFile(raw_zip, "w") as zf:
        zf.writestr("alpha/pack.json", json.dumps({"gun": "alpha"}))
        zf.writestr("alpha/textures/a.png", "PNG" * 500)

    folder = base / "beta"
    (folder / "textures").mkdir(parents=True)
    (folder / "pack.json").write_text(json.dumps({"gun": "beta"}),
                                     encoding="utf-8")
    (folder / "textures" / "b.png").write_text("PNG" * 800, encoding="utf-8")
    beta_zip = base / "beta.zip"
    packing.pack_folder(str(folder), str(beta_zip))

    files = [
        {"path": "alpha.zip", "type": "zip",
         "size": raw_zip.stat().st_size,
         "packed_size": raw_zip.stat().st_size,
         "sha256": hashing.sha256_file(str(raw_zip))},
        {"path": "beta.zip", "type": "folder", "target": "beta",
         "size": hashing.tree_digest(str(folder))[1],
         "files": hashing.tree_digest(str(folder))[2],
         "packed_size": beta_zip.stat().st_size,
         "sha256": hashing.tree_digest(str(folder))[0]},
    ]
    return raw_zip, beta_zip, files


def main() -> int:
    user = os.environ.get("PULSES_LANZOU_USER", "").strip()
    password = os.environ.get("PULSES_LANZOU_PASS", "")
    if not user or not password:
        print("缺少凭据：请设置 PULSES_LANZOU_USER / PULSES_LANZOU_PASS")
        return 1

    temp = Path(tempfile.mkdtemp(prefix="pulses_pub_"))
    account = LanzouAccount(timeout=120)
    sub_id = None
    uploaded_ids: list[int] = []
    ok = True

    try:
        # ---------- ① 登录 ----------
        start = step("登录")
        account.login(user, password)
        print(f"    uid 长度 {len(account.uid)}")
        done(start)

        # ---------- ② 建子目录 ----------
        start = step(f"在 {FOLDER_NAME} 下建临时目录 {SUBFOLDER}")
        parent = next((f for f in account.list_folders(-1)
                       if f["name"].strip().lower() == FOLDER_NAME), None)
        if parent is None:
            print(f"    没找到 {FOLDER_NAME} 文件夹，中止")
            return 1
        sub_id = account.ensure_folder(SUBFOLDER, parent["id"])
        print(f"    子目录 id {sub_id}")
        done(start)

        # ---------- ③ 造包 ----------
        start = step("造测试枪包")
        raw_zip, beta_zip, files = build_assets(temp)
        for entry in files:
            print(f"    {entry['path']}  {entry['size']} 字节  "
                  f"sha256 {entry['sha256'][:12]}…")
        done(start)

        # ---------- ④ 上传 ----------
        start = step("上传两个包 + manifest")
        for local, name in ((raw_zip, "alpha.zip"), (beta_zip, "beta.zip")):
            t0 = time.perf_counter()
            info = account.upload(str(local), sub_id)
            uploaded_ids.append(int(info["id"]))
            if info["name"] != name:
                print(f"    失败：{name} 被改名成 {info['name']}")
                ok = False
            print(f"    {name}  {local.stat().st_size} 字节  "
                  f"{time.perf_counter() - t0:.2f}s")
        manifest = normalize({"name": "真实闭环", "version": "v1.0.0",
                              "generation": 1, "files": files})
        manifest_path = temp / MANIFEST_NAME
        save(manifest, manifest_path)
        info = account.upload(str(manifest_path), sub_id)
        uploaded_ids.append(int(info["id"]))
        print(f"    manifest {manifest_path.stat().st_size} 字节")
        done(start)

        # ---------- ⑤ 匿名分享 → 下载 → 校验 ----------
        start = step("匿名分享：列表 / manifest / 下载 / 校验")
        share = account.folder_share(sub_id)
        print(f"    分享链接 {share['url']}")
        reader = LanzouShare(share["url"], share["password"], timeout=60,
                             retries=2)
        listing = reader.list_files()
        print(f"    列表 {len(listing)} 个文件")
        remote_manifest = next((f for f in listing
                                if f["name"] == MANIFEST_NAME), None)
        if remote_manifest is None:
            print("    失败：匿名列表里没有 manifest")
            ok = False
        else:
            raw = reader.fetch_bytes(remote_manifest["file_id"],
                                     raw_id=remote_manifest["raw_id"])
            fetched = normalize(json.loads(raw.decode("utf-8")))
            if fetched["generation"] != 1 or len(fetched["files"]) != 2:
                print("    失败：manifest 内容不对")
                ok = False
            else:
                print("    manifest 读回正常（generation 1，2 个文件）")

        for entry in files:
            remote = next((f for f in listing
                           if f["name"] == entry["path"]), None)
            if remote is None:
                print(f"    失败：列表里没有 {entry['path']}")
                ok = False
                continue
            target = temp / "down" / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            t0 = time.perf_counter()
            size = reader.download(remote["file_id"], str(target),
                                   raw_id=remote["raw_id"],
                                   expected_size=entry["packed_size"])
            cost = time.perf_counter() - t0
            if entry["type"] == "folder":
                unpacked = temp / "down" / "beta_unpacked"
                packing.unpack_to(str(target), str(unpacked))
                digest, total, count = hashing.tree_digest(str(unpacked))
                if digest != entry["sha256"]:
                    print(f"    失败：{entry['path']} 树摘要不一致")
                    ok = False
                else:
                    print(f"    {entry['path']}  解压后 {count} 个文件 / "
                          f"{total} 字节，树摘要一致  {cost:.2f}s")
            else:
                digest = hashing.sha256_file(str(target))
                if digest != entry["sha256"]:
                    print(f"    失败：{entry['path']} sha256 不一致")
                    ok = False
                else:
                    print(f"    {entry['path']}  {size} 字节，sha256 一致  "
                          f"{cost:.2f}s")
        done(start)

    except Exception:
        print("\n!!! 异常：")
        traceback.print_exc()
        ok = False
    finally:
        # ---------- ⑥ 清理 ----------
        print("\n=== 清理 ===")
        try:
            if sub_id is not None:
                for row in account.list_files(sub_id):
                    if row["name"] in ("alpha.zip", "beta.zip", MANIFEST_NAME):
                        removed = account.delete_file(row["id"])
                        print(f"    删除 {row['name']}: {removed}")
                left = account.list_files(sub_id)
                if left:
                    print(f"    失败：子目录还有残留 {[f['name'] for f in left]}")
                    ok = False
                else:
                    removed = account.delete_folder(sub_id)
                    print(f"    删除子目录: {removed}")
                    if not removed:
                        ok = False
        except Exception:
            print("    清理时出错：")
            traceback.print_exc()
            ok = False
        try:
            import shutil
            shutil.rmtree(temp, ignore_errors=True)
        except Exception:
            pass

    print("\n" + "=" * 56)
    print("真实发布闭环：全部通过" if ok else "真实发布闭环：有失败项")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
