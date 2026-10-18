"""
自绘控件与控件工厂
（由单文件按分区拆分而来，逻辑未改动）
"""
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

from . import config
from .config import *
from .utils import *
from . import config
from .animation import *
from .animation import _TWEENS



# ==================== 动画控件 ====================
class AnimatedButton(ctk.CTkButton):
    """带曲线过渡的按钮：hover / 按下都是逐帧混色，而不是瞬间跳色。

    CTk 自带的 hover 是「瞬时换色」，这里把它的 hover 目标设成底色把它架空，
    再由本类用补间驱动 fg_color。CTk 内部处理器与本类处理器在同一次事件
    分发里先后执行，本类每次都从当前插值色继续，因此不会看到跳变。
    """

    def __init__(self, master, base_color, hover_target, press_color=None,
                 **kwargs):
        kwargs["fg_color"] = base_color
        # hover_color 交给 CTk 用「目标色」：CTk 自己也会在进出/点击动画里
        # 瞬时刷一次颜色，如果这里填底色，就会把我逐帧混出来的中间色顶掉
        # （表现是 hover 一下又弹回原色）。填目标色两边一致，不会打架。
        kwargs["hover_color"] = hover_target
        super().__init__(master, **kwargs)
        self._base_color = base_color
        self._hover_target = hover_target
        self._press_color = press_color or hover_target
        self._current = base_color
        self._hovering = False
        try:
            self.bind("<Enter>", self._anim_enter, add="+")
            self.bind("<Leave>", self._anim_leave, add="+")
            self.bind("<ButtonPress-1>", self._anim_press, add="+")
            self.bind("<ButtonRelease-1>", self._anim_release, add="+")
        except Exception:
            pass

    def _enabled(self):
        try:
            return str(self.cget("state")) == "normal"
        except Exception:
            return True

    def _reassert(self):
        try:
            self.configure(fg_color=self._current)
        except Exception:
            pass

    def _to(self, target, duration=110):
        if target == self._current:
            return
        start = self._current

        def frame(e, raw):
            self._current = lerp_color(start, target, e)
            try:
                self.configure(fg_color=self._current)
            except Exception:
                pass

        frame(0.0, 0.0)
        tween(self, "bg", duration, frame, easing=ease_out_cubic,
              fps=FPS_COLOR)

    # 注意：处理函数一律用 _anim_* 命名，绝不能叫 _on_enter/_on_leave/
    # _on_release —— CTkButton 在 __init__ 里 bind("<ButtonRelease-1>",
    # self._on_release)，那是它执行 command 的地方；一旦被同名覆盖，
    # 按钮就变成「点下去什么都不执行」。
    def _anim_enter(self, _event=None):
        self._hovering = True
        self._reassert()
        if self._enabled():
            self._to(self._hover_target)

    def _anim_leave(self, _event=None):
        self._hovering = False
        self._reassert()
        self._to(self._base_color)

    def _anim_press(self, _event=None):
        self._reassert()
        if self._enabled():
            self._to(self._press_color, 70)

    def _anim_release(self, _event=None):
        self._reassert()
        if not self._enabled():
            return
        self._to(self._hover_target if self._hovering else self._base_color, 120)


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
                 duration_ms=240, hover_ms=110, width=1, height=1):
        # 自绘控件是原始像素：按 config.UI_SCALE 放大，否则系统 125%/150% 下会和
        # CTk 控件错位（CTk 自己会缩放，Canvas 不会）
        item_height = px(item_height)
        pad, gap, radius = px(pad), px(gap), px(radius)
        text_pad = px(text_pad)
        font_size = max(1, int(round(font_size * config.UI_SCALE)))
        super().__init__(parent, bg=bg_color, highlightthickness=0, bd=0,
                         width=px(width) if width > 1 else width,
                         height=px(height) if height > 1 else height)
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
        self._font = (config.FONT_FAMILY, font_size)
        self._font_active = (config.FONT_FAMILY, font_size,
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
            y1, y2 = self._pad, height - self._pad
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
              easing=ease_out_cubic, fps=FPS_MOVE)

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
        """给正在显示的页面拍一张位图，供切换动画当素材。失败返回 None。"""
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
        """页面稳定后补拍快照（延后一点，等布局与绘制落定）。"""
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


