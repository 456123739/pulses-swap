"""Windows 实机拖拽验收：Explorer 文件项 -> WebView2 窗口。

要求 Windows + pywinauto；CI 中运行，不使用网页内模拟事件。
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SWP_SHOWWINDOW = 0x40
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
user32 = ctypes.windll.user32


def drag(start, end, steps=36):
    user32.SetCursorPos(int(start[0]), int(start[1]))
    time.sleep(0.25)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.25)
    for i in range(1, steps + 1):
        t = i / steps
        x = start[0] + (end[0] - start[0]) * t
        y = start[1] + (end[1] - start[1]) * t
        user32.SetCursorPos(int(x), int(y))
        time.sleep(0.025)
    time.sleep(0.2)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()
    source = Path(args.source).resolve()
    report = Path(args.report).resolve()
    try:
        report.unlink()
    except OSError:
        pass
    env = dict(os.environ)
    env["PULSES_WEB_CI"] = "1"
    env["PULSES_WEB_DROP_REPORT"] = str(report)
    print('DRAG: launching app', flush=True)
    app = subprocess.Popen([args.app], env=env)
    try:
        time.sleep(3.0)
        # 打开父目录并选中 drag-pack
        subprocess.Popen(["explorer.exe", f"/select,{source}"], env=env)
        time.sleep(2.5)
        print('DRAG: locating explorer', flush=True)
        from pywinauto import Desktop
        desktop = Desktop(backend="uia")
        dlg = None
        for _ in range(20):
            for w in desktop.windows(title_re=".*drag-source.*"):
                try:
                    if w.is_visible():
                        dlg = w
                        break
                except Exception:
                    pass
            if dlg is not None:
                break
            time.sleep(0.5)
        if dlg is None:
            raise RuntimeError("找不到 Explorer 窗口")
        dlg.set_focus()
        hwnd = dlg.handle
        user32.SetWindowPos(hwnd, 0, 0, 0, 330, 720, SWP_SHOWWINDOW)
        time.sleep(0.8)
        item = None
        for _ in range(10):
            try:
                for child in dlg.descendants():
                    try:
                        if (child.window_text() == source.name
                                and child.element_info.control_type in
                                ("ListItem", "DataItem", "TreeItem")):
                            item = child
                            break
                    except Exception:
                        continue
            except Exception:
                item = None
            if item is not None:
                break
            time.sleep(0.4)
        if item is None:
            raise RuntimeError(f"Explorer 里找不到文件项 {source.name}")
        rect = item.rectangle()
        for _ in range(12):
            if (rect.right - rect.left) > 2 and (rect.bottom - rect.top) > 2:
                break
            time.sleep(0.5)
            try:
                item.scroll_into_view()
                dlg.set_focus()
            except Exception:
                pass
            rect = item.rectangle()
        print('DRAG: item rect', rect, flush=True)
        if (rect.right - rect.left) <= 2 or (rect.bottom - rect.top) <= 2:
            # Explorer 偶发还没画完；文件在列表第一行，使用稳定的行坐标兜底
            start = (220, 180)
        else:
            # 文件项在 Details 视图里横跨所有列，取文件名左侧，避免用到窗口外坐标
            start = (rect.left + 24, (rect.top + rect.bottom) // 2)
        # 目标在 Explorer 右侧、WebView2 窗口内
        print('DRAG: dragging', start, '->', (700,340), flush=True)
        drag(start, (700, 340))
        deadline = time.time() + 30
        data = None
        while time.time() < deadline:
            if report.exists():
                try:
                    data = json.loads(report.read_text(encoding="utf-8"))
                    break
                except Exception:
                    pass
            time.sleep(0.4)
        if not data:
            raise RuntimeError("拖入后没有生成报告")
        print(json.dumps(data, ensure_ascii=False))
        if not data.get("ok"):
            raise RuntimeError(f"拖入未加载整合包: {data}")
    finally:
        try:
            app.terminate()
            app.wait(timeout=8)
        except Exception:
            try:
                app.kill()
            except Exception:
                pass


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"DRAG_TEST_FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
