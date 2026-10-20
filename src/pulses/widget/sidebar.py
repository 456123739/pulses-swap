"""侧边栏专用控件：矢量图标导航 + 玩家/开发者滑动开关。

这两个控件都用 tk.Canvas 自绘：
  · 折叠成图标时只画图标，展开后同一套坐标里补上文字；
  · 宽度变化由父容器驱动，Canvas 在 <Configure> 里重排，不会把文字挤出边界；
  · 图标是线条画的，不依赖 emoji / 字体图标，Windows 7 到 11 都不会变成方框。
"""
from __future__ import annotations

import math
from tkinter import *

import customtkinter as ctk

from .. import config
from ..config import *
from ..utils import *
from ..animation import *


def _round_rect_points(x1, y1, x2, y2, radius):
    radius = max(0.0, min(float(radius), (x2 - x1) / 2.0, (y2 - y1) / 2.0))
    return [
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
    ]


class SidebarNav(Canvas):
    """侧边导航：折叠态是图标栏，展开态是图标 + 文字。"""

    ICONS = ("home", "cloud", "settings", "log")

    def __init__(self, parent, items, command=None, expanded=False,
                 item_height=None, bg_color=C_CARD_BG,
                 pill_color=C_ACCENT_SOFT, hover_color=C_ACCENT_SOFT,
                 text_color=C_TEXT_MAIN, active_text_color=C_ACCENT,
                 collapsed_width=56):
        self._item_h = px(item_height or 42)
        self._pad = px(6)
        self._gap = px(4)
        self._collapsed_w = px(collapsed_width)
        height = 2 * self._pad + len(items) * self._item_h + \
            max(0, len(items) - 1) * self._gap
        super().__init__(parent, bg=bg_color, highlightthickness=0, bd=0,
                         height=height, width=self._collapsed_w)
        self._items = [(str(k), str(t)) for k, t in items]
        self._keys = [k for k, _ in self._items]
        self._command = command
        self._expanded = bool(expanded)
        self._bg = bg_color
        self._pill = pill_color
        self._hover_color = hover_color
        self._text_color = text_color
        self._active_text_color = active_text_color
        self._font = tk_font(config.FONT_FAMILY, FS_BODY)
        self._font_active = tk_font(config.FONT_FAMILY, FS_BODY, "bold")
        self._active = None
        self._hover_index = -1
        self._rects = []
        self._pill_id = None
        self._pill_rect = None
        self._icon_ids = []
        self._text_ids = []
        self._hover_id = None
        self._size = (0, 0)
        self._busy = False
        self.bind("<Configure>", self._on_configure)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    # ---------- 几何 ----------
    def _layout(self, width, height):
        width = max(1, width)
        count = max(1, len(self._items))
        top = self._pad
        rects = []
        for i in range(count):
            y = top + i * (self._item_h + self._gap)
            rects.append((self._pad, y, width - self._pad, y + self._item_h))
        self._rects = rects
        self.delete("all")
        self._icon_ids = []
        self._text_ids = []
        self._pill_id = self.create_polygon(
            *_round_rect_points(-8, -8, -4, -4, px(R_CONTROL)),
            smooth=True, splinesteps=20, fill=self._bg, outline="")
        self._hover_id = self.create_polygon(
            *_round_rect_points(-8, -8, -4, -4, px(R_CONTROL)),
            smooth=True, splinesteps=20, fill=self._bg, outline="")
        for index, (key, text) in enumerate(self._items):
            x1, y1, x2, y2 = rects[index]
            cy = (y1 + y2) / 2.0
            icon_x = (x1 + x2) / 2.0 if not self._expanded else x1 + px(20)
            icon = self._draw_icon(key, icon_x, cy, self._text_color)
            self._icon_ids.append(icon)
            label = self.create_text(
                x1 + px(38), cy, text=text, anchor="w",
                fill=self._text_color, font=self._font,
                state="normal" if self._expanded else "hidden")
            self._text_ids.append(label)
        if self._active in self._keys:
            index = self._keys.index(self._active)
            # 宽度变化会重建文字/图标：把选中态的颜色和字重补回来，
            # 否则展开/收起后当前项会看起来像没选中。
            for i in range(len(self._items)):
                color = (self._active_text_color if i == index
                         else self._text_color)
                self._set_icon_color(i, color)
                try:
                    self.itemconfigure(
                        self._text_ids[i], fill=color,
                        font=self._font_active if i == index else self._font)
                except Exception:
                    pass
            self._paint_active(index, animate=False)
        if 0 <= self._hover_index < len(rects):
            self._paint_hover(self._hover_index)

    def _on_configure(self, event):
        size = (max(1, event.width), max(1, event.height))
        if size == self._size:
            return
        self._size = size
        self._layout(*size)

    def _index_at(self, x, y):
        for index, (x1, y1, x2, y2) in enumerate(self._rects):
            if x1 <= x <= x2 and y1 <= y <= y2:
                return index
        return -1

    # ---------- 图标 ----------
    def _draw_icon(self, key, x, y, color):
        """所有图标都是 18×18 的线稿，返回一个 group tag 方便整体换色。"""
        tag = f"icon_{id(self)}_{len(self._icon_ids)}"
        w = px(9)
        lw = max(1, int(round(1.6 * max(1.0, config.UI_SCALE))))
        shape_opts = dict(outline=color, width=lw, tags=(tag,))
        line_opts = dict(fill=color, width=lw, tags=(tag,),
                         capstyle="round", joinstyle="round")
        if key == "home":
            self.create_line(x - w, y, x, y - w, x + w, y, **line_opts)
            self.create_line(x - w + px(2), y, x - w + px(2), y + w, **line_opts)
            self.create_line(x + w - px(2), y, x + w - px(2), y + w, **line_opts)
            self.create_line(x - w + px(2), y + w, x + w - px(2), y + w, **line_opts)
        elif key == "cloud":
            self.create_oval(x - w, y - px(2), x, y + px(5), **shape_opts)
            self.create_oval(x - px(3), y - px(6), x + px(6), y + px(4), **shape_opts)
            self.create_oval(x + px(1), y - px(3), x + w, y + px(4), **shape_opts)
            self.create_line(x - w + px(1), y + px(5), x + w - px(1),
                             y + px(5), **line_opts)
        elif key in ("manage", "cloud"):
            # 刀片服务器：机箱 + 两条横向隔板 + 右侧三颗状态灯。
            # 小尺寸下不要画三层嵌套矩形，会糊成一团黑块。
            self.create_rectangle(x - w, y - w, x + w, y + w, **shape_opts)
            for dy in (-px(3), px(3)):
                self.create_line(x - w + px(2), y + dy,
                                 x + w - px(2), y + dy, **line_opts)
            for dy in (-px(6), 0, px(6)):
                self.create_rectangle(x + w - px(3), y + dy - px(0.7),
                                      x + w - px(2), y + dy + px(0.7),
                                      **shape_opts)
        elif key == "settings":
            self.create_oval(x - px(4), y - px(4), x + px(4), y + px(4),
                             **shape_opts)
            self.create_oval(x - px(1.5), y - px(1.5), x + px(1.5),
                             y + px(1.5), **shape_opts)
            for i in range(6):
                angle = math.pi * 2 * i / 6 - math.pi / 2
                self.create_line(x + math.cos(angle) * px(5),
                                 y + math.sin(angle) * px(5),
                                 x + math.cos(angle) * px(7),
                                 y + math.sin(angle) * px(7), **line_opts)
        elif key == "log":
            self.create_rectangle(x - w + px(1), y - w, x + w - px(1), y + w,
                                  **shape_opts)
            for dy in (-px(4), 0, px(4)):
                self.create_line(x - px(4), y + dy, x + px(3), y + dy, **line_opts)
        else:
            self.create_oval(x - w, y - w, x + w, y + w, **shape_opts)
        return tag

    def _set_icon_color(self, index, color):
        if not (0 <= index < len(self._icon_ids)):
            return
        tag = self._icon_ids[index]
        try:
            for item in self.find_withtag(tag):
                if self.type(item) == "line":
                    self.itemconfigure(item, fill=color)
                else:
                    self.itemconfigure(item, outline=color)
        except Exception:
            pass

    # ---------- 选中 / 悬停 ----------
    def _paint_active(self, index, animate=True):
        if not self._rects:
            return
        target = self._rects[index]
        start = self._pill_rect or target
        if not animate:
            self._pill_rect = target
            self.coords(self._pill_id, *_round_rect_points(
                target[0], target[1], target[2], target[3], px(R_CONTROL)))
            self.itemconfigure(self._pill_id, fill=self._pill)
            self.tag_raise(self._pill_id)
            self._raise_content()
            return

        def frame(e, raw):
            rect = tuple(lerp(a, b, e) for a, b in zip(start, target))
            self._pill_rect = rect
            self.coords(self._pill_id, *_round_rect_points(
                rect[0], rect[1], rect[2], rect[3], px(R_CONTROL)))
            self.itemconfigure(
                self._pill_id, fill=lerp_color(self._bg, self._pill, e))
            self.tag_raise(self._pill_id)
            self._raise_content()

        tween(self, "nav_pill", 220, frame, easing=ease_out_pill,
              fps=FPS_MOVE)

    def _raise_content(self):
        for item in self._icon_ids + self._text_ids:
            try:
                self.tag_raise(item)
            except Exception:
                pass

    def _paint_hover(self, index):
        if not (0 <= index < len(self._rects)):
            return
        rect = self._rects[index]
        self.coords(self._hover_id, *_round_rect_points(
            rect[0], rect[1], rect[2], rect[3], px(R_CONTROL)))
        self.itemconfigure(self._hover_id, fill=self._hover_color)
        self.tag_raise(self._hover_id)
        self.tag_raise(self._pill_id)
        self._raise_content()

    def _clear_hover(self):
        try:
            self.coords(self._hover_id, -8, -8, -4, -4)
        except Exception:
            pass

    def _on_motion(self, event):
        self._hover_index = self._index_at(event.x, event.y)
        if self._hover_index >= 0:
            self._paint_hover(self._hover_index)
        else:
            self._clear_hover()

    def _on_leave(self, _event=None):
        self._hover_index = -1
        self._clear_hover()

    def _on_click(self, event):
        index = self._index_at(event.x, event.y)
        if index < 0:
            return
        self.select(self._keys[index], animate=True, notify=True)

    # ---------- 对外 ----------
    def set_expanded(self, expanded: bool):
        expanded = bool(expanded)
        if expanded == self._expanded:
            return
        self._expanded = expanded
        if self._size[0] > 1:
            self._layout(*self._size)

    def select(self, key, animate=True, notify=False):
        if key not in self._keys:
            return
        old = self._active
        self._active = key
        index = self._keys.index(key)
        self._paint_active(index, animate=animate)
        for i in range(len(self._items)):
            color = self._active_text_color if i == index else self._text_color
            self._set_icon_color(i, color)
            try:
                self.itemconfigure(
                    self._text_ids[i], fill=color,
                    font=self._font_active if i == index else self._font)
            except Exception:
                pass
        if notify and callable(self._command):
            try:
                self._command(key)
            except Exception:
                pass

    def current(self):
        return self._active

    def refresh_colors(self, bg=None, pill=None, hover=None,
                       text=None, active=None):
        if bg is not None:
            self._bg = bg
            self.configure(bg=bg)
        if pill is not None:
            self._pill = pill
        if hover is not None:
            self._hover_color = hover
        if text is not None:
            self._text_color = text
        if active is not None:
            self._active_text_color = active
        if self._size[0] > 1:
            self._layout(*self._size)


