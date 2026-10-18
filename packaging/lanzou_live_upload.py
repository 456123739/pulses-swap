"""
真实蓝奏账号的上传验证（只在 test 文件夹里操作）。

凭据只从环境变量读，**不落盘、不打印、不进日志**：

    export PULSES_LANZOU_USER='账号'
    export PULSES_LANZOU_PASS='密码'
    python packaging/lanzou_live_upload.py

做的事（全部限制在根目录下的 test 文件夹内）：

    ① 登录
    ② 找到 test 文件夹（找不到就中止，绝不自己新建到别处）
    ③ 上传一个 2MB 的确定性测试文件
    ④ 列文件核对名字 / 大小
    ⑤ 取文件夹分享链接，用匿名接口把文件下载回来，比对 sha256
    ⑥ 收尾：默认把测试文件留在 test 文件夹里（方便去网页版看），
       加 --delete 则删除它

退出码：0 通过；1 失败。
"""
from __future__ import annotations

import hashlib
import os
import secrets
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from online import hashing                                   # noqa: E402
from online.errors import OnlineError                        # noqa: E402
from online.provider_lanzou import LanzouShare               # noqa: E402
from online.provider_lanzou_account import LanzouAccount     # noqa: E402

FOLDER_NAME = "test"
UPLOAD_MB = 2


def mask(value: str) -> str:
    """任何需要露出的标识都只给前两位。"""
    text = str(value or "")
    if not text:
        return "(空)"
    return text[:2] + "*" * max(0, len(text) - 2)


def step(title: str) -> float:
    print(f"\n=== {title} ===")
    return time.perf_counter()


def done(start: float, extra: str = "") -> None:
    print(f"    用时 {time.perf_counter() - start:.2f}s {extra}")


def build_payload(size_mb: int) -> bytes:
    """造一个约 size_mb 的 zip（蓝奏对扩展名有白名单，.zip 一定收）。"""
    import io
    import zipfile

    target = size_mb * 1024 * 1024
    block = hashlib.sha256(b"pulses-swap-upload-test").digest()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=1) as zf:
        written = 0
        index = 0
        while written < target:
            chunk = bytearray()
            while len(chunk) < 256 * 1024:
                chunk.extend(block)
                block = hashlib.sha256(block).digest()
            zf.writestr(f"payload/{index:03d}.bin", bytes(chunk))
            written += len(chunk)
            index += 1
    return buffer.getvalue()


