"""列表滚动回归：多列表互不抢绑定、卡片/Listbox 滚动跟手、无事件累积。

    python packaging/scroll_check.py

覆盖：
  · 两个 ScrollArea 交替滚动，后一个不会把前一个的全局滚轮绑定解掉
  · CTkScrollableFrame 在 ScrollArea 之后仍能滚动
  · tk.Listbox 原生滚动生效
  · 60 张卡片连续滚轮能走到列表底部（不再被 150ms 补间反复取消）
"""
from __future__ import annotations

import sys
import time
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import customtkinter as ctk  # noqa: E402

from pulses.widget.cards import CardList, ScrollArea  # noqa: E402
from pulses.widget.factory import make_list_scroll  # noqa: E402

FAILS: list[str] = []


def check(label: str, condition: bool, detail="") -> None:
    print(("  ok   " if condition else "  FAIL ") + label
          + ("" if condition else f"  {detail}"))
    if not condition:
        FAILS.append(label)


def pump(root, ms=60) -> None:
    end = time.time() + ms / 1000.0
    while time.time() < end:
        try:
            root.update()
        except Exception:
            break


def main() -> int:
    root = ctk.CTk()
    root.geometry("1000x700")

    print("== 1. 两个 ScrollArea 交替滚 ==")
    left = ScrollArea(root)
    left.pack(side="left", fill="both", expand=True)
    right = ScrollArea(root)
    right.pack(side="right", fill="both", expand=True)
    for area in (left, right):
        for index in range(80):
            ctk.CTkLabel(area.inner, text=f"Item {index}", height=36).pack(fill="x")
    root.update()
    left.scroll_to_top()
    right.scroll_to_top()
    root.update()
    left.inner.winfo_children()[0].event_generate("<MouseWheel>", delta=-120)
    root.update()
    check("左列表滚轮生效", left.canvas.yview()[0] > 0.0, left.canvas.yview())
    right.inner.winfo_children()[0].event_generate("<MouseWheel>", delta=-120)
    root.update()
    check("右列表滚轮生效", right.canvas.yview()[0] > 0.0, right.canvas.yview())
    left.inner.winfo_children()[0].event_generate("<MouseWheel>", delta=-120)
    root.update()
    check("切回左列表仍能滚", left.canvas.yview()[0] > 0.08, left.canvas.yview())

    print("== 2. CTkScrollableFrame 不被解绑 ==")
    frame = ctk.CTkScrollableFrame(root, width=280)
    frame.pack(side="right", fill="both", expand=True)
    for index in range(80):
        ctk.CTkLabel(frame, text=f"Row {index}", height=36).pack(fill="x")
    root.update()
    frame._parent_canvas.yview_moveto(0.0)
    frame.winfo_children()[0].event_generate("<MouseWheel>", delta=-120)
    root.update()
    check("CTkScrollableFrame 滚轮生效",
          frame._parent_canvas.yview()[0] > 0.0,
          frame._parent_canvas.yview())

    print("== 3. Listbox 原生滚动 ==")
    listbox_root = tk.Toplevel(root)
    listbox_root.geometry("420x360")
    listbox = tk.Listbox(listbox_root, height=12)
    listbox.pack(fill="both", expand=True)
    for index in range(120):
        listbox.insert("end", f"枪包 {index:03d}.zip")
    make_list_scroll(root, listbox)
    listbox.yview_moveto(0.0)
    root.update()
    before_last = listbox.yview()[1]
    listbox.event_generate("<MouseWheel>", delta=-120)
    root.update()
    check("Listbox 滚轮生效", listbox.yview()[1] > before_last, listbox.yview())
    listbox_root.destroy()

    print("== 4. 60 张卡片连续滚动 ==")
    # 把前面的测试控件清掉，给卡片列表完整高度
    for widget in (left, right, frame, listbox):
        try:
            widget.destroy()
        except Exception:
            pass
    root.update()
    cards = CardList(root)
    cards.pack(fill="both", expand=True)
    items = [{"name": f"预设 {i:03d}", "meta": "v1.0 · 2 个枪包 · 100 MB",
              "status": "未绑定来源"} for i in range(60)]
    cards.set_items(items, animate_new=False)
    root.update()
    check("卡片创建完成", cards.count() == 60, cards.count())
    cards.area.scroll_to_top()
    root.update()
    started = time.perf_counter()
    for _ in range(24):
        cards.area.scroll_by(-1)
        root.update()
    elapsed = time.perf_counter() - started
    check("连续滚动到底部", cards.area.canvas.yview()[1] >= 0.99,
          cards.area.canvas.yview())
    check("滚动耗时 < 2s", elapsed < 2.0, f"{elapsed:.2f}s")

    try:
        root.destroy()
    except Exception:
        pass
    print("\n" + ("全部通过" if not FAILS else f"失败 {len(FAILS)} 项"))
    for item in FAILS:
        print("  -", item)
    return 0 if not FAILS else 1


if __name__ == "__main__":
    raise SystemExit(main())