class RoleSwitch(Canvas):
    """玩家 / 开发者滑动开关：滑块曲线滑动，配色跟着身份走。"""

    def __init__(self, parent, command=None, role="player",
                 bg_color=C_CARD_BG, height=34):
        self._h = px(height)
        super().__init__(parent, bg=bg_color, highlightthickness=0, bd=0,
                         height=self._h, width=px(160))
        self._bg = bg_color
        self._command = command
        self._role = "developer" if str(role).startswith("dev") else "player"
        self._accent = C_ACCENT
        self._font = tk_font(config.FONT_FAMILY, FS_SMALL)
        self._font_active = tk_font(config.FONT_FAMILY, FS_SMALL, "bold")
        self._size = (0, 0)
        self._pill = None
        self._label_ids = {}
        self._pill_rect = None
        self._busy = False
        self.bind("<Configure>", self._on_configure)
        self.bind("<Button-1>", self._on_click)

    def _on_configure(self, event):
        size = (max(1, event.width), max(1, event.height))
        if size == self._size:
            return
        self._size = size
        self._layout(*size)

    def _layout(self, width, height):
        self.delete("all")
        pad = px(3)
        inner_w = max(10, width - 2 * pad)
        half = inner_w / 2.0
        top = pad
        bottom = max(top + 4, height - pad)
        self._rects = {
            "player": (pad, top, pad + half, bottom),
            "developer": (pad + half, top, pad + half * 2, bottom),
        }
        self._track = self.create_polygon(
            *_round_rect_points(0, 0, width, height, px(R_CONTROL)),
            smooth=True, splinesteps=20, fill=C_PANEL_ALT_BG, outline="")
        self._pill = self.create_polygon(
            *_round_rect_points(-8, -8, -4, -4, px(R_CONTROL)),
            smooth=True, splinesteps=20, fill=C_ACCENT, outline="")
        for role, text in (("player", "玩家"), ("developer", "开发者")):
            x1, y1, x2, y2 = self._rects[role]
            self._label_ids[role] = self.create_text(
                (x1 + x2) / 2.0, (y1 + y2) / 2.0, text=text,
                fill=C_TEXT_SECONDARY, font=self._font)
        self._paint(animate=False)

    def _paint(self, animate=True, previous=None):
        if not getattr(self, "_rects", None):
            return
        target = self._rects[self._role]
        start = self._pill_rect or previous or target
        active_color = self._accent

        def paint(rect, color):
            self._pill_rect = rect
            self.coords(self._pill, *_round_rect_points(
                rect[0], rect[1], rect[2], rect[3], px(R_CONTROL)))
            self.itemconfigure(self._pill, fill=color)
            self.tag_raise(self._track)
            self.tag_raise(self._pill)
            for role, item in self._label_ids.items():
                is_active = role == self._role
                self.itemconfigure(
                    item, fill=C_TEXT_INVERSE if is_active
                    else C_TEXT_SECONDARY,
                    font=self._font_active if is_active else self._font)
                self.tag_raise(item)

        if not animate:
            paint(target, active_color)
            return

        def frame(e, raw):
            rect = tuple(lerp(a, b, e) for a, b in zip(start, target))
            paint(rect, lerp_color(C_ACCENT_SOFT, active_color, e))

        frame(0.0, 0.0)
        tween(self, "role_pill", 260, frame, easing=ease_out_pill,
              fps=FPS_MOVE,
              on_done=lambda: paint(target, active_color))

    def _hit(self, x, y):
        for role, rect in self._rects.items():
            if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
                return role
        return None

    def _on_click(self, event):
        role = self._hit(event.x, event.y)
        if role is None or role == self._role or self._busy:
            return
        if callable(self._command):
            try:
                self._command(role)
            except Exception:
                pass

    def set_role(self, role, animate=True):
        role = "developer" if str(role).startswith("dev") else "player"
        if role == self._role:
            return
        previous = self._pill_rect
        self._role = role
        self._paint(animate=animate, previous=previous)

    def current(self):
        return self._role

    def set_busy(self, busy):
        self._busy = bool(busy)

    def refresh_colors(self, bg=None, accent=None):
        changed = False
        if bg is not None and bg != self._bg:
            self._bg = bg
            self.configure(bg=bg)
            changed = True
        if accent is not None and accent != self._accent:
            self._accent = accent
            changed = True
        if changed and self._size[0] > 1:
            self._layout(*self._size)
