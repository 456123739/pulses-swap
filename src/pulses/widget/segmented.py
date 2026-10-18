"""自绘分段控件（滑块动画）。"""
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

class CanvasSegmented(Canvas):
    """自绘分段控件（侧边栏导航 / 设置页选项卡共用）。

    选中态是一块圆角药丸，切换只更新位置与配色，不做过渡动画
    （需求：去掉图标与动画，界面保持静态、瞬时切换）。
    Canvas 会把子项裁剪在自身范围内，重排不会溢到隔壁区域。

    items: [(key, text), ...]
    """

    def __init__(self, parent, items, command=None, orientation="vertical",
                 item_height=H_NAV, pad=4, gap=4, radius=R_CONTROL,
                 bg_color=C_CARD_BG, pill_color=C_ACCENT_SOFT,
                 hover_color=C_ACCENT_SOFT, text_color=C_TEXT_MAIN,
                 active_text_color=C_ACCENT, font_size=FS_BODY,
                 bold_active=False, text_anchor="w", text_pad=14,
                 duration_ms=240, hover_ms=110, width=1, height=None):
        # 自绘控件是原始像素：按 config.UI_SCALE 放大，否则系统 125%/150% 下会和
        # CTk 控件错位（CTk 自己会缩放，Canvas 不会）
        item_height = px(item_height)
        pad, gap, radius = px(pad), px(gap), px(radius)
        text_pad = px(text_pad)
        font_size = max(1, int(round(font_size * config.UI_SCALE)))
        if height is None:
            # 不传高度就按内容算一个自然高度。
            # 原来默认 1：调用方只 pack(fill=X) 时画布就真的只有 1px 高，
            # 药丸/文字全被裁掉，看起来像「这个弹窗没有选项卡」。
            if orientation == "vertical":
                height = (2 * pad + len(items) * item_height
                          + max(0, len(items) - 1) * gap)
            else:
                height = 2 * pad + item_height
        else:
            height = px(height) if height > 1 else height
        super().__init__(parent, bg=bg_color, highlightthickness=0, bd=0,
                         width=px(width) if width > 1 else width,
                         height=height)
        self._items = [(key, str(text)) for key, text in items]
        self._keys = [key for key, _ in self._items]
        self._command = command
        self._orientation = orientation
        self._item_height = item_height
        self._pad = pad
        self._gap = gap
        self._radius = radius
        self._bg = bg_color
        self._pill_color = pill_color
        self._hover_color = hover_color
        self._text_color = text_color
        self._active_text_color = active_text_color
        # 字体族要在构造时取（apply_font_fallbacks 会就地改写全局名）
        # 用 tk_font()：这是 tk.Canvas 的文字，正数字号会被 Tk 当成「磅」
        # 再乘一次 tk scaling（100% 下 1.33 倍、150% 下 2 倍），字会明显偏大
        self._font = tk_font(config.FONT_FAMILY, font_size)
        self._font_active = tk_font(config.FONT_FAMILY, font_size,
                                    "bold" if bold_active else "normal")
        self._text_anchor = text_anchor
        self._text_pad = text_pad
        self._duration_ms = duration_ms
        self._hover_ms = hover_ms

        self._active = None
        self._rects = []
        self._text_ids = []
        self._text_colors = {}
        self._pill_id = None
        self._pill_rect = None
        self._pill_alpha = 0.0
        self._hover_id = None
        self._hover_rect = None
        self._hover_alpha = 0.0
        self._hover_index = -1
        self._size = (0, 0)
        self._laid_out = False

        # 层级：悬停层 -> 滑块 -> 文字
        self._hover_id = self.create_polygon(
            *self._rect_points((-6, -6, -3, -3)), smooth=True, splinesteps=24,
            fill=bg_color, outline="")
        self._pill_id = self.create_polygon(
            *self._rect_points((-6, -6, -3, -3)), smooth=True, splinesteps=24,
            fill=bg_color, outline="")
        for index, (_, text) in enumerate(self._items):
            self._text_ids.append(
                self.create_text(0, 0, text=text, fill=text_color,
                                  anchor=text_anchor, font=self._font))
            self._text_colors[index] = text_color
        self.bind("<Configure>", self._on_configure)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    # ---------- 几何 ----------
    def _rect_points(self, rect):
        x1, y1, x2, y2 = rect
        radius = max(0.0, min(float(self._radius), (x2 - x1) / 2.0,
                              (y2 - y1) / 2.0))
        return [x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
                x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
                x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1]

    def _on_configure(self, event):
        size = (max(1, event.width), max(1, event.height))
        if size == self._size:
            return
        self._size = size
        self._layout(*size)

    def _layout(self, width, height):
        count = max(1, len(self._items))
        rects = []
        if self._orientation == "vertical":
            x1, x2 = self._pad, width - self._pad
            for index in range(count):
                y1 = self._pad + index * (self._item_height + self._gap)
                rects.append((x1, y1, x2, y1 + self._item_height))
        else:
            inner = width - 2 * self._pad - (count - 1) * self._gap
            item_w = inner / float(count)
            # 容器被压得比内边距还小的时候，别算出反过来的矩形
            y1, y2 = self._pad, max(self._pad + 4, height - self._pad)
            x = self._pad
            for _ in range(count):
                rects.append((x, y1, x + item_w, y2))
                x += item_w + self._gap
        self._rects = rects
        for index, text_id in enumerate(self._text_ids):
            x1, y1, x2, y2 = rects[index]
            center_y = (y1 + y2) / 2.0
            if self._text_anchor == "w":
                self.coords(text_id, x1 + self._text_pad, center_y)
            else:
                self.coords(text_id, (x1 + x2) / 2.0, center_y)
        if self._active in self._keys:
            target = rects[self._keys.index(self._active)]
            resizing = self._pill_rect is not None
            self._pill_rect = target
            self.coords(self._pill_id, *self._rect_points(target))
            if resizing:
                # 窗口尺寸变化会打乱滑块的动画轨迹：取消补间并直接落到目标项
                cancel_tween(self, "pill")
                self._pill_alpha = 1.0
                self.itemconfigure(self._pill_id, fill=self._pill_color)
            elif not self._laid_out:
                # 首次拿到真实尺寸：补一次带淡入的选中，滑块不会「啪」地出现
                self._laid_out = True
                self.select(self._active, animate=True)
            else:
                self._pill_alpha = 1.0
                self.itemconfigure(self._pill_id, fill=self._pill_color)
        if 0 <= self._hover_index < len(rects):
            self._hover_rect = rects[self._hover_index]
            self.coords(self._hover_id, *self._rect_points(self._hover_rect))

    def _index_at(self, x, y):
        for index, (x1, y1, x2, y2) in enumerate(self._rects):
            if x1 <= x <= x2 and y1 <= y <= y2:
                return index
        return -1

    # ---------- 交互 ----------
    def _on_motion(self, event):
        self._set_hover(self._index_at(event.x, event.y))

    def _on_leave(self, _event=None):
        self._set_hover(-1)

    def _on_click(self, event):
        index = self._index_at(event.x, event.y)
        if index < 0:
            return
        self.select(self._keys[index], notify=True)

    def _set_hover(self, index, animate=True):
        if index == self._hover_index:
            return
        self._hover_index = index
        active_index = (self._keys.index(self._active)
                        if self._active in self._keys else -1)
        target_alpha = 1.0 if (0 <= index < len(self._rects)
                               and index != active_index) else 0.0
        if 0 <= index < len(self._rects):
            self._hover_rect = self._rects[index]
            try:
                self.coords(self._hover_id,
                            *self._rect_points(self._hover_rect))
            except Exception:
                pass
        start_alpha = self._hover_alpha

        def paint(alpha):
            self._hover_alpha = alpha
            try:
                self.itemconfigure(
                    self._hover_id,
                    fill=lerp_color(self._bg, self._hover_color, alpha))
            except Exception:
                pass

        if not animate or self._hover_ms <= 0:
            paint(target_alpha)
            return

        def frame(e, raw):
            paint(lerp(start_alpha, target_alpha, e))

        tween(self, "hover", self._hover_ms, frame, easing=ease_out_cubic,
              fps=FPS_COLOR)

    # ---------- 选中 ----------
    def current(self):
        """当前选中项的 key（未选中返回 None）。"""
        return self._active

    def index_of(self, key):
        return self._keys.index(key) if key in self._keys else -1

    def select(self, key, animate=True, notify=False):
        if key not in self._keys:
            return
        index = self._keys.index(key)
        previous = self._active
        self._active = key
        self._animate_texts(previous, index, animate)
        self._move_pill(index, animate)
        if self._hover_index == index:
            self._set_hover(-1, animate=animate)
        if notify and callable(self._command):
            try:
                self._command(key)
            except Exception:
                pass

    def _move_pill(self, index, animate=True):
        if not self._rects:
            return
        target = self._rects[index]
        if not animate:
            self._pill_rect = target
            self._pill_alpha = 1.0
            self.coords(self._pill_id, *self._rect_points(target))
            self.itemconfigure(self._pill_id, fill=self._pill_color)
            return
        start = self._pill_rect or target
        start_alpha = self._pill_alpha

        def frame(e, raw):
            self._pill_rect = tuple(lerp(a, b, e)
                                    for a, b in zip(start, target))
            self._pill_alpha = lerp(start_alpha, 1.0, e)
            self.coords(self._pill_id, *self._rect_points(self._pill_rect))
            self.itemconfigure(
                self._pill_id,
                fill=lerp_color(self._bg, self._pill_color, self._pill_alpha))

        def done():
            self._pill_rect = target
            self._pill_alpha = 1.0
            self.coords(self._pill_id, *self._rect_points(target))
            self.itemconfigure(self._pill_id, fill=self._pill_color)

        frame(0.0, 0.0)      # 立即落到起点，滑块不等待第一帧
        tween(self, "pill", self._duration_ms, frame, done,
              easing=ease_out_pill, fps=FPS_MOVE)

    def _animate_texts(self, previous_key, active_index, animate=True):
        for index, text_id in enumerate(self._text_ids):
            is_active = (index == active_index)
            target = self._active_text_color if is_active else self._text_color
            start = self._text_colors.get(index, self._text_color)
            try:
                self.itemconfigure(text_id,
                                   font=self._font_active if is_active
                                   else self._font)
            except Exception:
                pass
            if not animate or start == target:
                self._text_colors[index] = target
                try:
                    self.itemconfigure(text_id, fill=target)
                except Exception:
                    pass
                continue

            def frame(e, raw, i=index, s=start, t=target, item=text_id):
                color = lerp_color(s, t, e)
                self._text_colors[i] = color
                try:
                    self.itemconfigure(item, fill=color)
                except Exception:
                    pass

            frame(0.0, 0.0)
            tween(self, "text{}".format(index), 160, frame,
                  easing=ease_out_cubic, fps=FPS_COLOR)
