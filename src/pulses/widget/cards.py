"""
预设卡片与卡片列表。

Step 2 原来是一个 tk.Listbox（一行一个名字），放不下版本、体积、更新状态。
这里换成卡片：状态点 + 名称 + 元信息 + 状态行 + 动作按钮，整块可点选。

滚动用 Canvas 内嵌 frame 实现，滚轮直接走 Canvas 原生 yview，
不做逐事件补间（补间叠加会卡）。
卡片颜色变化全部走曲线过渡，避免闪烁。
"""
from __future__ import annotations

import math
import time
import tkinter as tk
from tkinter import Canvas

import customtkinter as ctk

from .. import config
from ..animation import (FPS_COLOR, attach_hover_glow, cancel_tween,
                         ease_in_out_cubic, ease_linear, ease_out_cubic,
                         ease_out_soft_spring, lerp_color, tween)
from ..config import (BORDER_W, C_ACCENT, C_ACCENT_HOVER,
                      C_ACCENT_PRESSED, C_ACCENT_SOFT, C_BORDER,
                      C_BORDER_SOFT, C_CARD_BG, C_DIVIDER, C_ERROR,
                      C_INFO, C_INPUT_BG, C_PANEL_ALT_BG, C_SUCCESS,
                      C_TEXT_INVERSE, C_TEXT_MAIN, C_TEXT_MUTED,
                      C_TEXT_SECONDARY, C_WARNING, FS_BODY, FS_SMALL,
                      FS_TINY, PAD_TIGHT, R_CARD, R_CONTROL)
from ..utils import px, tk_font
from .button import AnimatedButton
from .factory import bind_event, ellipsize

H_CARD = 92          # 卡片高度（px，未缩放）
H_CARD_MIN = 78
DOT_SIZE = 10

# 滚动进行中：卡片 hover 过渡先让路，避免快速滚过几十张卡时
# 同时启动几十条 140ms 的颜色补间。
_SCROLL_ACTIVE_UNTIL = 0.0


def _scroll_wheel_dispatch(event):
    """全局滚轮路由：把事件交给指针下最近的 ScrollArea。

    不能在每个 ScrollArea 的 <Enter> 里 bind_all/unbind_all：
    CTkScrollableFrame 自己也用 bind_all，先离开一个卡片列表就会把
    设置页/管理页/侧边栏的滚轮绑定一起解掉，表现为“某些列表突然滚不动”。
    """
    widget = getattr(event, "widget", None)
    while widget is not None:
        if isinstance(widget, ScrollArea):
            return widget._on_wheel(event)
        widget = getattr(widget, "master", None)
    return None


