"""一键化真实云端验收：全部通过 AppController（本软件）执行。

覆盖两个预设同时“一键上传全部 / 一键更新全部”，并在第二次发布时验证
单个预设失败隔离/增量更新。云端会留下 AutoTest-A/B 两个小目录。
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from online.service import OnlineService
from pulses_web.controller import AppController

ACCOUNT = Path("/tmp/ps_live/pack_dev/PulsesSwap_database/.online/account.json")
SHARE = "https://nimshade.lanzoul.com/b013a3htej"


def make_pack(root: Path, tag: str) -> Path:
    pack = root / f"pack-{tag}"
    tacz = pack / "tacz"
    tacz.mkdir(parents=True)
    (tacz / "alpha.zip").write_bytes((b"alpha-" + tag.encode()) * 16)
    (tacz / "beta.zip").write_bytes((b"beta-" + tag.encode()) * 16)
    return pack


def make_db(root: Path, tag: str) -> Path:
    db = root / f"db-{tag}"
    (db / ".online").mkdir(parents=True)
    shutil.copy2(ACCOUNT, db / ".online/account.json")
    return db


def open_controller(pack: Path, db: Path, role: str):
    ctrl = AppController(base_dir=db)
    ctrl.settings.storage_mode = "merged"
    ctrl.settings.role = role
    ctrl.settings.save()
    ctrl.open_pack(str(pack))
    svc = OnlineService(ctrl.db_path, account_db=str(db), app_version="3.1.0")
    assert svc.has_account(), "测试账号未加载"
    ctrl.online = svc
    ctrl.settings.role = role
    ctrl.settings.save()
    return ctrl, svc


def add_files(ctrl, preset: str, tag: str, a: bytes, b: bytes):
    ctrl.create_preset(preset)
    path = Path(ctrl.preset_manager.presets[preset]["path"])
    (path / "alpha.zip").write_bytes(a)
    (path / "beta.zip").write_bytes(b)
    return path


def bind(ctrl, preset, share, cloud, pwd=""):
    ctrl.bind_source(preset, share, pwd, cloud_path=cloud)


def main():
    root = Path(tempfile.mkdtemp(prefix="ps_auto_e2e_"))
    stamp = time.strftime("%m%d-%H%M%S")
    cloud_a = f"/PulsesSwap/AutoTest-{stamp}-A"
    cloud_b = f"/PulsesSwap/AutoTest-{stamp}-B"
    print("临时目录:", root)
    try:
        dev_pack = make_pack(root, "dev")
        dev_db = make_db(root, "dev")
        dev, dsvc = open_controller(dev_pack, dev_db, "developer")
        a_path = add_files(dev, "AutoDevA", "A", b"A" * 1024, b"B" * 2048)
        b_path = add_files(dev, "AutoDevB", "B", b"C" * 1024, b"D" * 2048)
        bind(dev, "AutoDevA", SHARE, cloud_a)
        bind(dev, "AutoDevB", SHARE, cloud_b)
        out = dev.publish_all_auto()
        print("开发一键上传全部:", out["message"])
        assert set(out["result"]["published"]) == {"AutoDevA", "AutoDevB"}, out
        shares = {}
        for name in ("AutoDevA", "AutoDevB"):
            src = dsvc.source_of(name)
            shares[name] = (src.get("share_url") or (src.get("lanzou") or {}).get("url"),
                            src.get("share_password") or (src.get("lanzou") or {}).get("password", ""))
            assert shares[name][0], f"{name} 没有分享链接"
            manifest = dsvc.load_cloud_manifest(name)
            assert manifest and manifest.get("files"), f"{name} manifest 为空"
            print(name, "版本:", manifest.get("version"), "链接:", shares[name][0][:52])

        player_pack = make_pack(root, "player")
        player_db = make_db(root, "player")
        player, psvc = open_controller(player_pack, player_db, "player")
        pa_path = add_files(player, "AutoPlayerA", "PA", b"", b"")
        pb_path = add_files(player, "AutoPlayerB", "PB", b"", b"")
        bind(player, "AutoPlayerA", shares["AutoDevA"][0], cloud_a, shares["AutoDevA"][1])
        bind(player, "AutoPlayerB", shares["AutoDevB"][0], cloud_b, shares["AutoDevB"][1])
        out = player.sync_all_auto()
        print("玩家一键更新全部:", out["message"])
        assert set(out["result"]["updated"]) == {"AutoPlayerA", "AutoPlayerB"}, out
        assert (pa_path / "alpha.zip").read_bytes() == b"A" * 1024
        assert (pb_path / "beta.zip").read_bytes() == b"D" * 2048
        # 已应用的预设，一键更新后必须自动替换 tacz
        player.apply_preset("AutoPlayerA")
        tacz_alpha = player_pack / "tacz" / "alpha.zip"
        assert tacz_alpha.read_bytes() == b"A" * 1024

        # 开发者已应用 A 时直接改 tacz，再一键上传，验证发布后仍能恢复应用状态
        dev.apply_preset("AutoDevA")
        (dev_pack / "tacz" / "alpha.zip").write_bytes(b"A2" * 2048)
        out = dev.publish_all_auto()
        print("开发增量一键上传:", out["message"])
        assert out["result"]["published"] == ["AutoDevA"], out
        assert "AutoDevB" in out["result"]["unchanged"], out
        assert (dev_pack / "tacz" / "alpha.zip").read_bytes() == b"A2" * 2048, "发布后未恢复应用状态"
        out = player.sync_all_auto()
        print("玩家增量一键更新:", out["message"])
        assert out["result"]["updated"] == ["AutoPlayerA"], out
        assert tacz_alpha.read_bytes() == b"A2" * 2048, "已应用预设没有自动替换"
        assert (pb_path / "alpha.zip").read_bytes() == b"C" * 1024
        print("PASS 多预设一键上传/一键更新真实云端闭环（含自动替换）")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
