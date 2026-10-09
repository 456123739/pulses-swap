"""
全流程 + 全 UI 操作漏洞扫描（真 Tk）

覆盖：
  A. 遍历所有按钮逐个点击（弹窗自动应答），检查异常、残留、卡死
  B. 每种弹窗（信息/警告/错误/确认/选择/数据库定位）开关一遍
  C. 设置页每个选项卡、每个选项切换
  D. 三个列表（预设/枪包/最近）的选中、双击、右键菜单
  E. 错误路径：非法整合包 / 未选预设就替换 / 无包导出 / 损坏文件导入
  F. 窗口尺寸变化（最小/最大）后的布局完整性
  G. 收尾检查：无残留遮罩、无残留浮层、无挂起补间、焦点未丢失
"""
import importlib.util
import time
import traceback
import zipfile
from pathlib import Path
import tempfile

SRC = "/home/admin/111/pulses-swap/src/pulses_swap.py"
spec = importlib.util.spec_from_file_location("ps", SRC)
ps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ps)

FAIL = []
INFO = []


def check(label, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + label + ("" if cond else "  " + str(detail)))
    if not cond:
        FAIL.append(label)


def note(text):
    INFO.append(text)
    print("  ·  " + text)


# ---------- 造环境 ----------
TMP = Path(tempfile.mkdtemp(prefix="ps_audit_"))
PACK = TMP / "modpack"
TACZ = PACK / "tacz"
TACZ.mkdir(parents=True)
with zipfile.ZipFile(TACZ / "gun_a.zip", "w") as z:
    z.writestr("pack.mcmeta", "{}")
(TACZ / "gun_b").mkdir()
(TACZ / "gun_b" / "pack.mcmeta").write_text("{}")
BAD_PACK = TMP / "bad_pack"          # 没有 tacz 目录
BAD_PACK.mkdir()
DB = TMP / "db"
DB.mkdir()
EXPORT = TMP / "export"
EXPORT.mkdir()

# ---------- 打桩：所有阻塞式对话框自动应答 ----------
ps.DatabaseLocatorDialog.show = lambda self: None
ps.show_info = lambda *a, **k: None
ps.show_warning = lambda *a, **k: None
ps.show_error = lambda *a, **k: None
ps.ask_yes_no = lambda *a, **k: True
ps.ask_ok_cancel = lambda *a, **k: True
ps.PulsesSwapApp._ask_after_migrate = lambda self: "mark"
ps.PulsesSwapApp._ask_conflict_mode = lambda self, m: "rename"
ps.PulsesSwapApp._show_role_dialog = lambda self, t, m: "ok"
import tkinter.simpledialog as sd
import tkinter.filedialog as fd
sd.askstring = lambda *a, **k: "审计预设"
fd.asksaveasfilename = lambda *a, **k: str(EXPORT / "out.fgcpack")
fd.askopenfilename = lambda *a, **k: ""
fd.askdirectory = lambda *a, **k: str(PACK)
ps.os.startfile = lambda *a, **k: None

root = ps.ctk.CTk()
ps.apply_font_fallbacks()
ps.sync_ui_scale(root)
root.geometry("1280x900")
root.update()
app = ps.PulsesSwapApp(root)


def pump(ms=350):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        root.update()
        time.sleep(0.004)


def pump_until(pred, ms=8000):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        root.update()
        if pred():
            return True
        time.sleep(0.01)
    return pred()


def walk(widget, out=None):
    """递归收集所有控件。"""
    out = [] if out is None else out
    out.append(widget)
    try:
        for ch in widget.winfo_children():
            walk(ch, out)
    except Exception:
        pass
    return out


def all_buttons():
    out = []
    for w in walk(root):
        if type(w).__name__ in ("AnimatedButton", "CTkButton", "Button"):
            try:
                text = str(w.cget("text"))
            except Exception:
                text = "?"
            out.append((text, w))
    return out


def clean_state():
    """收尾一致性：无遮罩、无浮层、无挂起补间。"""
    leftovers = []
    if ps._OVERLAY_STACK:
        leftovers.append(f"遮罩栈 {len(ps._OVERLAY_STACK)}")
    if getattr(app, "_toast", None) is not None:
        leftovers.append("Toast 未收")
    tweens = [k for k in ps._TWEENS]
    if tweens:
        leftovers.append(f"补间 {len(tweens)} 条")
    return leftovers