def main() -> int:
    user = os.environ.get("PULSES_LANZOU_USER", "").strip()
    password = os.environ.get("PULSES_LANZOU_PASS", "")
    if not user or not password:
        print("缺少凭据：请设置 PULSES_LANZOU_USER / PULSES_LANZOU_PASS 环境变量")
        return 1

    print(f"账号：{mask(user)}")

    # ---------- ① 登录 ----------
    start = step("登录")
    account = LanzouAccount(timeout=120)
    try:
        account.login(user, password)
    except OnlineError as exc:
        print(f"    失败：{exc}")
        if exc.hint:
            print(f"    提示：{exc.hint}")
        return 1
    print(f"    登录成功 · uid {mask(account.uid)}")
    done(start)

    # ---------- ② 找 test 文件夹 ----------
    start = step(f"定位 {FOLDER_NAME} 文件夹")
    try:
        folders = account.list_folders(-1)
    except OnlineError as exc:
        print(f"    列文件夹失败：{exc}")
        return 1
    print(f"    根目录 {len(folders)} 个文件夹")
    for folder in folders:
        print(f"      #{folder['id']}  {folder['name']}")
    target = next((f for f in folders if f["name"].strip().lower() == FOLDER_NAME),
                  None)
    if target is None:
        print(f"    没找到名为 {FOLDER_NAME} 的文件夹，中止（不会往别处写）")
        return 1
    folder_id = target["id"]
    print(f"    使用文件夹 #{folder_id}  {target['name']}")
    done(start)

    # ---------- ③ 上传 ----------
    start = step(f"上传 {UPLOAD_MB}MB 测试文件")
    payload = build_payload(UPLOAD_MB)
    digest = hashlib.sha256(payload).hexdigest()
    name = f"_pulses_upload_test_{secrets.token_hex(4)}.zip"
    temp = Path(tempfile.mkdtemp(prefix="pulses_up_")) / name
    temp.write_bytes(payload)
    progress_state = {"last": 0.0}

    def progress(sent, total):
        now = time.time()
        if now - progress_state["last"] < 1.0 and sent < total:
            return
        progress_state["last"] = now
        print(f"    {sent / 1048576:5.2f} / {total / 1048576:.2f} MB")

    uploaded = None
    try:
        uploaded = account.upload(str(temp), folder_id, progress=progress)
    except OnlineError as exc:
        print(f"    上传失败：{exc}")
        if exc.hint:
            print(f"    提示：{exc.hint}")
        return 1
    finally:
        try:
            temp.unlink()
        except OSError:
            pass
        try:
            temp.parent.rmdir()
        except OSError:
            pass
    print(f"    上传完成 · 文件 id {uploaded.get('id')} · 名字 {uploaded.get('name')}")
    done(start)

    ok = True
    try:
        # ---------- ④ 列文件核对 ----------
        start = step("列文件核对")
        files = account.list_files(folder_id)
        match = next((f for f in files if f["name"] == name), None)
        if match is None:
            print(f"    失败：云端列表里没有 {name}")
            ok = False
        else:
            print(f"    找到 {match['name']} · {match['size']}")
        done(start)

        # ---------- ⑤ 分享 → 匿名下载 → 校验 ----------
        start = step("取分享链接并用匿名接口下载回来")
        try:
            share_info = account.folder_share(folder_id)
            print(f"    分享链接：{share_info['url']}")
            print(f"    分享密码：{mask(share_info['password']) if share_info['password'] else '(无)'}")
            reader = LanzouShare(share_info["url"], share_info["password"],
                                 timeout=60, retries=2)
            listing = reader.list_files()
            print(f"    匿名列表 {len(listing)} 个文件")
            remote = next((f for f in listing if f["name"] == name), None)
            if remote is None:
                print(f"    失败：匿名列表里没有 {name}")
                ok = False
            else:
                out_dir = Path(tempfile.mkdtemp(prefix="pulses_down_"))
                target_path = out_dir / name
                try:
                    size = reader.download(remote["file_id"], str(target_path),
                                           raw_id=remote["raw_id"],
                                           expected_size=len(payload))
                    got = hashing.sha256_file(str(target_path))
                    print(f"    下载 {size} 字节 · sha256 {got[:16]}…")
                    if got != digest:
                        print(f"    失败：哈希不一致（期望 {digest[:16]}…）")
                        ok = False
                    else:
                        print("    哈希一致")
                finally:
                    try:
                        target_path.unlink()
                    except OSError:
                        pass
                    try:
                        out_dir.rmdir()
                    except OSError:
                        pass
        except OnlineError as exc:
            print(f"    失败：{exc}")
            if exc.hint:
                print(f"    提示：{exc.hint}")
            ok = False
        done(start)

        # ---------- ⑥ 收尾 ----------
        start = step("收尾")
        keep = "--delete" not in sys.argv
        if keep:
            print(f"    已保留在 {FOLDER_NAME} 文件夹：{name}")
            print(f"    大小 {len(payload) / 1048576:.2f} MB · "
                  f"sha256 {digest}")
        elif uploaded and uploaded.get("id"):
            removed = account.delete_file(uploaded["id"])
            print(f"    {'已删除' if removed else '删除失败'}")
            if not removed:
                ok = False
        remaining = [f["name"] for f in account.list_files(folder_id)
                     if f["name"] == name]
        if keep:
            if not remaining:
                print("    失败：文件不见了（本该保留）")
                ok = False
            else:
                print("    已确认文件在云端")
        elif remaining:
            print(f"    失败：云端还有残留 {remaining}")
            ok = False
        done(start)
    except Exception:
        print("\n!!! 异常：")
        traceback.print_exc()
        ok = False
        # 尽力清理，别在用户网盘里留垃圾
        try:
            if uploaded and uploaded.get("id"):
                account.delete_file(uploaded["id"])
                print("    已尝试删除测试文件")
        except Exception:
            pass

    print("\n" + "=" * 56)
    print("真实上传链路：全部通过" if ok else "真实上传链路：有失败项")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
