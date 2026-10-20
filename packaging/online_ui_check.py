"""
在线界面冒烟：带一个真实数据库启动，把新界面全部走一遍，断言不抛异常。

    python packaging/online_ui_check.py

检查项：
  · 在线服务初始化成功、预设卡片渲染出来
  · 卡片尺寸/文案符合预期（没被裁、没有空标签）
  · 来源框 / 身份框 / 同步框 / 发布框都能构建并关闭
  · 检查更新能跑完（无网络时走"连接失败"分支，不能崩）
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

SRC = str(Path(__file__).resolve().parents[1] / "src")
sys.path.insert(0, SRC)

import pulses_swap as ps  # noqa: E402

FAILURES: list[str] = []


def check(condition, message):
    if condition:
        print(f"  ok   {message}")
    else:
        print(f"  FAIL {message}")
        FAILURES.append(message)


def pump(root, ms=300):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        try:
            root.update()
        except Exception:
            break
        time.sleep(0.004)


def make_zip(path: Path, name: str, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(name, payload)


def build_pack(base: Path) -> Path:
    """造一个整合包：<pack>/tacz + <pack>/PulsesSwap_database（隔离模式）。"""
    pack = base / "pack"
    (pack / "tacz").mkdir(parents=True, exist_ok=True)
    db = pack / "PulsesSwap_database"
    db.mkdir(parents=True, exist_ok=True)
    for index, name in enumerate(("默认预设", "SSR预设包")):
        preset = db / name
        preset.mkdir(parents=True, exist_ok=True)
        make_zip(preset / f"gun_{index}.zip", "pack.json",
                 b'{"index":%d}' % index)
        folder = preset / f"folder_{index}"
        folder.mkdir(exist_ok=True)
        (folder / "a.txt").write_bytes(b"hello" * 50)
        (preset / "index.json").write_text(json.dumps({
            "name": name, "version": f"v1.{index}.0",
            "gunpacks": {}, "applied": index == 0,
            "incremental_count": 0}, ensure_ascii=False), encoding="utf-8")
        (preset / "version.txt").write_text(f"v1.{index}.0", encoding="utf-8")
    return pack


def main() -> int:
    temp = Path(tempfile.mkdtemp(prefix="pulses_ui_"))
    pack = build_pack(temp)

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
    pump(root, 1200)
    app.load_pack(pack)
    pump(root, 2500)

    print("\n[1] 启动")
    check(app.db_ready, "数据库就绪")
    check(app.online is not None, "在线服务已初始化")
    check(app.preset_manager is not None
          and len(app.preset_manager.presets) == 2,
          f"预设加载（{len(app.preset_manager.presets if app.preset_manager else {})}）")
    check(app.preset_cards.count() == 2, "卡片渲染 2 张")

    print("\n[2] 卡片数据")
    for name in (app.preset_manager.presets or {}):
        data = app._preset_card_data(name)
        check(bool(data["name"]), f"{name} 有名字")
        check("个枪包" in data["meta"], f"{name} 元信息：{data['meta']}")
        check(bool(data["status"]), f"{name} 状态：{data['status']}")

    print("\n[3] 卡片几何")
    card = app.preset_cards.card(list(app.preset_manager.presets)[0])
    check(card is not None, "拿到卡片实例")
    if card is not None:
        pump(root, 200)
        check(card.winfo_height() >= ps.px(ps.H_CARD_MIN),
              f"卡片高度 {card.winfo_height()}")
        check(card.winfo_width() > 200, f"卡片宽度 {card.winfo_width()}")
        for label in (card.name_label, card.meta_label, card.status_label):
            text = label.cget("text")
            check(label.winfo_width() > 20, f"标签有宽度：{text[:12]}")
            check(label.winfo_height() > 8, f"标签有高度：{text[:12]}")

    print("\n[4] 身份")
    check(not app.is_developer, "默认是玩家")
    app.open_identity_dialog()
    pump(root, 250)
    check(True, "身份框构建成功")
    _close_top_card(root)
    app.settings.role = "developer"
    app.online.accounts.set("4654636", "secret", username="18651999816")
    # 侧边栏是折叠图标栏：账号行只在展开态可见，先展开再断言
    app._sidebar_expand("test")
    app._update_identity_ui()
    pump(root, 350)
    check(app.identity_badge.cget("text") == "开发者",
          f"身份徽标：{app.identity_badge.cget('text')}")
    check(app.identity_account.winfo_ismapped() == 1
          and app.identity_account.cget("text") == "186****9816",
          f"账号行显示打码手机号：{app.identity_account.cget('text')}")
    check("4654636" not in app.identity_badge.cget("text"),
          "会话 ID 不出现在徽标里")
    app.settings.role = "player"
    app._update_identity_ui()
    pump(root, 120)
    check(app.identity_account.winfo_ismapped() == 0,
          "玩家身份不显示账号行")
    app._sidebar_collapse()
    pump(root, 250)

    print("\n[5] 来源框")
    name = list(app.preset_manager.presets)[0]
    app.open_source_dialog(name)
    pump(root, 250)
    check(True, "来源框构建成功")
    _close_top_card(root)

    print("\n[5b] 来源页：只填云端路径也能测试连接")
    app.settings.role = "developer"
    app._update_identity_ui()
    app.online.set_cloud_path(name, "test")
    app.online.test_cloud_path = lambda path: {
        "path": path, "files": 2, "has_manifest": False}
    app.open_preset_detail(name, tab="source")
    pump(root, 300)
    card = ps.dialogs._OVERLAY_STACK[-1]
    test_btn = _find_by_text(card.card, "测试连接")
    check(test_btn is not None, "来源页有「测试连接」")
    if test_btn is not None:
        test_btn.invoke()
        pump(root, 600)
        texts = [_text(w) for w in _walk(card.card) if _text(w)]
        check(any("test" in t and "2 个文件" in t for t in texts),
              f"只填云端路径时能测通：{texts[:2]}")
    _close_top_card(root)
    app.settings.role = "player"
    app._update_identity_ui()

    print("\n[6] 检查更新（无网络 → 失败分支）")
    app.online.bind(name, "https://example.invalid/b000", "")
    app.online_states.pop(name, None)
    app._online_check(name)
    pump(root, 1500)
    state = app._online_state(name)
    check(state.get("phase") in ("error", "ready"), f"检查完成：{state.get('phase')}")
    data = app._preset_card_data(name)
    check(bool(data["status"]), f"失败也有状态文案：{data['status'][:24]}")

    print("\n[6b] 检查阶段文案")
    app.online_states[name] = {"phase": "checking", "phase_text": "读取云端…"}
    pump(root, 60)
    data = app._preset_card_data(name)
    check(data["status"] == "读取云端…", f"卡片显示阶段：{data['status']}")
    app._on_check_done(name, _fake_plan(), None)
    pump(root, 60)
    check("phase_text" not in app._online_state(name), "完成后清掉阶段文案")

    print("\n[7] 同步框（有 plan 时）")
    app.online.unbind(name)
    app.online_states.pop(name, None)
    app.open_source_dialog(name)
    pump(root, 200)
    _close_top_card(root)
    app.online_states[name] = {"phase": "ready", "error": "", "checked_at": time.time(),
                               "plan": _fake_plan()}
    app.open_sync_dialog(name)
    pump(root, 300)
    check(True, "同步框构建成功")
    _close_top_card(root)

    print("\n[8] 发布框（开发者 + 假计划）")
    app.settings.role = "developer"
    app._apply_role_actions()
    app._set_pack_dependent_buttons(True)
    check(str(app.publish_btn.cget("state")) == "normal",
          "开发者「发布到云端」按钮可用（不是禁用状态）")
    app.online.set_cloud_path(name, "/PulsesSwap/测试")
    app.online_states[name] = {"phase": "ready", "error": "", "checked_at": time.time(),
                               "plan": _fake_plan(role="developer")}
    app.open_publish_dialog(name)
    pump(root, 300)
    check(True, "发布框构建成功")
    _close_top_card(root)
    app.settings.role = "player"

    print("\n[9] 页面切换")
    for page in ("settings", "log", "home"):
        app.show_page(page)
        pump(root, 400)
    check(True, "三个页面都能切")

    print("\n[10] 收尾")
    try:
        root.destroy()
    except Exception:
        pass
    shutil.rmtree(temp, ignore_errors=True)

    print("\n" + ("全部通过" if not FAILURES else f"失败 {len(FAILURES)} 项"))
    for item in FAILURES:
        print("  -", item)
    return 0 if not FAILURES else 1


def _fake_plan(role="player"):
    from online import diff
    from online.manifest import normalize
    local = [{"path": "gun_0.zip", "type": "zip", "size": 1024,
              "sha256": "a" * 64, "packed_size": 1024}]
    cloud = normalize({"name": "测试", "version": "v9.9", "generation": 3,
                       "files": [
                           {"path": "gun_0.zip", "type": "zip", "size": 1024,
                            "sha256": "b" * 64, "packed_size": 1024},
                           {"path": "gun_new.zip", "type": "zip", "size": 2048,
                            "sha256": "c" * 64, "packed_size": 2048}]})
    return diff.compare(local, cloud, role=role)


def _walk(widget):
    yield widget
    try:
        children = widget.winfo_children()
    except Exception:
        return
    for child in children:
        yield from _walk(child)


def _text(widget):
    try:
        return str(widget.cget("text"))
    except Exception:
        return ""


def _find_by_text(widget, text):
    for item in _walk(widget):
        if _text(item) == text:
            return item
    return None


def _close_top_card(root):
    """关掉最上层的覆盖层卡片，避免遮罩挡住后续操作。"""
    try:
        from pulses import dialogs
        stack = getattr(dialogs, "_OVERLAY_STACK", [])
        if stack:
            stack[-1].close(False)
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    raise SystemExit(main())
