"""
两端全流程端到端测试：开发者发布 → 玩家同步 → 改版 → 再同步 → 删除枪包。

跑的是真实界面代码路径（OnlineMixin 的方法），背后是真实的 OnlineService
和两个本地复刻的蓝奏服务（账号接口 + 分享接口）。

    python packaging/online_e2e.py

退出码：0 全部通过；1 有失败。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import traceback
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import pulses_swap as ps  # noqa: E402

from mock_lanzou_account import MockLanzouAccount  # noqa: E402
from online import diff, hashing, paths  # noqa: E402
from online.manifest import loads  # noqa: E402
from online.provider_lanzou import MANIFEST_NAME  # noqa: E402

FAILURES: list[str] = []


def check(message, condition, detail=None):
    """message 在前、条件在后：check("发布成功", result.ok)。"""
    if condition:
        print(f"  ok   {message}")
    else:
        print(f"  FAIL {message}" + (f"  {detail}" if detail is not None else ""))
        FAILURES.append(message)


def note(message):
    print(f"  --   {message}")


def pump(root, ms=200):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        try:
            root.update()
        except Exception:
            break
        time.sleep(0.004)


def pump_until(root, predicate, seconds=10.0, label=""):
    end = time.time() + seconds
    while time.time() < end:
        try:
            root.update()
        except Exception:
            break
        if predicate():
            return True
        time.sleep(0.01)
    if label:
        note(f"等待超时：{label}")
    return bool(predicate())


def wait_idle(app, root, name, seconds=15.0):
    """等某个预设的检查（含补查）彻底结束，避免读到上一轮的旧计划。"""
    end = time.time() + seconds
    while time.time() < end:
        try:
            root.update()
        except Exception:
            break
        if name not in app.online_checking \
                and name not in getattr(app, "_online_recheck", set()):
            return True
        time.sleep(0.01)
    return False


def refresh_online(app, root, name, seconds=15.0):
    """丢掉缓存状态 → 重新检查 → 等新计划。"""
    wait_idle(app, root, name)
    app.online_states.pop(name, None)
    app._online_check(name)
    wait_idle(app, root, name)
    return pump_until(
        root, lambda: (app._online_state(name) or {}).get("plan") is not None,
        seconds)


def close_overlays(root):
    """关掉所有还开着的覆盖层（发布成功后的分享框之类）。"""
    try:
        stack = list(getattr(ps, "_OVERLAY_STACK", []))
        for card in reversed(stack):
            try:
                card.close(True)
            except Exception:
                pass
        pump(root, 200)
    except Exception:
        pass


def make_zip(path: Path, name: str, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(name, payload)


def build_pack(base: Path) -> Path:
    pack = base / "pack"
    (pack / "tacz").mkdir(parents=True, exist_ok=True)
    db = pack / "PulsesSwap_database"
    preset = db / "测试预设"
    preset.mkdir(parents=True, exist_ok=True)
    make_zip(preset / "alpha.zip", "alpha.json", b'{"gun":"alpha"}')
    (preset / "beta").mkdir(exist_ok=True)
    (preset / "beta" / "pack.json").write_bytes(b'{"gun":"beta"}')
    (preset / "beta" / "textures").mkdir(exist_ok=True)
    (preset / "beta" / "textures" / "a.png").write_bytes(b"PNG" * 200)
    (preset / "readme.txt").write_bytes(b"hello world")
    (preset / "index.json").write_text(json.dumps({
        "name": "测试预设", "version": "v0.0.1", "gunpacks": {},
        "applied": False, "incremental_count": 0}, ensure_ascii=False),
        encoding="utf-8")
    (preset / "version.txt").write_text("v0.0.1", encoding="utf-8")
    return pack


def tree_signature(root: Path) -> dict:
    return {entry["path"]: entry["sha256"]
            for entry in hashing.scan_local(str(root))}


def run_child(pack: Path) -> tuple[int, str]:
    """在全新进程里重开一次程序，验证绑定与身份确实落盘了。"""
    import subprocess
    env = dict(os.environ)
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--child", str(pack)],
        capture_output=True, text=True, env=env, timeout=180)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def child_main(pack: Path) -> int:
    ps.DatabaseLocatorDialog.show = lambda self: None
    ps.DatabaseLocator.load_db_path = staticmethod(
        lambda: pack / "PulsesSwap_database")
    for module in (ps.dialogs, ps.utils, ps.app, ps.pages, ps.managers):
        for name in ("show_info", "show_warning", "show_error", "ask_yes_no",
                     "ask_ok_cancel", "show_message"):
            if hasattr(module, name):
                setattr(module, name, lambda *a, **k: None)

    root = ps.ctk.CTk()
    ps.apply_font_fallbacks()
    ps.sync_ui_scale(root)
    root.geometry("1280x900")
    root.update()
    app = ps.PulsesSwapApp(root)
    pump(root, 900)
    app.load_pack(pack)
    ok_load = pump_until(root, lambda: not app.loading_presets, 10)
    ok_bound = bool(app.online and app.online.is_bound("玩家预设"))
    ok_role = not app.is_developer
    app._online_check("玩家预设")
    ok_plan = pump_until(
        root, lambda: (app._online_state("玩家预设") or {}).get("plan")
        is not None, 15)
    plan = (app._online_state("玩家预设") or {}).get("plan")
    ok_clean = bool(plan and plan.is_clean)
    print(f"load={ok_load} bound={ok_bound} role_player={ok_role} "
          f"plan={ok_plan} clean={ok_clean}")
    if plan is not None:
        print("summary:", plan.summary())
    try:
        root.destroy()
    except Exception:
        pass
    return 0 if all((ok_load, ok_bound, ok_role, ok_plan, ok_clean)) else 1


def main() -> int:
    temp = Path(tempfile.mkdtemp(prefix="pulses_e2e_"))
    pack = build_pack(temp)
    dev_preset = pack / "PulsesSwap_database" / "测试预设"
    tacz = pack / "tacz"

    account = MockLanzouAccount("123456", "secret")
    account.start()

    ps.DatabaseLocatorDialog.show = lambda self: None
    ps.DatabaseLocator.load_db_path = staticmethod(
        lambda: pack / "PulsesSwap_database")
    for module in (ps.dialogs, ps.utils, ps.app, ps.pages, ps.managers):
        for name in ("show_info", "show_warning", "show_error", "ask_yes_no",
                     "ask_ok_cancel", "show_message"):
            if hasattr(module, name):
                setattr(module, name, lambda *a, **k: None)

    root = ps.ctk.CTk()
    ps.apply_font_fallbacks()
    ps.sync_ui_scale(root)
    root.geometry("1280x900")
    root.update()
    app = ps.PulsesSwapApp(root)
    pump(root, 900)
    app.load_pack(pack)
    check("整合包加载", pump_until(root, lambda: not app.loading_presets, 8))
    # e2e 用同一份整合包模拟两端，无法同时「已应用」；发布前的 applied 守卫
    # 由线上实测与 UI 自检覆盖，这里只测在线管线本身。
    app._online_guard_applied = lambda name, action: True
    app.online.account_base = account.base
    pump(root, 300)

    def state_of(name):
        return app._online_state(name)

    def plan_of(name):
        return (state_of(name) or {}).get("plan")

    try:
        # ============================================================
        print("\n=== 开发者端 ===")
        print("[1] 认证")
        app._developer_login("123456", "secret")
        check("登录并切换为开发者",
              pump_until(root, lambda: app.is_developer, 8))
        check("账号已记住", app.online.has_account())

        print("[2] 绑定云端路径并扫描差异")
        app._save_source("测试预设", "", "", "/PulsesSwap/测试预设", True)
        check("扫描出差异", pump_until(root, lambda: plan_of("测试预设"), 12),
              state_of("测试预设"))
        plan = plan_of("测试预设")
        check("待上传 3 项", plan.count_of(diff.UPLOAD) == 3, plan.summary())

        print("[3] 发布")
        selection = diff.selection_of(plan)
        app._run_publish("测试预设", plan, selection, "v2026.10.18", "首发")
        check("发布完成",
              pump_until(root, lambda: app._last_publish_result is not None, 30))
        result = app._last_publish_result
        check("发布成功", bool(result and result.ok),
              result.failed if result else None)
        check("上传了 3 个文件", result and len(result.uploaded) == 3)
        check("拿到分享链接", bool(result and result.share_url),
              result.share_url if result else None)
        check("generation = 1", result and result.generation == 1)
        close_overlays(root)

        folder_id = account.folder_id("测试预设",
                                      account.folder_id("PulsesSwap"))
        cloud_files = account.files_in(folder_id) if folder_id else {}
        check("云端有 4 个文件（3 枪包 + manifest）",
              len(cloud_files) == 4, sorted(cloud_files))
        manifest = loads(cloud_files.get(MANIFEST_NAME, b"{}").decode("utf-8"),
                         fmt="cfg")
        check("manifest 版本正确", manifest.get("version") == "v2026.10.18",
              manifest.get("version"))

        print("[4] 再扫一次应当没有待上传")
        app.online_states.pop("测试预设", None)
        app._online_check("测试预设")
        ok_second = pump_until(root, lambda: plan_of("测试预设") is not None, 12)
        if not ok_second:
            note(f"状态：{state_of('测试预设')}")
            note(f"checking={app.online_checking}")
        check("二次扫描完成", ok_second)
        plan2 = plan_of("测试预设")
        if plan2 is None:
            raise RuntimeError("二次扫描没有产出计划")
        check("没有待上传项", plan2.count_of(diff.UPLOAD) == 0, plan2.summary())

        # ============================================================
        print("\n=== 玩家端 ===")
        app._set_role("player")
        pump(root, 200)
        check("已切回玩家", not app.is_developer)

        print("[5] 新建空预设并绑定分享链接")
        app.preset_manager.create_preset("玩家预设")
        app.preset_manager.load_all_presets(use_cache=False)
        app._update_preset_list()
        pump(root, 300)
        check("玩家预设已创建", "玩家预设" in app.preset_manager.presets)

        share = app.online.source_of("测试预设")
        app._save_source("玩家预设", share.get("share_url", ""),
                         share.get("share_password", ""), "", True)
        check("检查到 3 个待下载",
              pump_until(root, lambda: plan_of("玩家预设") is not None, 15),
              state_of("玩家预设"))
        player_plan = plan_of("玩家预设")
        check("待下载 3 项", player_plan.count_of(diff.DOWNLOAD) == 3,
              player_plan.summary())

        print("[6] 同步")
        app._run_sync("玩家预设", player_plan,
                      diff.selection_of(player_plan))
        check("同步完成",
              pump_until(root, lambda: app._last_sync_result is not None, 40))
        sync_result = app._last_sync_result
        check("同步成功", bool(sync_result and sync_result.ok),
              sync_result.failed if sync_result else None)
        check("安装 3 项", sync_result and len(sync_result.installed) == 3)

        player_root = Path(app.preset_manager.presets["玩家预设"]["path"])
        dev_sig = tree_signature(dev_preset)
        player_sig = tree_signature(player_root)
        check("内容与开发者完全一致", dev_sig == player_sig,
              (sorted(dev_sig), sorted(player_sig)))
        index = json.loads((player_root / "index.json").read_text("utf-8"))
        check("index.json 版本已更新", index.get("version") == "v2026.10.18",
              index.get("version"))
        check("index.json 记录了 3 个枪包", len(index.get("gunpacks") or {}) == 3,
              list(index.get("gunpacks") or {}))

        print("[7] 再检查一次应当已是最新")
        check("检查完成", refresh_online(app, root, "玩家预设"))
        check("已无差异", plan_of("玩家预设").is_clean,
              plan_of("玩家预设").summary())
        # 同步结束会触发一次补查，等卡片从「检查中」落定再断言
        pump_until(root, lambda: "检查中" not in
                   app._preset_card_data("玩家预设")["status"], 10)
        data = app._preset_card_data("玩家预设")
        check("卡片显示已是最新", "已是最新" in data["status"], data["status"])
        check("卡片状态点是绿色", data["dot_color"] == ps.C_SUCCESS,
              data["dot_color"])

        # ============================================================
        print("\n=== 应用预设后的同步（内容在 tacz 目录） ===")
        print("[8] 应用预设")
        ok = app.preset_manager.apply_preset("玩家预设")
        check("应用成功", ok)
        app.preset_manager.reload_preset("玩家预设")
        app._update_preset_list()
        pump(root, 400)
        check("tacz 里有 3 个枪包",
              len([p for p in tacz.iterdir() if p.name != "tacz_default_gun"]) == 3,
              sorted(p.name for p in tacz.iterdir()))

        print("[9] 开发者改一个文件再发布")
        app._set_role("developer")
        (dev_preset / "alpha.zip").write_bytes(b"changed alpha payload")
        check("检查完成", refresh_online(app, root, "测试预设"))
        plan3 = plan_of("测试预设")
        check("只有 alpha.zip 待上传",
              [i.path for i in plan3.items if i.action == diff.UPLOAD]
              == ["alpha.zip"], plan3.summary())
        app._run_publish("测试预设", plan3, diff.selection_of(plan3),
                         "v2026.10.19", "修 alpha")
        check("二次发布完成",
              pump_until(root, lambda: (app._last_publish_result or None)
                         and app._last_publish_result.version == "v2026.10.19",
                         30))
        check("二次发布成功", bool(app._last_publish_result.ok))
        check("generation = 2", app._last_publish_result.generation == 2)
        check("发布后本地版本已更新",
              app.preset_manager.presets["测试预设"]["version"] == "v2026.10.19",
              app.preset_manager.presets["测试预设"]["version"])
        close_overlays(root)

        print("[10] 玩家（已应用）同步更新")
        app._set_role("player")
        app._last_sync_result = None
        check("检查完成", refresh_online(app, root, "玩家预设"),
              state_of("玩家预设"))
        update_plan = plan_of("玩家预设")
        check("待下载 1 项（alpha.zip）",
              [i.path for i in update_plan.items
               if i.action == diff.DOWNLOAD] == ["alpha.zip"],
              update_plan.summary())
        app._run_sync("玩家预设", update_plan,
                      diff.selection_of(update_plan))
        check("同步完成",
              pump_until(root, lambda: app._last_sync_result is not None, 40))
        check("同步成功", bool(app._last_sync_result.ok),
              app._last_sync_result.failed)
        tacz_alpha = tacz / "alpha.zip"
        check("tacz 里的 alpha.zip 已更新",
              tacz_alpha.exists()
              and tacz_alpha.read_bytes() == b"changed alpha payload")
        app.preset_manager.reload_preset("玩家预设")
        check("index.json 版本 = v2026.10.19",
              app.preset_manager.presets["玩家预设"]["version"] == "v2026.10.19",
              app.preset_manager.presets["玩家预设"]["version"])

        # ============================================================
        print("\n=== 删除枪包 ===")
        print("[11] 开发者删掉 readme.txt 再发布")
        app._set_role("developer")
        (dev_preset / "readme.txt").unlink()
        check("检查完成", refresh_online(app, root, "测试预设"))
        plan4 = plan_of("测试预设")
        check("readme.txt 被判为云端多余",
              [i.path for i in plan4.items
               if i.action == diff.DELETE_CLOUD] == ["readme.txt"],
              plan4.summary())
        app._run_publish("测试预设",
                         plan4,
                         diff.selection_of(plan4, include_deletes=True),
                         "v2026.10.20", "删 readme")
        check("三次发布完成",
              pump_until(root, lambda: (app._last_publish_result or None)
                         and app._last_publish_result.version == "v2026.10.20",
                         30))
        check("云端已删除", bool(app._last_publish_result.deleted))
        close_overlays(root)

        print("[12] 玩家看到本地多余")
        app._set_role("player")
        check("检查完成", refresh_online(app, root, "玩家预设"))
        extra = [i for i in plan_of("玩家预设").items
                 if i.action == diff.ASK_DELETE_LOCAL]
        check("readme.txt 被判为本地多余",
              [i.path for i in extra] == ["readme.txt"],
              [i.path for i in extra])
        check("默认不勾选删除", not extra[0].default_checked if extra else False)

        print("[13] 勾选删除并同步")
        final_plan = plan_of("玩家预设")
        selection = diff.selection_of(final_plan, include_deletes=True)
        app._last_sync_result = None
        app._run_sync("玩家预设", final_plan, selection)
        check("同步完成",
              pump_until(root, lambda: app._last_sync_result is not None, 40))
        check("同步成功", bool(app._last_sync_result.ok),
              app._last_sync_result.failed)
        check("readme.txt 已删除", not (tacz / "readme.txt").exists())
        app.online_states.pop("玩家预设", None)
        app._online_check("玩家预设")
        pump_until(root, lambda: plan_of("玩家预设") is not None, 15)
        check("最终完全一致", plan_of("玩家预设").is_clean,
              plan_of("玩家预设").summary())

        # ============================================================
        print("\n=== 失败路径 ===")
        print("[14] 云端文件损坏 → 同步应当报失败而不是装坏")
        app._set_role("player")
        # 先让本地与云端不一致，制造一次下载
        (tacz / "alpha.zip").write_bytes(b"local edit")
        share_server = account.share_server(folder_id)
        if share_server is None:
            share_server = account._shares.get(folder_id)
        check("拿到分享服务", share_server is not None)
        cloud_now = app.online.load_cloud_manifest("玩家预设") or {}
        target_cloud = next(
            (str(e.get("cloud") or e.get("path"))
             for e in cloud_now.get("files") or []
             if e.get("path") == "alpha.zip"), "alpha.zip")
        share_server.corrupt(target_cloud)
        app.online_states.pop("玩家预设", None)
        app._last_sync_result = None
        app._online_check("玩家预设")
        check("检查完成",
              pump_until(root, lambda: plan_of("玩家预设") is not None, 15))
        broken_plan = plan_of("玩家预设")
        check("识别出待下载",
              [i.path for i in broken_plan.items
               if i.action == diff.DOWNLOAD] == ["alpha.zip"],
              broken_plan.summary())
        app._run_sync("玩家预设", broken_plan,
                      diff.selection_of(broken_plan))
        check("同步结束",
              pump_until(root, lambda: app._last_sync_result is not None, 40))
        broken = app._last_sync_result
        check("有失败项", bool(broken and broken.failed), broken.failed
              if broken else None)
        check("失败的是 alpha.zip",
              bool(broken and broken.failed
                   and broken.failed[0][0] == "alpha.zip"),
              broken.failed if broken else None)
        # 失败时正式目录里还是玩家原来的内容，不会被坏包覆盖
        check("失败时不会把坏文件装进去",
              (tacz / "alpha.zip").read_bytes() == b"local edit",
              (tacz / "alpha.zip").read_bytes()[:24])
        share_server.state.corrupt.discard(target_cloud)

        print("[14b] 修好云端后重试，应当恢复正常")
        app.online_states.pop("玩家预设", None)
        app._last_sync_result = None
        app._online_check("玩家预设")
        check("重新检查完成",
              pump_until(root, lambda: plan_of("玩家预设") is not None, 15))
        retry_plan = plan_of("玩家预设")
        app._run_sync("玩家预设", retry_plan,
                      diff.selection_of(retry_plan))
        check("重试同步完成",
              pump_until(root, lambda: app._last_sync_result is not None, 40))
        check("重试成功", bool(app._last_sync_result and
                             app._last_sync_result.ok),
              app._last_sync_result.failed if app._last_sync_result else None)
        check("文件已恢复成云端版本",
              (tacz / "alpha.zip").read_bytes() == b"changed alpha payload",
              (tacz / "alpha.zip").read_bytes()[:24])

        # ============================================================
        print("\n=== 重启后状态 ===")
        print("[15] 关掉重开（子进程）：绑定关系与身份都还在")
        close_overlays(root)
        try:
            root.destroy()
        except Exception:
            pass
        pump(root, 200)
        code, out = run_child(pack)
        for line in out.strip().splitlines():
            note(line)
        check("重启后玩家状态一致", code == 0)

        # ============================================================
        print("\n=== 收尾检查 ===")
        # 让最后触发的动画（卡片闪光 / 状态点 / Toast）自然收尾
        pump(root, 1400)
        check("没有残留遮罩", not ps._OVERLAY_STACK, len(ps._OVERLAY_STACK))
        check("没有残留补间", not ps._TWEENS, list(ps._TWEENS)[:3])
        check("staging 已清理",
              not any(paths.staging_root(app.online.db_path).glob("*")))
    except Exception:
        print("\n!!! 异常：")
        traceback.print_exc()
        FAILURES.append("运行异常")
    finally:
        try:
            root.destroy()
        except Exception:
            pass
        account.stop()
        shutil.rmtree(temp, ignore_errors=True)

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"失败 {len(FAILURES)} 项：")
        for item in FAILURES:
            print("  -", item)
        return 1
    print("两端全流程全部通过：发布 → 同步 → 改版 → 应用后更新 → 删除")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--child":
        raise SystemExit(child_main(Path(sys.argv[2])))
    raise SystemExit(main())