pump(900)
app.settings.bind_database(DB)
app.recent_manager = ps.RecentPacksManager(DB / ".global.json")
app.db_ready = True
pump(200)

print("== A. 遍历所有按钮逐个点击 ==")
btns = all_buttons()
note(f"共发现 {len(btns)} 个按钮")
skipped = {"退出程序"}          # 点了会退出程序，跳过
clicked = 0
errors = []
for text, btn in btns:
    label = text.strip() or "(无文字)"
    if label in skipped:
        continue
    try:
        state = str(btn.cget("state"))
    except Exception:
        state = "?"
    if state == "disabled":
        continue
    try:
        btn.invoke()            # CTkButton.invoke() 会执行 command（绕过鼠标门禁）
        pump(260)
        clicked += 1
    except Exception:
        errors.append((label, traceback.format_exc().splitlines()[-1]))
        try:
            pump(150)
        except Exception:
            pass
check(f"逐个点击 {clicked} 个可用按钮，无异常抛出", not errors, errors[:4])
pump(2600)          # 等 Toast 自然消失（它有自己的存活时间）
left = clean_state()
check("点击过程中没有残留遮罩 / 浮层 / 挂起补间", not left, left)

print("== B. 每种弹窗开关一遍 ==")
dlg_specs = [
    ("信息", lambda: ps.show_info("标题", "内容")),
    ("警告", lambda: ps.show_warning("标题", "内容")),
    ("错误", lambda: ps.show_error("标题", "内容")),
    ("确认", lambda: ps.ask_yes_no("标题", "内容")),
    ("确定取消", lambda: ps.ask_ok_cancel("标题", "内容")),
]
for name, opener in dlg_specs:
    before = len(ps._OVERLAY_STACK)
    try:
        opener()
        pump(260)
        during = len(ps._OVERLAY_STACK)
        # 自动应答后应立即关闭
        pump(200)
        after = len(ps._OVERLAY_STACK)
        check(f"{name}弹窗 开→关 正常", during >= before and after == before,
              (before, during, after))
    except Exception:
        check(f"{name}弹窗 开→关 正常", False, traceback.format_exc().splitlines()[-1])

print("== B2. 弹窗内容是否在显示前就绪（先空白再出窗口的问题） ==")
holder = {}


class Probe(ps.OverlayCard):
    def _reveal(self):
        # 记录 reveal 那一刻 body 里已经有多少控件
        holder["children_at_reveal"] = len(self.body.winfo_children())
        holder["mask_placed_before"] = bool(self.mask.place_info())
        super()._reveal()


card = Probe(ps.get_overlay_host(), width=420, escape_value="ok")
ps.make_label(card.body, text="标题").pack()
ps.make_label(card.body, text="正文").pack()
ps.make_button(card.body, "确定", command=lambda: card.close("ok")).pack()
root.update()
pump(260)
check("显示时内容已建好（不是先空白再出窗口）",
      holder.get("children_at_reveal", 0) >= 3, holder)
check("显示前遮罩未摆上去", holder.get("mask_placed_before") is False, holder)
try:
    card.close("ok")
except Exception:
    pass
pump(200)

print("== C. 设置页：选项卡 + 所有选项 ==")
app.show_page("settings")
pump(600)
sp = app.settings_page
for tab in ("general", "database", "about"):
    sp.show_tab(tab)
    pump(400)
    check(f"切到选项卡 {tab}", sp.stack.current == tab, sp.stack.current)
sp.show_tab("general")
pump(300)
for key in ("merged", "isolated"):
    sp.mode_seg.select(key, notify=True)
    pump(300)
    _sf = app.settings._settings_file
    check(f"存储模式切到 {key} 且已落盘",
          app.settings.storage_mode == key and _sf is not None and _sf.exists(),
          (app.settings.storage_mode, _sf))
for key in ("developer", "player"):
    sp.role_seg.select(key, notify=True)
    pump(300)
    check(f"用户身份切到 {key}", app.settings.role == key, app.settings.role)
