"""「最近」下拉浮层的开合自检。

    python packaging/recent_check.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

TMP = Path(tempfile.mkdtemp(prefix="ps_recent_"))
PACK = TMP / "modpack"
TACZ = PACK / "tacz"
TACZ.mkdir(parents=True)
with zipfile.ZipFile(TACZ / "gun_a.zip", "w") as z:
    z.writestr("pack.mcmeta", "{}")

FAIL = []


def check(label, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + label
          + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


def pump(root, ms=400):
    end = time.time() + ms / 1000
    while time.time() < end:
        try:
            root.update()
        except Exception:
            break
        time.sleep(0.01)


import pulses_swap as ps  # noqa: E402

for _mod in (ps.dialogs, ps.utils, ps.app, ps.pages, ps.managers):
    for _name in ("show_info", "show_warning", "show_error", "ask_yes_no",
                  "ask_ok_cancel", "show_message"):
        if hasattr(_mod, _name):
            setattr(_mod, _name, lambda *a, **k: None)
    if hasattr(_mod, "DatabaseLocatorDialog"):
        _mod.DatabaseLocatorDialog.show = lambda self: None
ps.PulsesSwapApp._init_database_flow = lambda self: None

root = ps.ctk.CTk()
_scale = float(os.environ.get("PS_SCALE") or "1")
if _scale != 1.0:
    ps.ctk.set_widget_scaling(_scale)
    ps.ctk.set_window_scaling(_scale)
root.geometry("1280x900")
root.update()
app = ps.PulsesSwapApp(root)
pump(root, 300)


class _Recent:
    """测试里没有真数据库，给「最近」一个固定条目。"""

    def get_all(self):
        return [{"name": "modpack", "path": str(PACK)}]

    def add(self, *a, **k):
        pass


app.recent_manager = _Recent()
app.load_pack(PACK)
pump(root, 1200)

row = app.pack_btn_row
btn = app.recent_toggle_btn
wrap = app.recent_wrap
lb = app.recent_listbox

# 展开
app.toggle_recent()
pump(root, 300)

check("展开后浮层可见", wrap.winfo_ismapped() == 1,
      f"mapped={wrap.winfo_ismapped()}")
check("展开后高度到位", wrap.winfo_height() >= app.RECENT_H - 4,
      f"h={wrap.winfo_height()}")
check("浮层在按钮行下方（不遮按钮）",
      wrap.winfo_rooty() >= row.winfo_rooty() + row.winfo_height(),
      f"wrap_y={wrap.winfo_rooty()} row_bottom="
      f"{row.winfo_rooty() + row.winfo_height()}")
cx = btn.winfo_rootx() + btn.winfo_width() // 2
cy = btn.winfo_rooty() + btn.winfo_height() // 2
hit = root.winfo_containing(cx, cy)
top = hit
while top is not None and top is not btn:
    top = getattr(top, "master", None)
check("「最近」按钮没有被浮层盖住（还能点到）", top is btn,
      f"命中 {hit}")
_gap = wrap.winfo_rooty() - (row.winfo_rooty() + row.winfo_height())
check("浮层紧贴按钮行下方（不跑偏）", 0 <= _gap <= 14, f"gap={_gap}")
check("列表有最近项", lb.size() >= 1, f"行数={lb.size()}")

# 再点一次收起
app.toggle_recent()
pump(root, 300)
check("再点一次收起", app.recent_visible is False)
check("收起后浮层完全撤下", wrap.winfo_ismapped() == 0,
      f"mapped={wrap.winfo_ismapped()}")

# 点外面收起
app.toggle_recent()
pump(root, 300)


class _Evt:
    widget = app.pack_drop_label


app._recent_click_outside(_Evt())
pump(root, 100)
check("点别处收起", app.recent_visible is False)

# 点面板内部不收起
app.toggle_recent()
pump(root, 200)


class _Evt2:
    widget = lb


app._recent_click_outside(_Evt2())
pump(root, 100)
check("点面板内部不收起", app.recent_visible is True)

# 双击最近项：加载并收起
if lb.size():
    lb.selection_set(0)
    app.on_recent_double_click(None)
    pump(root, 600)
    check("选中最近项后收起", app.recent_visible is False)

# 反复开合不漏事件
for _ in range(3):
    app.toggle_recent()
    pump(root, 120)
    app.toggle_recent()
    pump(root, 120)
check("反复开合后处于收起状态", app.recent_visible is False
      and wrap.winfo_ismapped() == 0)

# 切页面 / 换整合包也要收起
app.toggle_recent()
pump(root, 200)
app.show_page("settings")
pump(root, 700)
check("切页面后收起", app.recent_visible is False
      and wrap.winfo_ismapped() == 0)
app.show_page("home")
pump(root, 500)
app.toggle_recent()
pump(root, 200)
app.db_ready = True          # 这个用例要真正走 load_pack
app.load_pack(PACK)
pump(root, 900)
check("换整合包后收起", app.recent_visible is False
      and wrap.winfo_ismapped() == 0,
      f"visible={app.recent_visible} mapped={wrap.winfo_ismapped()}")

print()
print("FAIL" if FAIL else "全部通过")
root.destroy()
sys.exit(1 if FAIL else 0)
