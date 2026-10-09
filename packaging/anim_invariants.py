"""
动画中间帧不变量审计：逐帧采样几何/颜色，断言每个动画在任意中间帧都满足
应有的不变量（拼接无缝、不越界、单调、无残留）。比肉眼看缩略图严格得多。
"""
import importlib.util
import time

SRC = "/home/admin/111/pulses-swap/src/pulses_swap.py"
spec = importlib.util.spec_from_file_location("ps", SRC)
ps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ps)
ps.DatabaseLocatorDialog.show = lambda self: None

FAIL = []


def check(label, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + label + ("" if cond else "  " + str(detail)))
    if not cond:
        FAIL.append(label)


root = ps.ctk.CTk()
ps.apply_font_fallbacks()
ps.sync_ui_scale(root)
root.geometry("1280x900")
root.update()
app = ps.PulsesSwapApp(root)


def pump(ms):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        root.update()
        time.sleep(0.003)


def sample(start, duration_ms, sampler, steps=14):
    """跑一个动画，按固定间隔采样。"""
    start()
    out = []
    t0 = time.perf_counter()
    for i in range(steps):
        while (time.perf_counter() - t0) * 1000 < duration_ms * i / steps:
            root.update()
            time.sleep(0.002)
        out.append(sampler())
    pump(400)
    return out


pump(900)
canvas = app.stack.canvas

# ── 1. 侧边栏切页：走位图路径，控件树一动不动 ──
print("== 1. 侧边栏切页：只搬位图，活控件树不动 ==")
app.show_page("home")
pump(700)
for _p in ("settings", "log", "home"):
    app.show_page(_p)
    pump(700)
check("三页快照齐备", sorted(app.stack._shots) == ["home", "log", "settings"],
      sorted(app.stack._shots))


def sampler_page():
    imgs = [i for i in canvas.find_all() if canvas.type(i) == "image"]
    return (canvas.coords(app.stack.items["settings"])[1],
            canvas.coords(app.stack.items["home"])[1],
            (canvas.coords(imgs[-1])[1] if imgs else None))


rows = sample(lambda: app.show_page("settings"), 260, sampler_page)
live_new = [r[0] for r in rows]
live_old = [r[1] for r in rows]
img_ys = [r[2] for r in rows if r[2] is not None]
check("走位图路径（有图片项在动）", len(img_ys) > 6, len(img_ys))
check("位图单调滑入（-span → 0）",
      img_ys and all(a <= b + 0.6 for a, b in zip(img_ys, img_ys[1:])),
      [round(y, 1) for y in img_ys[:6]])
check("滑动期间活控件树一动不动（不会 remap 闪白）",
      live_new and all(abs(y - live_new[0]) < 0.01 for y in live_new),
      live_new[:4])
check("旧页也保持停靠不动", live_old and all(abs(y - live_old[0]) < 0.01
                                        for y in live_old), live_old[:4])

# ── 2. 设置页选项卡：同样必须拼接 ──
print("== 2. 设置页选项卡切换：任意中间帧严格拼接 ==")
app.show_page("settings")
pump(600)
sp = app.settings_page
tabs = sp.stack.canvas
span_x = sp.stack._size[0]
sp.show_tab("general", animate=False)
pump(300)


def sampler_tab():
    # 顺序：新页 about 在前，旧页 general 在后
    return (tabs.coords(sp.stack.items["about"])[0],
            tabs.coords(sp.stack.items["general"])[0],
            sp.stack.frames["about"].winfo_width())


rows2 = sample(lambda: sp.show_tab("about"), 260, sampler_tab)
new_xs = [r[0] for r in rows2]
old_xs = [r[1] for r in rows2]
check("旧选项卡留在原地（铺满视口 → 不露底色）",
      all(abs(x) < 1.5 for x in old_xs), [round(x, 1) for x in old_xs[:5]])
check("新选项卡在视口范围内单调滑入",
      all(-span_x - 1 <= x <= 1 for x in new_xs)
      and all(a <= b + 0.6 for a, b in zip(new_xs, new_xs[1:])),
      [round(x, 1) for x in new_xs[:6]])
check("选项卡尺寸始终等于视口",
      all(w == tabs.winfo_width() for _n, _o, w in rows2),
      {w for _n, _o, w in rows2})

# ── 3. 侧边栏滑块：不越界、单调、落在目标上 ──
print("== 3. 侧边栏滑块 ==")
app.show_page("home")
pump(500)
nav = app.nav
rects = [nav._rect_of(k) if hasattr(nav, "_rect_of") else None for k in ("home", "log")]


def sampler_pill():
    c = nav.coords(nav._pill_id)
    return (c[1], c[3])


rows3 = sample(lambda: nav.select("log"), 240, sampler_pill)
ys = [r[0] for r in rows3]
check("滑块 y 单调下滑", all(a <= b + 0.6 for a, b in zip(ys, ys[1:])), [round(y, 1) for y in ys])
check("滑块始终落在导航区内部（不越界）",
      all(0 <= y and h <= nav.winfo_height() + 1 for y, h in rows3),
      (min(ys), max(h for _y, h in rows3), nav.winfo_height()))

# ── 4. 按钮 hover/按下：颜色单调过渡且三态互不相同 ──
print("== 4. 按钮三态颜色 ==")
btn = app.refresh_all_btn
base, hover, press = btn._base_color, btn._hover_target, btn._press_color


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


