"""PyWebView 启动入口。"""
from __future__ import annotations

import ctypes
import os
import sys
import threading
import time
import traceback
from pathlib import Path

import webview
from webview.dom import DOMEventHandler

from .api import Api
from .controller import AppController
from .events import EventBus, EventPump, JobRunner

ROOT = Path(__file__).resolve().parents[2]
WEB_DIST = Path(__file__).resolve().parent / "web" / "dist"
WEB_DEV = os.environ.get("PULSES_WEB_DEV", "").strip()


def _startup_log(message: str) -> None:
    """WebView 版没有控制台；启动阶段尽量留下可读日志。"""
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n"
    for path in (Path.cwd() / "PulsesSwap_database" / "webview-startup.log",
                 Path.home() / "PulsesSwap-webview-startup.log"):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line)
            return
        except Exception:
            continue


def _fatal(message: str, detail: str = "") -> None:
    _startup_log(f"FATAL: {message}\n{detail}")
    if sys.platform.startswith("win"):
        try:
            ctypes.windll.user32.MessageBoxW(
                None, f"{message}\n\n{detail}", "Pulses Swap", 0x10)
            return
        except Exception:
            pass
    print(f"Pulses Swap: {message}\n{detail}", file=sys.stderr)


def _web_url():
    if WEB_DEV:
        return WEB_DEV
    index = WEB_DIST / "index.html"
    if not index.exists():
        # 开发时给一个明确错误，别让 WebView 显示空白
        raise SystemExit(
            f"前端产物不存在：{index}。请先在 web/ 目录运行 npm run build。")
    return str(index)


def _bind_drop(window, api: Api):
    def on_drop(event):
        files = event.get("dataTransfer", {}).get("files", []) or []
        paths = []
        for item in files:
            path = item.get("pywebviewFullPath") if isinstance(item, dict) else None
            if path:
                paths.append(path)
        # 即使没有拿到 pywebviewFullPath，也要走 handle_drop 发 dnd.error，
        # 否则覆盖层会永久留在界面上且用户得不到任何提示。
        api.handle_drop(paths)

    def on_drag(event):
        return

    try:
        window.dom.document.events.drop += DOMEventHandler(
            on_drop, prevent_default=True, stop_propagation=True)
        # dragenter/dragover 不阻断冒泡：React 还要用它们显示覆盖层。
        # drop 必须阻断冒泡，由 Python 拿 pywebviewFullPath 后统一处理。
        window.dom.document.events.dragenter += DOMEventHandler(
            on_drag, prevent_default=True)
        window.dom.document.events.dragover += DOMEventHandler(
            on_drag, prevent_default=True)
    except Exception:
        # 某些后端没有 DOM 支持；明确通知前端，避免遮罩闪一下却无动作。
        try:
            window.evaluate_js(
                "window.PS && (window.PS.dndUnavailable = true);")
        except Exception:
            pass


def main():
    _startup_log("main() begin")
    bus = EventBus()
    try:
        controller = AppController(bus=bus)
        jobs = JobRunner(bus, logger=controller.add_log)
        api = Api(controller, bus, jobs)
    except Exception:
        _fatal("核心模块初始化失败。", traceback.format_exc())
        return

    window = None
    try:
        # 不再使用 hidden=True：先让窗口出现，前端没加载完时显示纯色底，
        # 也比“进程在后台、用户看不到窗口”可靠。on_loaded 里仍会再 show 一次兜底。
        window = webview.create_window(
            "Pulses Swap",
            _web_url(),
            js_api=api,
            width=1280,
            height=900,
            min_size=(1140, 812),
            background_color="#F2F3F5",
            hidden=False,
            text_select=True,
            confirm_close=False,
        )
    except Exception:
        _fatal("创建窗口失败。请确认已安装 Microsoft Edge WebView2 Runtime。",
               traceback.format_exc())
        return
    api.bind_window(window)
    pump_holder = {}
    loaded_once = {"done": False}

    def on_loaded():
        # loaded 可能在重载/某些后端上重复触发；重复启动 EventPump 会
        # 多出几条线程一起 evaluate_js，表现为后台持续占用 CPU。
        if loaded_once["done"]:
            return
        loaded_once["done"] = True
        _startup_log("webview loaded")
        # 先 show，再做 DOM 绑定/事件泵：后面任何一步慢或异常都不能把窗口留在后台。
        try:
            window.show()
        except Exception:
            _startup_log("window.show() failed:\n" + traceback.format_exc())
        try:
            _bind_drop(window, api)
        except Exception:
            _startup_log("bind drop failed:\n" + traceback.format_exc())
        try:
            pump = EventPump(bus, window, logger=controller.add_log).start()
            pump_holder["pump"] = pump
        except Exception:
            _startup_log("event pump failed:\n" + traceback.format_exc())

    window.events.loaded += on_loaded

    def after_start():
        # webview.start 的 func 在 GUI 循环启动后执行；再兜一次显示。
        _startup_log("webview started")
        try:
            window.show()
        except Exception:
            _startup_log("after_start show failed:\n" + traceback.format_exc())

    try:
        webview.start(debug=bool(os.environ.get("PULSES_WEBVIEW_DEBUG")),
                      http_server=True, private_mode=True,
                      func=after_start)
    except Exception:
        _fatal("窗口启动失败。请确认已安装 Microsoft Edge WebView2 Runtime。",
               traceback.format_exc())
    finally:
        pump = pump_holder.get("pump")
        if pump:
            pump.stop()
        try:
            controller._stop_watcher()
        except Exception:
            pass
        _startup_log("main() end")


if __name__ == "__main__":
    main()