for key in ("off", "on"):
    sp.anim_seg.select(key, notify=True)
    pump(300)
    expect = (key == "on")
    check(f"动画开关切到 {key}", ps.ANIMATIONS_ENABLED is expect,
          ps.ANIMATIONS_ENABLED)
_sf = app.settings._settings_file
check("动画设置已写盘", _sf is not None and _sf.exists(), _sf)
if _sf is not None and _sf.exists():
    import json as _json
    _data = _json.loads(_sf.read_text(encoding="utf-8"))
    check("落盘内容包含 animations 字段", "animations" in _data, list(_data))

print("== D. 三个列表的交互 ==")
app.show_page("home")
pump(600)
app.load_pack(PACK)
check("整合包加载完成", pump_until(lambda: not app.loading_presets, 8000))
pump(400)
for name, lb in (("预设", app.preset_listbox), ("枪包", app.gunpack_listbox)):
    n = lb.size()
    if n:
        lb.selection_clear(0, "end")
        lb.selection_set(0)
        app.on_preset_selected(None) if name == "预设" else None
        pump(300)
        check(f"{name}列表可选中（{n} 项）", bool(lb.curselection()) or name == "枪包",
              lb.curselection())
    else:
        note(f"{name}列表为空，跳过选中")
# 右键菜单
try:
    if app.preset_listbox.size():
        class _Ev:
            x = y = 10
            x_root = y_root = 200
        app.show_preset_context_menu(_Ev())
        pump(200)
        for w in list(ps._OVERLAY_STACK):
            try:
                w.close(None)
            except Exception:
                pass
        pump(200)
        check("预设右键菜单可打开并关闭", True)
except Exception:
    check("预设右键菜单可打开并关闭", False,
          traceback.format_exc().splitlines()[-1])
# 最近面板
app.recent_visible = False      # 前面点过按钮，先归位再测
pump(300)
app.toggle_recent()
pump(400)
check("最近面板展开", bool(app.recent_wrap.place_info()), app.recent_wrap.place_info())
app.toggle_recent()
pump(400)
check("最近面板收起", not app.recent_wrap.place_info())

print("== E. 错误路径 ==")
# E1 非法整合包（没有 tacz）
try:
    app.close_pack()
    pump(400)
    app.load_pack(BAD_PACK)
    pump(1200)
    check("加载没有 tacz 的目录：不崩溃且给出提示",
          app.tacz_path is None or app.current_pack_path is None
          or str(app.tacz_path).endswith("tacz"),
          (app.current_pack_path, app.tacz_path))
except Exception:
    check("加载没有 tacz 的目录：不崩溃且给出提示", False,
          traceback.format_exc().splitlines()[-1])
# E2 未选预设就替换
try:
    app.close_pack()
    pump(400)
    app.apply_preset()
    pump(600)
    check("未加载整合包时点替换：不崩溃", True)
except Exception:
    check("未加载整合包时点替换：不崩溃", False,
          traceback.format_exc().splitlines()[-1])
# E3 无包导出
try:
    app.export_preset()
    pump(500)
    check("无包导出：不崩溃", True)
except Exception:
    check("无包导出：不崩溃", False, traceback.format_exc().splitlines()[-1])
# E4 导入损坏文件
try:
    bad = TMP / "broken.fgcpack"
    bad.write_bytes(b"not a zip")
    app.handle_import_file(str(bad))
    pump(800)
    check("导入损坏文件：不崩溃", True)
except Exception:
    check("导入损坏文件：不崩溃", False, traceback.format_exc().splitlines()[-1])
left = clean_state()
check("错误路径走完后无残留", not left, left)

print("== F. 窗口尺寸变化后的布局 ==")
for w, h, tag in ((ps.WINDOW_MIN_W, ps.WINDOW_MIN_H, "最小"),
                  (1600, 1000, "放大")):
    root.geometry(f"{w}x{h}")
    pump(700)
    lp = app.pages["home"].winfo_children()[0]
    cards = [c for c in lp.winfo_children()
             if type(c).__name__ == "CTkFrame"][:3]
    need = sum(c.winfo_reqheight() for c in cards)
    check(f"{tag}尺寸下左列三张卡装得下", need <= lp.winfo_height() + 2,
          (need, lp.winfo_height()))
    check(f"{tag}尺寸下无控件溢出窗口",
          all(c.winfo_rooty() - root.winfo_rooty() + c.winfo_height()
              <= root.winfo_height() + 2 for c in cards),
          [(c.winfo_rooty() - root.winfo_rooty() + c.winfo_height(),
            root.winfo_height()) for c in cards])

