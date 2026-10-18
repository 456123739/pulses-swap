"""
UI 结构快照：把整个控件树导成 JSON，用于"改动前后 UI 完全一致"的比对。

只记录稳定特征：层级路径、类名、文案、坐标尺寸、关键颜色与字体。
不记录内存地址等每次都会变的东西。
"""
import json
import sys
import time
from pathlib import Path

SRC = "/home/admin/111/pulses-swap/src"
sys.path.insert(0, SRC)

import pulses_swap as ps  # noqa: E402

ps.DatabaseLocatorDialog.show = lambda self: None
for _mod in (ps.dialogs, ps.utils, ps.app, ps.pages, ps.managers):
    for _name in ("show_info", "show_warning", "show_error", "ask_yes_no",
                  "ask_ok_cancel", "show_message"):
        if hasattr(_mod, _name):
            setattr(_mod, _name, lambda *a, **k: None)

OPTION_KEYS = ("fg_color", "bg_color", "text_color", "border_color",
               "border_width", "corner_radius", "font", "state", "text")


def opt(widget, key):
    try:
        val = widget.cget(key)
    except Exception:
        return None
    if isinstance(val, (int, float, str, bool)) or val is None:
        return str(val)
    return str(val)[:60]


def dump(widget, path="root", out=None, depth=0):
    if out is None:
        out = []
    if depth > 12:
        return out
    try:
        cls = widget.winfo_class()
    except Exception:
        cls = "?"
    rec = {
        "path": path,
        "class": cls,
        "type": type(widget).__name__,
        "xy": [widget.winfo_x(), widget.winfo_y()],
        "wh": [widget.winfo_width(), widget.winfo_height()],
        "opts": {k: opt(widget, k) for k in OPTION_KEYS
                 if opt(widget, k) is not None},
    }
    out.append(rec)
    try:
        children = widget.winfo_children()
    except Exception:
        children = []
    for i, child in enumerate(children):
        dump(child, f"{path}/{i}", out, depth + 1)
    return out


def main():
    root = ps.ctk.CTk()
    ps.apply_font_fallbacks()
    ps.sync_ui_scale(root)
    root.geometry("1280x900")
    root.update()
    app = ps.PulsesSwapApp(root)
    t0 = time.time()
    while (time.time() - t0) * 1000 < 2500:
        root.update()
        time.sleep(0.004)

    snaps = {}
    for page in ("home", "settings", "log"):
        app.show_page(page)
        t0 = time.time()
        while (time.time() - t0) * 1000 < 900:
            root.update()
            time.sleep(0.004)
        snaps[page] = dump(root)

    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/ui_snapshot.json")
    out.write_text(json.dumps(snaps, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"已写入 {out}（{sum(len(v) for v in snaps.values())} 个控件）")
    root.destroy()


if __name__ == "__main__":
    main()
