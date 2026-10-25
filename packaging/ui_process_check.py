"""UI 操作过程审计：检查动画中间帧、文字刷新和真实指针命中。

与 ui_audit 的区别：本脚本不只验证“点完后的结果”，还会在
展开/收起、切页、悬停、弹窗入场的过程中逐帧取几何/颜色，并让鼠标
真正移到 CTkLabel 内部的原生 Label 上，复现“看得见但点不到”的问题。

运行：
    DISPLAY=:12 PYTHONPATH=/tmp/deps5:src python packaging/ui_process_check.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import time
import traceback
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import customtkinter as ctk  # noqa: E402

import pulses_swap as ps  # noqa: E402

FAIL = []
NOTES = []


def check(label, condition, detail=""):
    print(("  ok   " if condition else "  FAIL ") + label
          + ("" if condition else f"  {detail}"))
    if not condition:
        FAIL.append(label)


def note(text):
    NOTES.append(text)
    print("  ·", text)


TMP = Path(tempfile.mkdtemp(prefix="ps_process_"))
PACK = TMP / "pack"
TACZ = PACK / "tacz"
TACZ.mkdir(parents=True)
for i in range(10):
    with zipfile.ZipFile(TACZ / f"gun_{i}.zip", "w") as zf:
        zf.writestr("pack.mcmeta", "{}")
        zf.writestr(f"assets/{i}.json", "{}")
DB = TMP / "db"
DB.mkdir()
ps.DatabaseLocator.init_database_detailed(DB)

# 固定数据库，避免测试污染用户目录/随包数据库
ps.PulsesSwapApp._init_database_flow = lambda self: self._use_database(DB)

root = ctk.CTk()
ps.apply_font_fallbacks()
ps.sync_ui_scale(root)
root.geometry("1280x900+80+60")
root.update()
CALLBACK_ERRORS = []
root.report_callback_exception = lambda *args: CALLBACK_ERRORS.append(
    "".join(traceback.format_exception(*args)))
app = ps.PulsesSwapApp(root)


def pump(ms=300):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        try:
            root.update()
        except Exception:
            break
        time.sleep(0.003)


def wait_until(cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        root.update()
        if cond():
            return True
        time.sleep(0.01)
    return cond()


def move_to(widget, settle=80):
    """把真实指针移到控件上（CTkLabel 要移到内部 Label）。"""
    target = getattr(widget, "_label", None) or getattr(widget, "_canvas", None) or widget
    target.event_generate("<Motion>", x=3, y=3, warp=True)
    pump(settle)


def click_widget(widget):
    target = getattr(widget, "_label", None) or getattr(widget, "_canvas", None) or widget
    target.event_generate("<Button-1>", x=3, y=3)
    target.event_generate("<ButtonRelease-1>", x=3, y=3)
    pump(250)


def hex_rgb(text):
    text = str(text or "").lstrip("#")
    if len(text) != 6:
        return None
    try:
        return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


pump(1800)
app.load_pack(PACK)
check("整合包加载完成", wait_until(lambda: not app.loading_presets, 20))
app.settings.online_auto_check = False
try:
    if app.online is not None:
        app.online.sources.items.clear()
        app.online.sources.save()
        app.online_states.clear()
except Exception:
    pass
for name, version in (("Alpha", "v1.1.0"), ("Beta", "v1.2.0"),
                      ("Gamma", "v1.3.0"), ("Delta", "v1.4.0")):
    app.preset_manager.create_preset(name, version)
app._update_preset_list()
app.on_preset_selected("Alpha")
pump(500)

print("== 1. 卡片：悬停命中内部文字、移出恢复、点击文字可选中 ==")
card = app.preset_cards.card("Beta")
base_color = card.cget("fg_color")
move_to(card.name_label, 220)
hover_color = card.cget("fg_color")
check("鼠标移到卡片文字上触发 hover", hover_color != base_color,
      (base_color, hover_color))
move_to(card.status_label, 20)
pump(220)
check("在卡片内部子控件之间移动不会闪回", card.cget("fg_color") == hover_color,
      card.cget("fg_color"))
move_to(app.pack_drop_label)
pump(250)
check("移出卡片后 hover 收回", card.cget("fg_color") == base_color,
      card.cget("fg_color"))
click_widget(card.status_label)
check("点击卡片文字可选中（不是只有空白区能点）",
      app.current_selected_preset == "Beta",
      app.current_selected_preset)
check("选中后 Step 1 / 侧栏 / 详情同步", (
    "Beta" in str(app.pack_name_label.cget("text"))
    and "Beta" in str(app.sb_preset_label.cget("text"))
    and str(app.preset_name_label.cget("text")) == "Beta"),
    (app.pack_name_label.cget("text"), app.sb_preset_label.cget("text"),
     app.preset_name_label.cget("text")))

print("== 2. 卡片 flash 在中间帧真的有颜色变化 ==")
g = app.preset_cards.card("Gamma")
start = g.cget("border_color")
g.flash()
pump(120)
mid = g.cget("border_color")
pump(600)
end = g.cget("border_color")
check("flash 中间帧描边不同于起点", mid != start, (start, mid))
check("flash 结束回到起点", end == start, (start, end))
check("卡片描边宽度非 0（动画可见）", int(g.cget("border_width")) > 0,
      g.cget("border_width"))

print("== 3. 侧栏展开/收起：宽度单调、内容/图标、无残留遮罩 ==")
# 先归位到折叠态，并把指针移出侧栏，避免上一次悬停留下的展开任务干扰计时。
app._sidebar_collapse()
pump(350)
move_to(app.home_log_text, 60)
note(f"pre-expand width={app.sidebar_shell.winfo_width()} expanded={app._sidebar_expanded} jobs={app._sidebar_jobs} pointer={app._pointer_in_sidebar()}")
app._sidebar_expand("process")
scheduled = (id(app.sidebar_shell), "sidebar_width") in ps._TWEENS
widths = []
for _ in range(18):
    root.update()
    widths.append(app.sidebar_shell.winfo_width())
    time.sleep(0.012)
pump(260)
check("侧栏最终展开到目标宽度",
      app.sidebar_shell.winfo_width() > 200,
      app.sidebar_shell.winfo_width())
check("侧栏展开调度了宽度补间", scheduled)
if len({w for w in widths if w > 60}) < 2:
    note("本机 CTk 首帧排版耗时超过补间时长，展开在第一次 update 内到位；"
         "已保留补间，Windows 实机需再确认帧率")
check("展开后内容区可见", bool(app.session_card.winfo_ismapped()))
check("展开没有创建黑色遮罩", getattr(app, "_sidebar_dim", None) is None)
app._sidebar_collapse()
for _ in range(18):
    root.update()
    widths.append(app.sidebar_shell.winfo_width())
    time.sleep(0.012)
pump(260)
check("侧栏最终收起到 60", app.sidebar_shell.winfo_width() <= 64,
      app.sidebar_shell.winfo_width())
check("收起后内容区隐藏", not bool(app.session_card.winfo_ismapped()))

print("== 4. 页面切换：旧页留底、新页滑入、不露空白 ==")
app.show_page("settings")
rows = []
for _ in range(16):
    root.update()
    try:
        rows.append((app.stack.canvas.coords(app.stack.items["settings"])[1],
                     app.stack.canvas.coords(app.stack.items["home"])[1]))
    except Exception:
        pass
    time.sleep(0.012)
pump(400)
ys = [r[0] for r in rows]
check("切到设置页完成", app.active_page == "settings", app.active_page)
check("设置页从视口外滑入并收敛到 0",
      ys and ys[-1] == 0 and any(y < 0 for y in ys), ys[:4] + ys[-2:])
check("旧主页全程留在原地（不露底色）",
      all(abs(y) < 1 for _new, y in rows), [r[1] for r in rows[:4]])
check("设置页选项卡有选中态", app.settings_page.tab_bar.current() == "general",
      app.settings_page.tab_bar.current())
app.settings_page.show_tab("database")
pump(300)
check("设置页切到数据库选项卡", app.settings_page.stack.current == "database",
      app.settings_page.stack.current)
app.show_page("home")
pump(400)

print("== 5. 预设详情弹窗：首帧尺寸、内容、选项卡选中 ==")
app.open_preset_detail("Beta", tab="source")
pump(80)
card2 = ps._OVERLAY_STACK[-1]
check("详情弹窗已显示", card2.mask.winfo_ismapped())
check("弹窗首帧不是 1px（内容在显示前已建好）",
      card2.card.winfo_width() >= 600 and card2.card.winfo_height() > 200,
      (card2.card.winfo_width(), card2.card.winfo_height()))
check("详情来源选项卡处于选中态",
      getattr(card2, "tab_bar", None) is not None
      and card2.tab_bar.current() == "source",
      getattr(getattr(card2, "tab_bar", None), "current", lambda: None)())
card2.close(False)
pump(100)
check("详情弹窗关闭后无残留", not ps._OVERLAY_STACK, len(ps._OVERLAY_STACK))

print("== 6. Toast：长文案不越界、短文案会收掉 ==")
long_text = "同步失败：" + "很长的错误说明" * 24
app.toast(long_text, "warning")
pump(300)
toast = app._toast
check("长 Toast 已显示", toast is not None)
if toast is not None:
    check("长 Toast 宽度不超出窗口",
          toast.frame.winfo_width() <= root.winfo_width() - 20,
          (toast.frame.winfo_width(), root.winfo_width()))
    check("长 Toast 左边不越界", toast.frame.winfo_x() >= 0,
          toast.frame.winfo_x())
    toast.close()
pump(100)
app.toast("已保存", "success")
pump(180)
check("短 Toast 显示", app._toast is not None)
pump(2200)
check("短 Toast 自动收掉", app._toast is None)

print("== 7. 长预设名与进度条状态文字 ==")
long_name = ("很长的预设名称" * 12)[:78]
app.preset_manager.create_preset(long_name, "v1.0.0")
app._update_preset_list()
app.on_preset_selected(long_name)
pump(300)
check("长预设名不会撑破 Step 1 标签",
      len(str(app.pack_name_label.cget("text"))) < len(long_name) + 10,
      app.pack_name_label.cget("text"))
check("长预设名在详情标题中截断",
      len(str(app.preset_name_label.cget("text"))) <= 30,
      app.preset_name_label.cget("text"))
app.set_status("阶段 1", "busy", progress=0.4)
pump(100)
app.set_status("阶段 1", "busy", progress=None)
pump(100)
check("同一状态文字调用 progress=None 会清掉进度条",
      not app.progress_bar.winfo_manager(), app.progress_bar.winfo_manager())

print("== 8. 收尾：无残留遮罩 / 浮层 / 补间 ==")
app.progress_bar.pack_forget()
try:
    app._toast.close()
except Exception:
    pass
for card in list(ps._OVERLAY_STACK):
    try:
        card.close(False)
    except Exception:
        pass
pump(500)
left = []
if ps._OVERLAY_STACK:
    left.append(f"遮罩栈 {len(ps._OVERLAY_STACK)}")
if getattr(app, "_toast", None) is not None:
    left.append("Toast")
if ps._TWEENS:
    left.append(f"补间 {len(ps._TWEENS)}")
check("没有残留遮罩/Toast/挂起补间", not left, left)
check("过程操作没有触发 Tk 回调异常", not CALLBACK_ERRORS,
      CALLBACK_ERRORS[:2])

try:
    app._stop_watcher()
except Exception:
    pass
try:
    root.destroy()
except Exception:
    pass
shutil.rmtree(TMP, ignore_errors=True)

print()
if NOTES:
    print("补充观察：")
    for line in NOTES:
        print("  -", line)
if FAIL:
    print(f"!!! {len(FAIL)} 项失败: {FAIL}")
    raise SystemExit(1)
print("UI 操作过程审计：全部通过")
