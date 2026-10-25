"""补间调度与帧率统计。"""
from __future__ import annotations

import ctypes
try:                      # ctypes.wintypes 在非 Windows 上会抛 ValueError
    import ctypes.wintypes
except Exception:
    ctypes.wintypes = None
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import zipfile
from datetime import datetime
from pathlib import Path
from tkinter import *
from tkinter import filedialog

import customtkinter as ctk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False
    TkinterDnD = None
    DND_FILES = None

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False
    Observer = None
    FileSystemEventHandler = object

from .. import config
from ..config import *
from .easing import *
from .easing import _TWEENS, _TWEEN_OWNERS

def cancel_tween(widget, key):
    token = (id(widget), key)
    job = _TWEENS.pop(token, None)
    _TWEEN_OWNERS.pop(token, None)
    if job is not None:
        try:
            widget.after_cancel(job)
        except Exception:
            pass


def cancel_all_tweens(widget):
    for token in [k for k in _TWEENS if k[0] == id(widget)]:
        cancel_tween(widget, token[1])


def _install_destroy_guard(widget):
    """控件被销毁时把它的补间一起清掉。

    否则 _TWEENS 里会留下一个指向已销毁控件的 token：Tk 已经取消了 after
    任务，那条补间永远不会再推进，也就永远不会被移除（长跑必漏）。

    普通控件用闭包捕获的 widget 清理（CustomTkinter 的 bind() 可能绑在
    内部 Canvas 上，事件里的 widget 不一定是宿主控件）；根窗口 / Toplevel
    的 <Destroy> 还会收到所有子控件的销毁事件，因此额外用 event.widget
    过滤，只认宿主自己的销毁。
    """
    if getattr(widget, "_tween_destroy_guard", False):
        return
    token_prefix = id(widget)

    def _cleanup(_event=None):
        # 根窗口/Toplevel 的 <Destroy> 绑定会收到所有子控件的销毁事件
        # （bindtags 里包含 toplevel）。只认宿主自己的销毁，否则界面里
        # 任何一个卡片被回收都会把窗口级补间一起取消。
        try:
            if widget.winfo_toplevel() is widget:
                if _event is not None and getattr(_event, "widget", None) is not widget:
                    return
        except Exception:
            pass
        for token in [k for k in _TWEENS if k[0] == token_prefix]:
            job = _TWEENS.pop(token, None)
            _TWEEN_OWNERS.pop(token, None)
            if job not in (None, -1):
                try:
                    widget.after_cancel(job)
                except Exception:
                    pass

    try:
        widget.bind("<Destroy>", _cleanup, add="+")
        widget._tween_destroy_guard = True
    except Exception:
        pass


_FPS_LOG = {"interval": None, "total_ms": 0.0, "frames": 0}


def _note_frame_time(interval_ms: float) -> None:
    """累计补间帧间隔，切换结束后由调用方读出来记日志。"""
    _FPS_LOG["interval"] = interval_ms
    _FPS_LOG["total_ms"] += interval_ms
    _FPS_LOG["frames"] += 1


def take_frame_stats() -> tuple:
    """取走累计的帧统计 → (平均帧间隔ms, 帧数)，并清零。"""
    frames = _FPS_LOG["frames"]
    total = _FPS_LOG["total_ms"]
    _FPS_LOG["frames"] = 0
    _FPS_LOG["total_ms"] = 0.0
    if frames <= 0 or total <= 0:
        return (0.0, 0)
    return (total / frames, frames)


def apply_animations_setting(enabled: bool) -> None:
    """把「动画」设置应用到全局开关（设置页切换时也走这里）。"""
    config.ANIMATIONS_ENABLED = bool(enabled)


