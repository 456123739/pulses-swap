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
from .easing import _TWEENS

def cancel_tween(widget, key):
    job = _TWEENS.pop((id(widget), key), None)
    if job is not None:
        try:
            widget.after_cancel(job)
        except Exception:
            pass


def cancel_all_tweens(widget):
    for token in [k for k in _TWEENS if k[0] == id(widget)]:
        cancel_tween(widget, token[1])


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
          easing=ease_out_cubic, fps=60):
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
    interval = max(1, int(round(1000.0 / max(1, fps))))
    duration_ms = max(1, int(duration_ms))
    max_frames = int(duration_ms / interval) + 3
    token = (id(widget), key)
    start = time.perf_counter()
    state = {"frames": 0, "last": None}

    def step():
        if token not in _TWEENS:
            return
        state["frames"] += 1
        now = time.perf_counter()
        if state.get("last") is not None:
            _note_frame_time((now - state["last"]) * 1000.0)
        state["last"] = now
        elapsed = (now - start) * 1000.0
        raw = clamp01(elapsed / duration_ms)
        if state["frames"] >= max_frames:
            raw = 1.0
        try:
            on_frame(easing(raw), raw)
        except Exception:
            pass
        if raw >= 1.0:
            _TWEENS.pop(token, None)
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
    try:
        job = widget.after(interval, step)
    except Exception:
        _TWEENS.pop(token, None)
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

    try:
        widget.bind("<Enter>", _on_enter, add="+")
        widget.bind("<Leave>", _on_leave, add="+")
    except Exception:
        pass
    return widget
