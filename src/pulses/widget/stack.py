"""Canvas 内的页面栈（滑动/位图切换）。"""
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
from ..utils import *
from ..animation import *
from ..animation import _TWEENS

class SlideStack:
    """把若干页面放进一个 Canvas，用缓动曲线做「推入 / 推出」切换。

    Canvas 会裁剪内嵌窗口，所以页面在滑动过程中不会溢到侧边栏上 ——
    这也是这里不直接用 place() 搬页面的原因（Tk 普通容器不裁剪子控件）。
    """

    def __init__(self, parent, bg_color=C_WINDOW_BG, duration_ms=260,
                 easing=ease_out_cubic):
        self.canvas = Canvas(parent, bg=bg_color, highlightthickness=0, bd=0)
        self.canvas.pack(fill=BOTH, expand=True)
        self.bg_color = bg_color
        self.duration_ms = duration_ms
        self.easing = easing
        self.frames = {}
        self.items = {}
        self.order = []
        self.current = None
        self._size = (1, 1)
        # 页面快照：切换动画期间只搬位图，不搬控件树
        # （搬控件树时 Tk 会把移出可视区的窗口项 unmap/remap，
        #   Windows 上 remap 那一下控件会闪成白的 —— 用户反馈的「插帧」）
        self._shots = {}
        self._slide_imgs = None
        self.canvas.bind("<Configure>", self._on_configure)

    def add(self, key, frame):
        try:
            frame.configure(fg_color=self.bg_color)
        except Exception:
            pass
        item = self.canvas.create_window(
            0, 0, window=frame, anchor="nw",
            width=self._size[0], height=self._size[1])
        self.canvas.itemconfigure(item, state="hidden")
        self.frames[key] = frame
        self.items[key] = item
        if key not in self.order:
            self.order.append(key)
        return item

    def _on_configure(self, event):
        self._size = (max(1, event.width), max(1, event.height))
        for item in self.items.values():
            try:
                self.canvas.itemconfigure(item, width=self._size[0],
                                          height=self._size[1])
            except Exception:
                pass
        if (id(self.canvas), "slide") in _TWEENS:
            # 切换动画进行中被重排：轨迹已失效，直接落到终点
            cancel_tween(self.canvas, "slide")
            self._settle()
        if self.current in self.items:
            self.canvas.coords(self.items[self.current], 0, 0)

    def _settle(self):
        """把所有页面归位：当前页贴左可见，其余隐藏。"""
        for key, item in self.items.items():
            try:
                self.canvas.coords(item, 0, 0)
                self.canvas.itemconfigure(
                    item, state="normal" if key == self.current else "hidden")
            except Exception:
                pass

    def show(self, key, animate=True, direction=1, axis="x"):
        """direction: +1 = 新页从右/下方滑进来；-1 反之。
        axis: 侧边栏是竖排 → 竖着滑；设置页选项卡是横排 → 横着滑。

        真·滑动（不是幕布、也不是淡入淡出）：新页从进入侧滑到正位，
        旧页原地不动、滑完再隐藏。只搬一棵控件树，帧开销是「两页对开」
        的一半，也不会在中间露出空白带。
        """
        if key not in self.items:
            return
        # 上一次切换还没跑完就被打断：先让它落位，否则状态和画面会不一致
        if (id(self.canvas), "slide") in _TWEENS:
            cancel_tween(self.canvas, "slide")
            self._settle()
        span = float(self._size[0] if axis == "x" else self._size[1])
        previous = self.current
        if key == previous:
            self._activate(key)      # 兜一次，保证画面和 current 一致
            return
        self.current = key
        if previous is None or not animate or not config.ANIMATIONS_ENABLED:
            self._activate(key)
            return

        new_item = self.items[key]
        old_item = self.items.get(previous)
        start = -span if direction >= 0 else span      # 新页起点
        # 有快照就只搬位图（控件树一动不动，不会出现 remap 闪白）
        old_shot = self._shots.get(previous)
        new_shot = self._shots.get(key)
        if old_shot is not None and new_shot is not None:
            self._slide_images(key, start, old_shot, new_shot, axis, span)
            return
        try:
            # 旧页留在原地当背景（它整页不透明，天然铺满视口，不会露底色），
            # 只搬新页 —— 每帧只搬一棵控件树，开销是对开推入的一半。
            if old_item is not None:
                if axis == "x":
                    self.canvas.coords(old_item, 0, 0)
                else:
                    self.canvas.coords(old_item, 0, 0)
                self.canvas.itemconfigure(old_item, state="normal")
            if axis == "x":
                self.canvas.coords(new_item, start, 0)
            else:
                self.canvas.coords(new_item, 0, start)
            self.canvas.itemconfigure(new_item, state="normal")
        except Exception:
            self._activate(key)
            return

        def frame(e, raw):
            pos = lerp(start, 0.0, e)
            try:
                if axis == "x":
                    self.canvas.coords(new_item, pos, 0)
                else:
                    self.canvas.coords(new_item, 0, pos)
            except Exception:
                pass

        def done():
            # 收尾：新页贴正位、旧页隐藏（_activate 里统一处理）
            self._activate(key)

        frame(0.0, 0.0)
        tween(self.canvas, "slide", self.duration_ms, frame, done,
              easing=self.easing, fps=FPS_MOVE)

    def prewarm(self):
        """把每一页都 map 一次再藏回去。

        Canvas 窗口项第一次被 map 时，Tk 要跑一遍整棵控件树的布局
        （实测设置页 78 个控件约 41ms，主页 137 个更久，Windows 还要翻倍），
        这一下正好卡在切换动画的第一帧 —— 表现就是「点了没反应，
        过一会儿才切页」。提前付掉这笔钱，之后切换就只剩搬位置。
        """
        try:
            for item in self.items.values():
                self.canvas.itemconfigure(item, state="normal")
            self.canvas.update_idletasks()
            for name, item in self.items.items():
                if name != self.current:
                    self.canvas.itemconfigure(item, state="hidden")
            self.canvas.update_idletasks()
        except Exception:
            pass

    def _capture(self, key):
        """不再截图。

        原来用 ImageGrab 抓整页位图做滑动素材：抓一次 30~80ms，
        Windows 上还会闪一下（抓到的是屏幕内容，窗口一动就花）——
        这就是"切页面拉丝、卡顿"的来源。现在直接用页面 frame 平移，
        不产生位图，切换是纯窗口移动，稳定且没有撕裂。
        """
        return None

    def _capture_disabled(self, key):
        try:
            from PIL import ImageGrab, ImageTk
        except Exception:
            return None
        try:
            w, h = int(self._size[0]), int(self._size[1])
            if w < 16 or h < 16:
                return None
            cv = self.canvas
            x, y = cv.winfo_rootx(), cv.winfo_rooty()
            img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    def _schedule_capture(self, key):
        """截图已停用（见 _capture），这里直接返回。"""
        return

        def _do():
            if key != self.current:
                return
            shot = self._capture(key)
            if shot is not None:
                self._shots[key] = shot
        try:
            self.canvas.after(180, _do)
        except Exception:
            pass

    def _slide_images(self, key, start, old_shot, new_shot, axis, span):
        """只搬两张位图的切换动画：控件树全程不动，任何平台都不会闪白。"""
        cv = self.canvas
        park = self._park_position()
        for item in self.items.values():
            try:
                cv.coords(item, park, 0)
                cv.itemconfigure(item, state="normal")
            except Exception:
                pass
        try:
            if axis == "x":
                old_img = cv.create_image(0, 0, anchor="nw", image=old_shot)
                new_img = cv.create_image(start, 0, anchor="nw", image=new_shot)
            else:
                old_img = cv.create_image(0, 0, anchor="nw", image=old_shot)
                new_img = cv.create_image(0, start, anchor="nw", image=new_shot)
        except Exception:
            self._activate(key)
            return
        self._slide_imgs = (old_img, new_img)

        def frame(e, raw):
            pos = lerp(start, 0.0, e)
            try:
                if axis == "x":
                    cv.coords(new_img, pos, 0)
                else:
                    cv.coords(new_img, 0, pos)
            except Exception:
                pass

        def done():
            for it in (old_img, new_img):
                try:
                    cv.delete(it)
                except Exception:
                    pass
            self._slide_imgs = None
            self._activate(key)

        frame(0.0, 0.0)
        tween(cv, "slide", self.duration_ms, frame, done,
              easing=self.easing, fps=FPS_MOVE)

    def _park_position(self):
        """停靠点：视口右侧外一屏。"""
        span = float(self._size[0] if self._size[0] > 1 else 1)
        return span

    def _activate(self, key):
        """当前页摆正位，其余**停到视口外**（不是隐藏）。

        为什么不能隐藏：Canvas 窗口项在 state="hidden" 期间不会被 Tk 调整
        尺寸，再显示时还带着旧尺寸（实测设置页/日志页停在 384x483 的 CTk
        默认尺寸），滑进来时四周会露出下面那页的内容 —— 就是用户反馈的
        「撕裂」。一直保持 map、只挪到视口外，尺寸就始终跟画布一致。
        """
        if key not in self.items:
            return
        self.current = key
        park = self._park_position()
        for name, item in self.items.items():
            try:
                if name == key:
                    self.canvas.coords(item, 0, 0)
                else:
                    self.canvas.coords(item, park, 0)
                self.canvas.itemconfigure(item, state="normal")
            except Exception:
                pass
        # 页面落定后补拍快照，供下一次切换当素材
        self._schedule_capture(key)