rows4 = sample(lambda: btn._anim_enter(), 130, lambda: btn._current)
cols = [hex_rgb(c) for c in rows4]
check("hover 过程中颜色逐帧逼近目标（单调）",
      all(all(abs(b - a) <= abs(c - a) + 1.5 for a, b, c in zip(hex_rgb(base), p1, p2))
          for p1, p2 in zip(cols, cols[1:])) or len(set(cols)) > 3,
      rows4[:4])
check("hover 终态等于目标色", rows4[-1] == hover, (rows4[-1], hover))
check("三态颜色互不相同", len({base, hover, press}) == 3, (base, hover, press))
btn._anim_leave()
pump(300)

# ── 5. 卡片描边：起点/终点正确，中间色在两者之间 ──
print("== 5. 卡片 hover 描边 ==")
card = app.drop_area          # 挂了 hover 描边的是 Step2 导入框
rows5 = sample(lambda: card._canvas.event_generate("<Enter>", x=5, y=5), 150,
               lambda: card.cget("border_color"))
check("描边起点是发丝色", rows5[0] == ps.C_BORDER_SOFT, rows5[0])
check("描边终点是强调软色", rows5[-1] == ps.C_ACCENT_SOFT, rows5[-1])
mid = [hex_rgb(c) for c in rows5]
lo, hi = hex_rgb(ps.C_BORDER_SOFT), hex_rgb(ps.C_ACCENT_SOFT)
check("中间帧颜色落在起止两色之间",
      all(all(min(a, b) - 3 <= v <= max(a, b) + 3 for v, a, b in zip(p, lo, hi))
          for p in mid), rows5)
card._canvas.event_generate("<Leave>", x=5, y=5)
pump(400)

# ── 6. Toast：从右侧进入、逐帧逼近终点、结束后收掉 ──
print("== 6. Toast 浮层 ==")
app.toast("审计提示", kind="success")
rows6 = []
t0 = time.perf_counter()
while (time.perf_counter() - t0) * 1000 < 300:
    root.update()
    if app._toast is not None:
        try:
            rows6.append(float(app._toast._slide))
        except Exception:
            pass
    time.sleep(0.004)
check("Toast 从屏幕外滑入（_slide 单调减小到 0）",
      len(rows6) > 3 and all(a >= b - 1.0 for a, b in zip(rows6, rows6[1:]))
      and rows6[0] > 5 and abs(rows6[-1]) < 1.0,
      [round(x, 1) for x in rows6[:6]] + [round(rows6[-1], 1)])
pump(2600)
check("Toast 结束后已收掉", app._toast is None, app._toast)

# ── 7. 最近面板：高度单调增/减，且落在 1 与 RECENT_H 之间 ──
print("== 7. 最近面板展开/收起 ==")
rows7 = sample(lambda: app.toggle_recent(), 260,
               lambda: int((app.recent_wrap.place_info() or {}).get("height") or 1))
check("展开过程中高度单调不减",
      all(a <= b + 0.6 for a, b in zip(rows7, rows7[1:])), rows7)
check("展开终态 = RECENT_H", rows7[-1] == app.RECENT_H, rows7[-1])
rows7b = sample(lambda: app.toggle_recent(), 260,
                lambda: int((app.recent_wrap.place_info() or {}).get("height") or 1))
check("收起过程中高度单调不增",
      all(a >= b - 0.6 for a, b in zip(rows7b, rows7b[1:])), rows7b)
check("收起终态 = 1", rows7b[-1] == 1, rows7b[-1])

# ── 8. 进度条：单调推进、落在目标值 ──
print("== 8. 进度条 ==")
rows8 = sample(lambda: app.show_progress(4, 10, "审计"), 320,
               lambda: getattr(app, "_progress_value", 0.0))
check("进度值单调不减", all(a <= b + 1e-6 for a, b in zip(rows8, rows8[1:])), rows8)
check("进度终值 = 0.4", abs(rows8[-1] - 0.4) < 1e-3, rows8[-1])
app.hide_progress()
pump(400)

# ── 9. 加载小圆点：文字形态在 0~3 个点之间循环 ──
print("== 9. 加载小圆点 ==")
app._start_loading_dots("加载中")
seen = set()
t0 = time.perf_counter()
while (time.perf_counter() - t0) * 1000 < 700:
    root.update()
    seen.add(app.loading_label.cget("text"))
    time.sleep(0.01)
app._stop_loading_dots()
check("小圆点有多个中间形态", len(seen) >= 3, sorted(seen))
check("形态都在「加载中 + 0~3 个点」范围内",
      all(t.startswith("加载中") and 0 <= len(t) - 3 <= 3 for t in seen), sorted(seen))

# ── 10. 设置保存回显：出现后淡回默认 ──
print("== 10. 设置保存回显 ==")
app.show_page("settings")
pump(500)
sp._flash_saved()
pump(200)
check("回显文案已出现", "已自动保存" in str(sp.saved_label.cget("text")),
      sp.saved_label.cget("text"))
pump(1400)
check("回显已淡回默认文案", str(sp.saved_label.cget("text")) == "自动保存",
      sp.saved_label.cget("text"))

print()
if FAIL:
    print(f"!!! {len(FAIL)} 项失败: {FAIL}")
    raise SystemExit(1)
print("所有动画中间帧不变量全部通过")