class Toast:
    """右上角浮出提示：曲线滑入 + 自动淡出，全程不阻塞操作。"""

    def __init__(self, host, text, kind="success", duration_ms=1700):
        self.host = host
        self.color = {"success": C_SUCCESS, "info": C_ACCENT,
                      "warning": C_WARNING, "error": C_ERROR}.get(kind, C_ACCENT)
        self.frame = ctk.CTkFrame(host.overlay_host, fg_color=C_PANEL_BG,
                                   corner_radius=R_CONTROL,
                                   border_width=BORDER_W,
                                   border_color=self.color)
        self.label = ctk.CTkLabel(self.frame, text=text, text_color=self.color,
                                   font=(config.FONT_FAMILY, FS_SMALL),
                                   fg_color="transparent")
        self.label.pack(padx=PAD_CARD_X, pady=PAD_TIGHT)
        # _slide > 0 表示浮层右边缘越出容器右边缘（= 在屏幕外），
        # 入场从 +28 滑到 0，出场再滑回去 —— 之前符号写反了，
        # 变成「从里往外滑」，看着像往右弹一下。
        self._slide = 28.0
        self._hold_ms = duration_ms
        self._place()
        self._play_in()

    def _place(self):
        try:
            self.frame.place(relx=1.0, rely=0.0, anchor="ne",
                              x=-PAD_WINDOW + self._slide, y=PAD_WINDOW)
        except Exception:
            pass

    def _play_in(self):
        def frame(e, raw):
            self._slide = lerp(28.0, 0.0, e)
            self._place()

        def done():
            try:
                self.host.root.after(self._hold_ms, self._play_out)
            except Exception:
                pass

        frame(0.0, 0.0)
        tween(self.frame, "toast_in", 200, frame, done, easing=ease_out_back)

    def _play_out(self):
        def frame(e, raw):
            self._slide = lerp(0.0, 28.0, e)
            self._place()
            try:
                self.frame.configure(
                    fg_color=lerp_color(C_PANEL_BG, C_WINDOW_BG, e),
                    border_color=lerp_color(self.color, C_WINDOW_BG, e))
                self.label.configure(
                    text_color=lerp_color(self.color, C_WINDOW_BG, e))
            except Exception:
                pass

        tween(self.frame, "toast_out", 190, frame, self.close,
              easing=ease_in_out_cubic)

    def close(self):
        cancel_all_tweens(self.frame)
        # 清掉宿主持有的引用，否则 app._toast 会一直指向已销毁的浮层
        try:
            if getattr(self.host, "_toast", None) is self:
                self.host._toast = None
        except Exception:
            pass
        try:
            self.frame.destroy()
        except Exception:
            pass


# ==================== 控件工厂 ====================
def make_button(parent, text, command=None, width=None, state="normal", accent=False):
    """统一按钮工厂：返回的按钮自带 hover / 按下的曲线过渡。"""
    kwargs = dict(
        text=text, command=command,
        text_color=C_TEXT_INVERSE if accent else C_TEXT_MAIN,
        border_color=C_ACCENT if accent else C_BORDER_SOFT,
        border_width=BORDER_W, corner_radius=R_CONTROL,
        font=(config.FONT_FAMILY, FS_BODY), height=H_CONTROL, state=state)
    if width is not None:
        kwargs['width'] = width
    if accent:
        # 按下要更沉一档：之前 press_color 直接用了 hover 色，按下去看不出变化
        return AnimatedButton(parent, C_ACCENT, C_ACCENT_HOVER,
                               press_color=C_ACCENT_PRESSED, **kwargs)
    return AnimatedButton(parent, C_PANEL_ALT_BG, C_ACCENT_SOFT,
                           press_color=lerp_color(C_ACCENT_SOFT, C_ACCENT, 0.45),
                           **kwargs)


def make_entry(parent, textvariable=None, placeholder="", width=None):
    kwargs = dict(
        fg_color=C_INPUT_BG, border_color=C_BORDER_SOFT, border_width=BORDER_W,
        corner_radius=R_CONTROL, text_color=C_TEXT_MAIN,
        placeholder_text=placeholder, placeholder_text_color=C_TEXT_MUTED,
        font=(config.FONT_FAMILY, FS_BODY), height=H_CONTROL)
    if textvariable is not None:
        kwargs['textvariable'] = textvariable
    if width is not None:
        kwargs['width'] = width
    return ctk.CTkEntry(parent, **kwargs)