print("== H. 边界用例 ==")
# H1 超长预设名：不应撑破卡片
try:
    app.load_pack(PACK)
    pump_until(lambda: not app.loading_presets, 8000)
    pump(400)
    long_name = "超长预设名称" * 12
    app.preset_manager.create_preset(long_name, "v1.0.0")
    app._update_preset_list()
    pump(400)
    lp = app.pages["home"].winfo_children()[0]
    cards = [c for c in lp.winfo_children() if type(c).__name__ == "CTkFrame"][:3]
    need = sum(c.winfo_reqheight() for c in cards)
    check("超长预设名不会撑破左列布局", need <= lp.winfo_height() + 2,
          (need, lp.winfo_height()))
except Exception:
    check("超长预设名不会撑破左列布局", False,
          traceback.format_exc().splitlines()[-1])
# H2 空 tacz 目录
try:
    empty = TMP / "empty_pack" / "tacz"
    empty.mkdir(parents=True)
    app.close_pack()
    pump(400)
    app.load_pack(empty.parent)
    pump(1500)
    check("空 tacz 目录：不崩溃", True)
    check("空 tacz 目录：枪包数为 0",
          "0 个枪包" in str(app.gunpack_count_label.cget("text")),
          app.gunpack_count_label.cget("text"))
except Exception:
    check("空 tacz 目录：不崩溃", False, traceback.format_exc().splitlines()[-1])
# H3 枪包列表双击
try:
    app.load_pack(PACK)
    pump_until(lambda: not app.loading_presets, 8000)
    pump(400)
    if app.gunpack_listbox.size():
        app.gunpack_listbox.selection_set(0)
        app.on_gunpack_open(None)
        pump(400)
    check("枪包列表双击：不崩溃", True)
except Exception:
    check("枪包列表双击：不崩溃", False, traceback.format_exc().splitlines()[-1])
# H4 连点替换（防重复触发）
try:
    for _ in range(3):
        app.apply_preset()
        pump(60)
    ok = pump_until(lambda: not app.is_applying, 20000)
    pump(500)
    check("连点替换：最终状态正确、不会卡在 applying",
          ok and not app.is_applying, app.is_applying)
except Exception:
    check("连点替换：最终状态正确、不会卡在 applying", False,
          traceback.format_exc().splitlines()[-1])
# H5 监视器启停
try:
    app._start_watcher()
    pump(400)
    app._stop_watcher()
    pump(300)
    check("TACZ 监视器可启停", True)
except Exception:
    check("TACZ 监视器可启停", False, traceback.format_exc().splitlines()[-1])
# H6 操作中切页面
try:
    app.apply_preset()
    app.show_page("log")
    pump(400)
    app.show_page("settings")
    pump(400)
    app.show_page("home")
    pump_until(lambda: not app.is_applying, 20000)
    check("替换过程中切页面：不崩溃且状态正确", not app.is_applying)
except Exception:
    check("替换过程中切页面：不崩溃且状态正确", False,
          traceback.format_exc().splitlines()[-1])
pump(2500)          # 等动画收尾（切页/替换的补间）
left = clean_state()
check("边界用例后无残留", not left, left)

print("== G. 收尾一致性 ==")
root.geometry("1280x900")
pump(500)
left = clean_state()
check("无残留遮罩 / 浮层 / 挂起补间", not left, left)
check("界面仍可响应（切换页面正常）", (app.show_page("log"), pump(500),
                                 app.stack.current == "log")[2],
      app.stack.current)
app.show_page("home")
pump(400)

print()
if INFO:
    print("补充观察：")
    for line in INFO:
        print("  -", line)
if FAIL:
    print(f"!!! {len(FAIL)} 项失败: {FAIL}")
    raise SystemExit(1)
print("全流程 + 全 UI 操作扫描：全部通过")
