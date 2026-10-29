"""PyWebView 启动入口。"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

import webview
from webview.dom import DOMEventHandler

from .api import Api
from .controller import AppController
from .events import EventBus, EventPump, JobRunner

ROOT = Path(__file__).resolve().parents[2]
WEB_DIST = Path(__file__).resolve().parent / "web" / "dist"
WEB_DEV = os.environ.get("PULSES_WEB_DEV", "").strip()


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
        if paths:
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
    bus = EventBus()
    controller = AppController(bus=bus)
    jobs = JobRunner(bus, logger=controller.add_log)
    api = Api(controller, bus, jobs)
    window = webview.create_window(
        "Pulses Swap",
        _web_url(),
        js_api=api,
        width=1280,
        height=900,
        min_size=(1140, 812),
        background_color="#F2F3F5",
        hidden=True,
        text_select=True,
        confirm_close=False,
    )
    api.bind_window(window)
    pump_holder = {}

    def on_loaded():
        _bind_drop(window, api)
        pump = EventPump(bus, window, logger=controller.add_log).start()
        pump_holder["pump"] = pump
        try:
            window.show()
        except Exception:
            pass

    window.events.loaded += on_loaded
    try:
        webview.start(debug=bool(os.environ.get("PULSES_WEBVIEW_DEBUG")),
                      http_server=True, private_mode=True)
    finally:
        pump = pump_holder.get("pump")
        if pump:
            pump.stop()
        controller._stop_watcher()


if __name__ == "__main__":
    main()
