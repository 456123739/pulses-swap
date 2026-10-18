"""
DPI / 缩放检查：在 100% / 125% / 150% 三档下重建界面，确认布局不被挤爆。

    python packaging/scale_check.py

每一档都在独立子进程里跑（Tk 的 UI 泵只能绑定一次 root），检查：

  · 侧边栏宽度够（没被内容压窄）
  · 左列三张卡（Step1/2/3）纵向装得下
  · 预设卡片高度、宽度正常，文字标签有尺寸
  · 同步弹窗在窗口内（不超出上下边界）
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SCALES = (1.0, 1.25, 1.5)
FAILURES: list[str] = []


def check(message, condition, detail=None):
    if condition:
        print(f"  ok   {message}")
    else:
        print(f"  FAIL {message}" + (f"  {detail}" if detail is not None else ""))
        FAILURES.append(f"[{os.environ.get('PULSES_SCALE', '?')}] {message}")


def pump(root, ms=200):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        try:
            root.update()
        except Exception:
            break
        time.sleep(0.004)


def pump_until(root, predicate, seconds=8.0):
    end = time.time() + seconds
    while time.time() < end:
        try:
            root.update()
        except Exception:
            break
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


def build_pack(base: Path) -> Path:
    pack = base / "pack"
    (pack / "tacz").mkdir(parents=True, exist_ok=True)
    db = pack / "PulsesSwap_database"
    for index, name in enumerate(("默认预设", "SSR预设包")):
        preset = db / name
        preset.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(preset / f"gun_{index}.zip", "w") as zf:
            zf.writestr("pack.json", b'{"index":%d}' % index)
        folder = preset / f"folder_{index}"
        folder.mkdir(exist_ok=True)
        (folder / "a.txt").write_bytes(b"hello" * 40)
        (preset / "index.json").write_text(json.dumps({
            "name": name, "version": f"v1.{index}.0", "gunpacks": {},
            "applied": index == 0, "incremental_count": 0},
            ensure_ascii=False), encoding="utf-8")
        (preset / "version.txt").write_text(f"v1.{index}.0", encoding="utf-8")
    return pack


def child(scale: float, pack: Path) -> int:
    os.environ["PULSES_SCALE"] = str(scale)
    import pulses_swap as ps

    ps.DatabaseLocatorDialog.show = lambda self: None
    ps.DatabaseLocator.load_db_path = staticmethod(
        lambda: pack / "PulsesSwap_database")
    for module in (ps.dialogs, ps.utils, ps.app, ps.pages, ps.managers):
        for name in ("show_info", "show_warning", "show_error", "ask_yes_no",
                     "ask_ok_cancel", "show_message"):
            if hasattr(module, name):
                setattr(module, name, lambda *a, **k: None)

    # 强制这一档缩放，再建界面（px() / tk_font() 读的是 config.UI_SCALE）
    ps.config.UI_SCALE = scale
    # 走真实的缩放锁：CTk 的自动 DPI 轮询会被摘掉（那段会闪 alpha）
    ps.lock_ctk_scaling(scale)
    root = ps.ctk.CTk()
    ps.apply_font_fallbacks()
    root.geometry("1280x900")
    root.update()
    app = ps.PulsesSwapApp(root)
    pump(root, 900)
    app.load_pack(pack)
    ok_load = pump_until(root, lambda: not app.loading_presets, 10)
    pump(root, 500)

    print(f"\n=== 缩放 {scale:.2f} · UI_SCALE {ps.config.UI_SCALE:.2f} ===")
    check("整合包加载完成", ok_load)

    # 侧边栏
    sidebar = app.sidebar
    expect_side = ps.px(ps.SIDEBAR_W)
    # 高 DPI 下窗口会被屏幕尺寸钳制，侧边栏允许被压缩 10%
    check(f"侧边栏宽度 {sidebar.winfo_width()} ≥ {expect_side * 0.9:.0f}",
          sidebar.winfo_width() >= expect_side * 0.9,
          (sidebar.winfo_width(), expect_side))

    # 左列两块（整合包 / 预设管理；详情条已移到右列顶部）
    left = app.pack_drop_area.master.master.master   # page → left_panel
    page = left.master
    groups = []
    for child_widget in left.winfo_children():
        groups.append(child_widget)
    total_h = sum(g.winfo_height() for g in groups)
    check(f"左列两块合计 {total_h} ≤ 容器 {left.winfo_height()}",
          total_h <= left.winfo_height() + 2,
          [(g.winfo_height()) for g in groups])
    # 真正要防的是「被压得比内容还矮」——那才会裁切
    clipped = [(g.winfo_height(), g.winfo_reqheight()) for g in groups
               if g.winfo_height() + 2 < g.winfo_reqheight()]
    check("左列两块都没有被压到内容以下", not clipped, clipped)
    check(f"左列宽度 {left.winfo_width()} 不超过页面 {page.winfo_width()}",
          left.winfo_width() <= page.winfo_width())

    # 预设列表至少能看到 3 条（列表是主界面主角）
    rows = app.preset_cards.winfo_height() // ps.px(92)
    check(f"预设列表高度 {app.preset_cards.winfo_height()} 可显示约 {rows} 条 ≥ 3",
          rows >= 3, app.preset_cards.winfo_height())

    # 预设卡片
    count = app.preset_cards.count()
    check("卡片渲染 2 张", count == 2, count)
    names = list(app.preset_manager.presets)
    card = app.preset_cards.card(names[0]) if names else None
    check("拿到卡片", card is not None)
    if card is not None:
        expect_h = ps.px(ps.H_CARD)
        check(f"卡片高度 {card.winfo_height()} ≈ {expect_h}",
              abs(card.winfo_height() - expect_h) <= 2,
              (card.winfo_height(), expect_h))
        check(f"卡片宽度 {card.winfo_width()} > 0", card.winfo_width() > 100)
        for label in (card.name_label, card.meta_label, card.status_label):
            text = str(label.cget("text"))
            check(f"标签可读：{text[:10]}",
                  label.winfo_width() > 20 and label.winfo_height() > 8,
                  (label.winfo_width(), label.winfo_height()))

    # 同步弹窗
    from online import diff
    from online.manifest import normalize
    plan = diff.compare(
        [{"path": "gun_0.zip", "type": "zip", "size": 1024,
          "sha256": "a" * 64, "packed_size": 1024}],
        normalize({"name": "x", "version": "v1", "generation": 1,
                   "files": [{"path": "gun_0.zip", "type": "zip", "size": 1024,
                              "sha256": "b" * 64, "packed_size": 1024}]}),
        role="player")
    app.online_states[names[0]] = {"phase": "ready", "error": "",
                                   "checked_at": time.time(), "plan": plan}
    app.open_sync_dialog(names[0])
    pump(root, 500)
    stack = getattr(ps, "_OVERLAY_STACK", [])
    check("同步弹窗已打开", bool(stack))
    if stack:
        card_widget = stack[-1].card
        win_h = root.winfo_height()
        win_w = root.winfo_width()
        check(f"弹窗高度 {card_widget.winfo_height()} ≤ 窗口 {win_h}",
              card_widget.winfo_height() <= win_h - 10,
              (card_widget.winfo_height(), win_h))
        check(f"弹窗宽度 {card_widget.winfo_width()} ≤ 窗口 {win_w}",
              card_widget.winfo_width() <= win_w - 10,
              (card_widget.winfo_width(), win_w))
        stack[-1].close(False)
        pump(root, 200)

    try:
        root.destroy()
    except Exception:
        pass
    return 0 if not FAILURES else 1


def main() -> int:
    temp = Path(tempfile.mkdtemp(prefix="pulses_scale_"))
    pack = build_pack(temp)
    try:
        for scale in SCALES:
            proc = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--child",
                 str(scale), str(pack)],
                capture_output=True, text=True, timeout=180)
            print(proc.stdout.rstrip())
            if proc.returncode != 0 and proc.stderr.strip():
                print(proc.stderr.rstrip()[-800:])
            if proc.returncode != 0:
                FAILURES.append(f"缩放 {scale} 子进程失败")
    finally:
        shutil.rmtree(temp, ignore_errors=True)

    print("\n" + "=" * 56)
    if FAILURES:
        print(f"失败 {len(FAILURES)} 项：")
        for item in FAILURES:
            print("  -", item)
        return 1
    print("三档缩放全部通过")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 3 and sys.argv[1] == "--child":
        raise SystemExit(child(float(sys.argv[2]), Path(sys.argv[3])))
    raise SystemExit(main())