def tween(widget, key, duration_ms, on_frame, on_done=None,
          easing=ease_out_cubic, fps=60, start_on_first_frame=False):
    """
    用 widget.after 驱动一条补间时间线。

    on_frame(缓动值, 线性进度) 每帧调用；进度按真实耗时计算，掉帧不会变慢。
    另有帧数上限兜底：即使事件循环被压缩（例如同步 after 的测试环境），
    动画也一定会在有限帧内收敛到终点，不会自锁。
    """
    cancel_tween(widget, key)
    if not config.ANIMATIONS_ENABLED:
        # 动画关闭：一帧到位，逻辑与开启时完全一致
        try:
            on_frame(1.0, 1.0)
        except Exception:
            pass
        if on_done is not None:
            try:
                on_done()
            except Exception:
                pass
        return
    _install_destroy_guard(widget)
    interval = max(1, int(round(1000.0 / max(1, fps))))
    duration_ms = max(1, int(duration_ms))
    max_frames = int(duration_ms / interval) + 3
    token = (id(widget), key)
    state = {"frames": 0, "last": None,
             "start": None if start_on_first_frame else time.perf_counter()}

    def step():
        if token not in _TWEENS:
            return
        state["frames"] += 1
        now = time.perf_counter()
        if state.get("start") is None:
            # 首帧可能被一次很重的布局阻塞几百毫秒；从首帧开始计时，
            # 动画就不会“还没显示就已经播完”。窗口级动画需要这个语义。
            state["start"] = now
        if state.get("last") is not None:
            _note_frame_time((now - state["last"]) * 1000.0)
        state["last"] = now
        elapsed = (now - state["start"]) * 1000.0
        raw = clamp01(elapsed / duration_ms)
        if state["frames"] >= max_frames:
            raw = 1.0
        try:
            on_frame(easing(raw), raw)
        except Exception:
            pass
        if raw >= 1.0:
            _TWEENS.pop(token, None)
            _TWEEN_OWNERS.pop(token, None)
            if on_done is not None:
                try:
                    on_done()
                except Exception:
                    pass
            return
        try:
            _TWEENS[token] = widget.after(interval, step)
        except Exception:
            _TWEENS.pop(token, None)

    # 先占位再排期：万一宿主把 after 做成同步回调，step 里的守卫也能认出自己
    _TWEENS[token] = -1
    _TWEEN_OWNERS[token] = widget
    try:
        job = widget.after(interval, step)
    except Exception:
        _TWEENS.pop(token, None)
        _TWEEN_OWNERS.pop(token, None)
        return
    if token in _TWEENS:
        _TWEENS[token] = job


def attach_hover_glow(widget, base_color=None, hover_color=None, duration_ms=130):
    """卡片/拖入框的 hover 描边过渡：进入混向强调色，离开混回原色。

    卡片里通常还嵌着按钮/标签，鼠标从卡片移到子控件上时 Tk 会给卡片发
    <Leave>，直接响应会来回闪。这里把「离开」延后 90ms，期间若有 <Enter>
    就撤销，等效于「指针真的移出卡片」才收光。
    """
    try:
        base_color = base_color or widget.cget("border_color")
    except Exception:
        base_color = C_BORDER_SOFT
    if hex_to_rgb(base_color) is None:
        base_color = C_BORDER_SOFT
    hover_color = hover_color or C_ACCENT_SOFT
    state = {"color": base_color, "leave_job": None}

    def _to(target, ms=duration_ms):
        start = state["color"]
        if start == target:
            return

        def frame(e, raw):
            state["color"] = lerp_color(start, target, e)
            try:
                widget.configure(border_color=state["color"])
            except Exception:
                pass

        frame(0.0, 0.0)
        tween(widget, "glow", ms, frame, easing=ease_in_out_cubic,
              fps=FPS_COLOR)

    def _cancel_leave():
        if state["leave_job"] is not None:
            try:
                widget.after_cancel(state["leave_job"])
            except Exception:
                pass
            state["leave_job"] = None

    def _on_enter(_event=None):
        _cancel_leave()
        _to(hover_color)

    def _on_leave(_event=None):
        _cancel_leave()

        def fire():
            state["leave_job"] = None
            _to(base_color)

        try:
            state["leave_job"] = widget.after(90, fire)
        except Exception:
            fire()

    # CTk 的 bind() 只绑内部 Canvas，指针落在子标签/子按钮上时收不到。
    # 把实际接收事件的内部控件和现有子控件都绑上，悬停到文字上不会断。
    targets, stack = [], [widget]
    while stack:
        node = stack.pop()
        for target in (node, getattr(node, "_canvas", None),
                       getattr(node, "_label", None),
                       getattr(node, "_text_label", None)):
            if target is not None and target not in targets:
                targets.append(target)
        try:
            stack.extend(node.winfo_children())
        except Exception:
            pass
    for target in targets:
        try:
            target.bind("<Enter>", _on_enter, add="+")
            target.bind("<Leave>", _on_leave, add="+")
        except Exception:
            pass
    return widget