def make_display_box(parent, text="", width=None, height=H_CONTROL):
    frame = ctk.CTkFrame(parent, fg_color=C_INPUT_BG, border_color=C_BORDER_SOFT,
                          border_width=BORDER_W, corner_radius=R_CONTROL,
                          height=height)
    frame.pack_propagate(False)
    label = ctk.CTkLabel(frame, text=text, text_color=C_TEXT_SECONDARY,
                          font=(config.FONT_FAMILY, FS_SMALL), anchor="w",
                          fg_color="transparent")
    label.pack(fill=BOTH, expand=True, padx=PAD_INNER)
    return frame, label


def open_path(path) -> bool:
    """在系统文件管理器里打开路径（Windows / macOS / Linux 都支持）。

    原来直接用 os.startfile —— 那是 Windows 专有 API，Linux 版点了
    「打开TACZ / 目录 / 数据库」全都静默失败（只往日志里写一条错误）。
    """
    target = str(path)
    try:
        if IS_WINDOWS:
            os.startfile(target)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def make_list_scroll(parent, listbox, width=10):
    """给 tk.Listbox 配一条细滚动条 + 顺滑滚轮。

    tk.Listbox 本身没有滚动条（要自己配），而且默认滚轮是「一格一行」，
    条目多的时候一格一格跳，手感很卡。这里统一滚 3 行/格，
    并且只在指针位于列表上时生效（返回 "break" 不让事件冒到外层）。
    """
    # height=1 很关键：CTkScrollbar 默认 200x200，不压下去会把列表容器
    # 的「请求高度」顶到 200+，卡片下限跟着虚高，导入框就会被挤出卡片。
    # 实际高度由 pack(fill="y") 决定，这里只要请求值够小。
    bar = ctk.CTkScrollbar(
        parent, width=px(width), height=1, corner_radius=R_PROGRESS,
        fg_color="transparent", button_color=C_BORDER,
        button_hover_color=C_ACCENT, command=listbox.yview)
    listbox.configure(yscrollcommand=bar.set)

    def _scroll(units):
        """逐帧滑过去，而不是整行一跳。

        Tk 的 Listbox 只能按「行」滚，直接 yview_scroll 会一顿一顿的；
        这里把目标位置换算成视图比例，用补间在 140ms 内滑过去。
        """
        total = max(1, listbox.size())
        first, last = listbox.yview()
        visible = max(0.0, last - first)
        start = first
        target = min(max(0.0, first + units / total), max(0.0, 1.0 - visible))
        if abs(target - start) < 1e-6:
            return "break"

        def frame(e, raw):
            try:
                listbox.yview_moveto(start + (target - start) * e)
            except Exception:
                pass

        tween(listbox, "scroll", 140, frame, easing=ease_out_cubic)
        return "break"

    def _on_wheel(event):
        delta = getattr(event, "delta", 0) or 0
        return _scroll(-3 if delta > 0 else 3)

    def _on_wheel_x11(event):
        return _scroll(-3 if event.num == 4 else 3)

    for seq, fn in (("<MouseWheel>", _on_wheel),
                    ("<Button-4>", _on_wheel_x11),
                    ("<Button-5>", _on_wheel_x11)):
        try:
            listbox.bind(seq, fn, add="+")
        except Exception:
            pass
    return bar


def make_label(parent, text="", fg=None, bg=None, font_size=FS_BODY, bold=False,
               justify=None):
    if fg is None:
        fg = C_TEXT_MAIN
    weight = "bold" if bold else "normal"
    kwargs = dict(text=text, text_color=fg,
                  font=(config.FONT_FAMILY, font_size, weight),
                  anchor="w")
    kwargs['fg_color'] = bg if bg is not None else "transparent"
    # justify 只在显式传入时下发，避免影响其余单行标签的外观。
    # （原来多行提示写的是 justify=LEFT，但本工厂没有该参数 -> 一进设置页就 TypeError）
    if justify is not None:
        kwargs['justify'] = justify
    return ctk.CTkLabel(parent, **kwargs)