class ScrollArea(ctk.CTkFrame):
    """竖向滚动容器：Canvas + 内嵌 frame + 细滚动条。"""

    def __init__(self, parent, *, bg=C_CARD_BG, bar_width=8, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(parent, **kwargs)
        self._bg = bg
        # height=1：Canvas 默认请求高 276px，会把左列的纵向预算顶爆
        self.canvas = Canvas(self, bg=bg, highlightthickness=0, bd=0,
                             height=1, takefocus=0)
        # height=1：CTkScrollbar 默认 200x200，会顶高容器
        self.bar = ctk.CTkScrollbar(
            self, width=bar_width, height=1, corner_radius=4,
            fg_color="transparent", button_color=C_BORDER,
            button_hover_color=C_ACCENT, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.bar.pack(side="right", fill="y", padx=(2, 0))

        self.inner = ctk.CTkFrame(self.canvas, fg_color="transparent")
        self._window = self.canvas.create_window((0, 0), window=self.inner,
                                                 anchor="nw")
        self.inner.bind("<Configure>", self._on_inner_configure, add="+")
        self.canvas.bind("<Configure>", self._on_canvas_configure, add="+")
        self._bind_global_wheel()

    # ---------- 布局 ----------
    def _on_inner_configure(self, _event=None):
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except Exception:
            pass

    def _on_canvas_configure(self, event):
        try:
            self.canvas.itemconfigure(self._window, width=event.width)
        except Exception:
            pass

    # ---------- 滚轮 ----------
    def _bind_global_wheel(self):
        """每个 Tk root 只装一次全局滚轮路由，不抢占/解绑别人的绑定。"""
        try:
            root = self.winfo_toplevel()
        except Exception:
            return
        if getattr(root, "_pulses_scroll_wheel_bound", False):
            return
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                root.bind_all(seq, _scroll_wheel_dispatch, add="+")
            except Exception:
                pass
        try:
            root._pulses_scroll_wheel_bound = True
        except Exception:
            pass

    def _on_wheel(self, event):
        if getattr(event, "num", None) == 4:
            steps = 1
        elif getattr(event, "num", None) == 5:
            steps = -1
        else:
            steps = 1 if (getattr(event, "delta", 0) or 0) > 0 else -1
        self.scroll_by(-steps)
        return "break"

    def scroll_by(self, units: float) -> None:
        """按"卡片高度"为单位滚动。

        直接用 Canvas 原生 yview_moveto，不再为每个滚轮事件启动 150ms 补间：
        连续滚轮时补间会被反复取消/重开，实际只挪一点点，卡片一多就明显卡。
        """
        global _SCROLL_ACTIVE_UNTIL
        try:
            first, last = self.canvas.yview()
        except Exception:
            return
        visible = max(0.0, last - first)
        if visible >= 0.999:
            return
        step = max(0.04, min(0.35, units * 0.09))
        target = min(max(0.0, first + step), max(0.0, 1.0 - visible))
        if abs(target - first) < 1e-6:
            return
        _SCROLL_ACTIVE_UNTIL = time.monotonic() + 0.16
        try:
            self.canvas.yview_moveto(target)
        except Exception:
            pass

    def scroll_to_top(self) -> None:
        try:
            self.canvas.yview_moveto(0.0)
        except Exception:
            pass


class StatusDot(Canvas):
    """状态圆点：换色走补间，不闪。"""

    def __init__(self, parent, size=DOT_SIZE, color=C_TEXT_MUTED):
        # tk.Canvas 不参与 CTk 的缩放，这里必须自己乘
        size = px(size)
        super().__init__(parent, width=size, height=size, highlightthickness=0,
                         bd=0, bg=C_CARD_BG, takefocus=0)
        self._size = size
        self._color = color
        self._pulsing = False
        self._item = self.create_oval(1, 1, size - 1, size - 1,
                                      fill=color, outline="")

    def set_color(self, color, animate=True):
        if not color or color == self._color:
            return
        start = self._color
        self._color = color
        if self._pulsing:
            self.stop_pulse()
            self.start_pulse(color)
            return
        if not animate or not config.ANIMATIONS_ENABLED:
            try:
                self.itemconfigure(self._item, fill=color)
            except Exception:
                pass
            return

        def frame(e, _raw):
            try:
                self.itemconfigure(self._item, fill=lerp_color(start, color, e))
            except Exception:
                pass

        tween(self, "dot", 220, frame, easing=ease_in_out_cubic, fps=FPS_COLOR)

    def set_bg(self, color):
        try:
            self.configure(bg=color)
        except Exception:
            pass

    # ---------- 呼吸 ----------
    def start_pulse(self, color=None):
        """有更新时让圆点轻轻脉动：只改颜色深浅，不动布局。"""
        if color:
            self._color = color
        if self._pulsing or not config.ANIMATIONS_ENABLED:
            return
        self._pulsing = True
        base = self._color

        def beat():
            if not self._pulsing:
                return

            def frame(e, raw):
                # 0→1→0 的往返，用 sin 让两端都平滑
                wave = (math.sin(raw * math.pi * 2 - math.pi / 2) + 1) / 2
                try:
                    self.itemconfigure(
                        self._item, fill=lerp_color(base, C_TEXT_MUTED,
                                                    wave * 0.45))
                except Exception:
                    pass

            tween(self, "pulse", 1400, frame, on_done=beat,
                  easing=ease_linear, fps=FPS_COLOR)

        beat()

    def stop_pulse(self):
        self._pulsing = False
        cancel_tween(self, "pulse")
        try:
            self.itemconfigure(self._item, fill=self._color)
        except Exception:
            pass


class EmptyState(ctk.CTkFrame):
    """空状态：一个极简圆环 + 标题 + 提示，居中。"""

    def __init__(self, parent, title="", hint="", color=C_TEXT_MUTED,
                 bg=C_CARD_BG):
        super().__init__(parent, fg_color="transparent")
        self._canvas = Canvas(self, width=px(44), height=px(44),
                              highlightthickness=0, bd=0, bg=bg,
                              takefocus=0)
        size = px(44)
        self._canvas.create_oval(4, 4, size - 4, size - 4,
                                 outline=C_BORDER, width=2)
        self._canvas.create_oval(size / 2 - px(3), size / 2 - px(3),
                                 size / 2 + px(3), size / 2 + px(3),
                                 fill=C_BORDER_SOFT, outline="")
        self._canvas.pack(pady=(0, PAD_TIGHT))
        self.title = ctk.CTkLabel(
            self, text=title, text_color=C_TEXT_SECONDARY,
            font=(config.FONT_FAMILY, FS_SMALL, "bold"))
        self.title.pack()
        self.hint = ctk.CTkLabel(
            self, text=hint, text_color=C_TEXT_MUTED,
            font=(config.FONT_FAMILY, FS_TINY))
        self.hint.pack(pady=(px(2), 0))

    def update_text(self, title: str, hint: str = "") -> None:
        self.title.configure(text=title)
        self.hint.configure(text=hint)


class PresetCard(ctk.CTkFrame):
    """一张预设卡片。数据通过 update_data() 刷新，控件复用不重建。"""

    def __init__(self, parent, name, *, on_select=None, on_action=None,
                 on_menu=None, on_open=None):
        super().__init__(parent, fg_color=C_CARD_BG, corner_radius=R_CONTROL,
                         border_width=BORDER_W, border_color=C_CARD_BG,
                         height=H_CARD)
        # 子控件用的是 grid，所以必须关 grid_propagate；
        # 只写 pack_propagate 的话高度仍会被内容顶开（150% 下多出 17px）
        self.pack_propagate(False)
        self.grid_propagate(False)
        self.name = name
        self._on_select = on_select
        self._on_action = on_action
        self._on_menu = on_menu
        self._on_open = on_open
        self._selected = False
        self._action_kind = ""
        self._data: dict = {}
        self._hover_job = None

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.dot = StatusDot(self, color=C_TEXT_MUTED)
        self.dot.grid(row=0, column=0, sticky="w", padx=(12, 8))

        text_box = ctk.CTkFrame(self, fg_color="transparent")
        text_box.grid(row=0, column=1, sticky="nsew",
                      pady=(10, 8), padx=0)
        text_box.grid_columnconfigure(0, weight=1)
        self._text_box = text_box
        # 用来量宽度的字体（负数=像素，和 CTk 实际渲染一致）
        self._name_font = tk_font(config.FONT_FAMILY, FS_BODY, "bold")
        self._meta_font = tk_font(config.FONT_FAMILY, FS_TINY)
        self._status_font = tk_font(config.FONT_FAMILY, FS_TINY)
        self._raw = {"name": str(name), "meta": "", "status": ""}
        self._fit_last = -1

        self.name_label = ctk.CTkLabel(
            text_box, text=name, anchor="w", justify="left",
            text_color=C_TEXT_MAIN,
            font=(config.FONT_FAMILY, FS_BODY, "bold"))
        self.name_label.grid(row=0, column=0, sticky="ew")

        self.meta_label = ctk.CTkLabel(
            text_box, text="", anchor="w", justify="left",
            text_color=C_TEXT_MUTED,
            font=(config.FONT_FAMILY, FS_TINY))
        self.meta_label.grid(row=1, column=0, sticky="ew", pady=(1, 0))

        # 状态行是「唯一需要用户行动」的信息，不再排在最后又最小：
        # 字号抬到 FS_SMALL，有动作时再加粗
        self.status_label = ctk.CTkLabel(
            text_box, text="", anchor="w", justify="left",
            text_color=C_TEXT_SECONDARY,
            font=(config.FONT_FAMILY, FS_SMALL))
        self.status_label.grid(row=2, column=0, sticky="ew", pady=(1, 0))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=0, column=2, sticky="ne",
                     padx=(6, 10), pady=(10, 0))

        self.action_btn = AnimatedButton(
            actions, C_ACCENT, C_ACCENT_HOVER, press_color=C_ACCENT_PRESSED,
            text="更新", width=60, height=26, corner_radius=R_CONTROL,
            border_width=0, text_color=C_TEXT_INVERSE,
            font=(config.FONT_FAMILY, FS_TINY, "bold"), command=self._fire_action)
        self.action_btn.pack(side="left")
        self.action_btn.pack_forget()

        self.menu_btn = AnimatedButton(
            actions, C_PANEL_ALT_BG, C_ACCENT_SOFT,
            press_color=lerp_color(C_ACCENT_SOFT, C_ACCENT, 0.45),
            text="⋯", width=26, height=26, corner_radius=R_CONTROL,
            border_width=0, text_color=C_TEXT_MUTED,
            font=(config.FONT_FAMILY, FS_SMALL, "bold"), command=self._fire_menu)
        self.menu_btn.pack(side="left", padx=(4, 0))

        self.badge = ctk.CTkLabel(
            actions, text="", text_color=C_ACCENT,
            fg_color=C_ACCENT_SOFT, corner_radius=8,
            font=(config.FONT_FAMILY, FS_TINY), height=18, width=46)
        self.badge.pack(side="left", padx=(0, 4))
        self.badge.pack_forget()

        # iOS 分组列表的行：没有描边，靠底部一条内缩分隔线分界；
        # 鼠标经过整行微微加深，选中是强调软色圆角块。
        # 注意：CTk 控件不允许在 place() 里传 width/height，高度要建的时候就给
        self.sep = ctk.CTkFrame(self, fg_color=C_DIVIDER, height=1)
        self.sep.place(relx=0.04, rely=1.0, relwidth=0.92, anchor="sw")
        # 指针从卡片移到卡片里的子控件时，Tk 会给卡片发 <Leave>。
        # 只在卡片本身绑 Enter/Leave 的话，悬停到文字上就会闪回白底。
        # 所有子控件都参与，并用一个短延迟确认指针真的离开了整张卡。
        for widget in (self, text_box, self.name_label, self.meta_label,
                       self.status_label, self.dot, actions,
                       self.action_btn, self.menu_btn, self.badge):
            bind_event(widget, "<Enter>", self._on_hover)
            bind_event(widget, "<Leave>", self._on_hover)
        try:
            text_box.bind("<Configure>", lambda e: self._fit_texts(), add="+")
        except Exception:
            pass

        for widget in (self, text_box, self.name_label, self.meta_label,
                       self.status_label, self.dot):
            bind_event(widget, "<Button-1>", self._select)
            bind_event(widget, "<Double-Button-1>", self._open)
        bind_event(self, "<Button-3>", self._menu_event)
        bind_event(self.name_label, "<Button-3>", self._menu_event)

    # ---------- 事件 ----------
    def _select(self, _event=None):
        if self._on_select is not None:
            self._on_select(self.name)

    def _open(self, _event=None):
        if self._on_open is not None:
            self._on_open(self.name)

    def _fire_action(self):
        if self._on_action is not None:
            self._on_action(self.name, self._action_kind)

    def _fire_menu(self):
        if self._on_menu is not None:
            self._on_menu(self.name, self.menu_btn)

    def _menu_event(self, event):
        if self._on_menu is not None:
            self._on_menu(self.name, event)

    # ---------- 数据 ----------
    def update_data(self, data: dict) -> None:
        """data: name/version/meta/status/status_color/dot_color/action/
        action_kind/badge/applied"""
        self._data = dict(data)
        self._raw["name"] = str(data.get("name") or self.name)
        self._raw["meta"] = str(data.get("meta") or "")
        self._raw["status"] = str(data.get("status") or "")
        self._fit_last = -1
        self._fit_texts()

        actionable = bool(str(data.get("action") or "").strip())
        self.status_label.configure(
            text_color=data.get("status_color") or C_TEXT_SECONDARY,
            font=(config.FONT_FAMILY, FS_SMALL,
                  "bold" if actionable else "normal"))

        dot_color = data.get("dot_color") or C_TEXT_MUTED
        self.dot.set_color(dot_color)
        if data.get("pulse"):
            self.dot.start_pulse(dot_color)
        else:
            self.dot.stop_pulse()

        badge = str(data.get("badge") or "")
        if badge:
            self.badge.configure(text=badge)
            if not self.badge.winfo_ismapped():
                self.badge.pack(side="left", padx=(0, 4),
                                before=self.action_btn
                                if self.action_btn.winfo_ismapped()
                                else self.menu_btn)
        elif self.badge.winfo_ismapped():
            self.badge.pack_forget()

        action = str(data.get("action") or "")
        self._action_kind = str(data.get("action_kind") or "")
        if action:
            self.action_btn.configure(text=action,
                                      state="normal" if data.get(
                                          "action_enabled", True) else "disabled")
            if not self.action_btn.winfo_ismapped():
                self.action_btn.pack(side="left", padx=(0, 4),
                                     before=self.menu_btn)
        elif self.action_btn.winfo_ismapped():
            self.action_btn.pack_forget()

    # ---------- 文本截断 ----------
    def _fit_texts(self):
        """按当前可用宽度把三行文字截到不溢出（多出来的加省略号）。"""
        try:
            avail = self._text_box.winfo_width() - 4
        except Exception:
            return
        if avail <= 24 or avail == self._fit_last:
            return
        self._fit_last = avail
        try:
            self.name_label.configure(
                text=ellipsize(self._raw["name"], self._name_font, avail))
            self.meta_label.configure(
                text=ellipsize(self._raw["meta"], self._meta_font, avail))
            self.status_label.configure(
                text=ellipsize(self._raw["status"], self._status_font, avail))
        except Exception:
            pass

    def _pointer_inside(self) -> bool:
        try:
            x, y = self.winfo_pointerxy()
            left, top = self.winfo_rootx(), self.winfo_rooty()
            return (left <= x <= left + self.winfo_width()
                    and top <= y <= top + self.winfo_height())
        except Exception:
            return False

    def _set_hover(self, over: bool) -> None:
        target = C_INPUT_BG if over else C_CARD_BG
        start = self.cget("fg_color")
        if start == target:
            return

        def frame(e, _raw):
            try:
                self.configure(fg_color=lerp_color(start, target, e))
            except Exception:
                pass

        frame(0.0, 0.0)
        tween(self, "hover", 140, frame, easing=ease_out_cubic,
              fps=FPS_COLOR)

    def _on_hover(self, event=None):
        """整行 hover：子控件之间移动不闪，真正离开后才收回。"""
        if self._selected or time.monotonic() < _SCROLL_ACTIVE_UNTIL:
            return
        # tkinter 的 Event.type 是 EventType 枚举；str(EventType.Enter)
        # 得到的是 "7"，不是 "Enter"。之前这里用 str(...) 比较，真实
        # 鼠标事件永远被当成 Leave，hover 动画其实从未生效。
        etype = getattr(event, "type", None)
        kind = getattr(etype, "name", None) or str(etype or "")
        entering = kind == "Enter"
        job = self._hover_job
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
            self._hover_job = None
        if entering:
            self._set_hover(True)
            return

        def finish():
            self._hover_job = None
            if self._pointer_inside() or self._selected:
                return
            self._set_hover(False)

        try:
            self._hover_job = self.after(70, finish)
        except Exception:
            finish()

    def set_selected(self, selected: bool, animate: bool = True) -> None:
        if selected == self._selected:
            return
        self._selected = selected
        if self._hover_job is not None:
            try:
                self.after_cancel(self._hover_job)
            except Exception:
                pass
            self._hover_job = None
        target_bg = C_ACCENT_SOFT if selected else C_CARD_BG
        start_bg = self.cget("fg_color")
        if not animate or not config.ANIMATIONS_ENABLED:
            self.configure(fg_color=target_bg)
            self.dot.set_bg(target_bg)
            return

        def frame(e, _raw):
            try:
                self.configure(fg_color=lerp_color(start_bg, target_bg, e))
            except Exception:
                pass

        frame(0.0, 0.0)
        tween(self, "select", 210, frame, easing=ease_out_soft_spring,
              fps=FPS_COLOR)
        self.dot.set_bg(target_bg)

    def flash(self) -> None:
        """卡片闪一下强调色（同步完成之类的反馈）。

        卡片本身保持无描边外观：只在动画期间把 1px 描边从底色提到强调色，
        再落回底色。之前直接改 border_color，但 border_width=0，整段动画
        实际上完全看不见。
        """
        base = C_CARD_BG

        def frame(e, raw):
            wave = 1.0 - abs(raw - 0.5) * 2
            try:
                self.configure(
                    border_color=lerp_color(base, C_ACCENT_SOFT, wave))
            except Exception:
                pass

        tween(self, "flash", 520, frame, easing=ease_out_cubic,
              fps=FPS_COLOR,
              on_done=lambda: self.configure(border_color=base))

    def play_enter(self, delay_ms: int = 0) -> None:
        """入场：描边从强调色淡回底色。delay 用来做交错。"""
        if not config.ANIMATIONS_ENABLED:
            return

        def start():
            def frame(e, _raw):
                try:
                    self.configure(
                        border_color=lerp_color(C_ACCENT_SOFT,
                                                C_CARD_BG, e))
                except Exception:
                    pass

            frame(0.0, 0.0)
            tween(self, "enter", 300, frame, easing=ease_out_soft_spring,
                  fps=FPS_COLOR)

        try:
            self.after(delay_ms, start)
        except Exception:
            start()


class CardList(ctk.CTkFrame):
    """卡片列表：按名字复用卡片，增删改都不重建整列。"""

    def __init__(self, parent, *, on_select=None, on_action=None,
                 on_menu=None, on_open=None, empty_text="还没有预设",
                 empty_hint="拖入整合包，或点下面的「选择」",
                 bg=C_CARD_BG):
        super().__init__(parent, fg_color="transparent")
        self._on_select = on_select
        self._on_action = on_action
        self._on_menu = on_menu
        self._on_open = on_open
        self._cards: dict[str, PresetCard] = {}
        self._order: list[str] = []
        self._selected: str | None = None
        self._loading = False
        self._enabled = True

        self.area = ScrollArea(self, bg=bg)
        self.area.pack(fill="both", expand=True)

        self.empty = ctk.CTkFrame(self, fg_color="transparent")
        self.empty_state = EmptyState(self.empty, empty_text, empty_hint,
                                      bg=bg)
        self.empty_state.pack(expand=True)
        # 初始没有任何卡片时就要显示空状态；否则列表区是一块纯白，
        # 用户不知道是“没加载”还是“加载失败”。
        self.empty.pack(fill="both", expand=True)

        self._bind_keys()

    # ---------- 键盘 ----------
    def _bind_keys(self):
        try:
            self.area.canvas.configure(takefocus=1)
            self.area.canvas.bind("<Up>", lambda e: self._move(-1), add="+")
            self.area.canvas.bind("<Down>", lambda e: self._move(1), add="+")
        except Exception:
            pass

    def _move(self, delta: int):
        if not self._order:
            return "break"
        try:
            index = self._order.index(self._selected or "")
        except ValueError:
            index = -1
        index = max(0, min(len(self._order) - 1, index + delta))
        self.select(self._order[index], notify=True)
        return "break"

    # ---------- 状态 ----------
    def set_loading(self, loading: bool) -> None:
        """加载中：清空卡片，空状态改成「正在加载」。"""
        self._loading = bool(loading)
        if loading:
            self.set_items([])
            self.empty_state.update_text("正在加载预设…", "")
            if not self.empty.winfo_ismapped():
                self.empty.pack(fill="both", expand=True)
        else:
            self.empty_state.update_text("还没有预设",
                                         "拖入整合包，或点下面的「选择」")

    def set_enabled(self, enabled: bool) -> None:
        """整体禁用（应用预设的过程中）。"""
        self._enabled = bool(enabled)
        for card in self._cards.values():
            try:
                state = "normal" if enabled else "disabled"
                card.action_btn.configure(state=state)
                card.menu_btn.configure(state=state)
            except Exception:
                pass

    # ---------- 数据 ----------
    def set_items(self, items: list[dict], *, animate_new: bool = True) -> None:
        names = [str(item.get("name") or "") for item in items]
        for stale in [n for n in self._cards if n not in names]:
            card = self._cards.pop(stale)
            try:
                card.destroy()
            except Exception:
                pass
        self._order = names

        new_index = 0
        for position, item in enumerate(items):
            name = str(item.get("name") or "")
            card = self._cards.get(name)
            created = False
            if card is None:
                card = PresetCard(self.area.inner, name,
                                  on_select=self._select_cb,
                                  on_action=self._on_action,
                                  on_menu=self._on_menu,
                                  on_open=self._on_open)
                self._cards[name] = card
                created = True
            card.update_data(item)
            card.pack(fill="x", pady=0, padx=0)
            if created and animate_new and new_index < 8:
                card.play_enter(min(240, new_index * 40))
                new_index += 1
            if name == self._selected:
                card.set_selected(True, animate=False)

        if names:
            if self.empty.winfo_ismapped():
                self.empty.pack_forget()
            if not self._enabled:
                self.set_enabled(False)
        elif not self.empty.winfo_ismapped():
            self.empty.pack(fill="both", expand=True)

    def _select_cb(self, name: str):
        if self._on_select is not None:
            self._on_select(name)

    def select(self, name: str | None, *, notify: bool = False) -> None:
        self._selected = name
        for card_name, card in self._cards.items():
            card.set_selected(card_name == name)
        if notify and self._on_select is not None and name:
            self._on_select(name)

    @property
    def selected_name(self) -> str | None:
        return self._selected

    def card(self, name: str) -> PresetCard | None:
        return self._cards.get(name)

    def flash(self, name: str) -> None:
        card = self._cards.get(name)
        if card is not None:
            card.flash()

    def count(self) -> int:
        return len(self._cards)
