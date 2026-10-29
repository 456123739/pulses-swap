"""页面切换的 logo 覆盖层。

切页不再把整页位图/控件树横向推走，而是先用一块纯色幕布盖住工作区，
在幕布中央浮出完整的 Pulses Swap 字标；页面在幕布下面完成切换和重排，
再从中间把幕布向两侧收掉。

为什么不是整块透明 Canvas：
  · Tk 的 Canvas 没有透明背景，幕布一旦移开就会露出 Canvas 底色；
  · 这里用两个原生 Frame 做左右幕布，中间留出的缝就是真正的页面；
  · 字标直接画在与幕布同色的小 Canvas 上，没有矩形底，天然融合。

动画只移动原生 Frame / 小 Canvas，不碰页面控件树，也不抓截图。
"""
from __future__ import annotations

from tkinter import Canvas, Frame, Label
from tkinter import font as tkfont

from ..config import (
    C_ACCENT, C_COVER_ACCENT, C_COVER_BG, C_COVER_MUTED,
    C_COVER_TEXT, FONT_FAMILY,
)
from ..utils import px, tk_font
from ..animation import (
    FPS_MOVE, cancel_tween, clamp01, ease_in_out_cubic, ease_linear,
    ease_out_back, ease_out_cubic, lerp_color, tween,
)


class PageCover:
    """覆盖在工作区上的纯色字标幕布。"""

    COVER_MS = 250
    LOGO_MS = 280
    REVEAL_MS = 380
    WORD_SIZE = 44
    TRACKING = 1

    def __init__(self, parent):
        self.parent = parent
        self._w = max(1, int(parent.winfo_width()))
        self._h = max(1, int(parent.winfo_height()))
        self._visible = False
        self._phase = "idle"          # idle / covering / holding / revealing
        self._progress = 0.0

        # 整块入场幕布 + 出场时用的左右半幕。三者同色，切换时看不出接缝。
        self.panel = Frame(parent, bg=C_COVER_BG, bd=0, highlightthickness=0)
        self.left = Frame(parent, bg=C_COVER_BG, bd=0, highlightthickness=0)
        self.right = Frame(parent, bg=C_COVER_BG, bd=0, highlightthickness=0)
        self.edge = Frame(parent, bg=C_COVER_ACCENT, bd=0, highlightthickness=0)
        self.left_edge = Frame(parent, bg=C_COVER_ACCENT, bd=0, highlightthickness=0)
        self.right_edge = Frame(parent, bg=C_COVER_ACCENT, bd=0, highlightthickness=0)
        for widget in (self.panel, self.left, self.right,
                       self.edge, self.left_edge, self.right_edge):
            widget.place_forget()
            widget.bind("<Button-1>", self._swallow)
            widget.bind("<ButtonRelease-1>", self._swallow)

        # 字标单独一个小 Canvas：底色与大幕布完全相同，只有文字像素。
        self.logo = Canvas(
            parent, bg=C_COVER_BG, highlightthickness=0, bd=0, takefocus=0)
        self.logo.place_forget()
        self.logo.bind("<Button-1>", self._swallow)
        self.logo.bind("<ButtonRelease-1>", self._swallow)

        self._font = tkfont.Font(
            family=FONT_FAMILY, size=-max(18, px(self.WORD_SIZE)),
            weight="normal")
        self._tracking = max(0, px(self.TRACKING))
        self._glyphs = []          # (canvas item, target color)
        self._bar = None
        self._build_wordmark()

        self.footer = Label(
            parent, text="PULSES 0 Studio · NimShade & DS",
            bg=C_COVER_BG, fg=C_COVER_MUTED,
            font=tk_font(FONT_FAMILY, 11), bd=0,
            highlightthickness=0, padx=0, pady=0)
        self.footer.place_forget()
        self.footer.bind("<Button-1>", self._swallow)

        try:
            parent.bind("<Configure>", self._on_configure, add="+")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    @property
    def visible(self):
        return self._visible

    @property
    def phase(self):
        return self._phase

    def cover(self, on_covered=None):
        """幕布从下往上盖住工作区；完全盖住后回调 on_covered。"""
        self.cancel()
        self._visible = True
        self._phase = "covering"
        self._progress = 0.0
        self._size_from_parent()
        self._hide_logo()
        self._place_cover(0.0)
        self.panel.lift()
        self.edge.lift()

        def frame(_eased, raw):
            self._progress = clamp01(raw)
            self._place_cover(self._progress)

        def done():
            self._progress = 1.0
            self._place_cover(1.0)
            self._phase = "holding"
            self._show_logo()
            self._logo_in()
            if on_covered is not None:
                on_covered()

        tween(self.parent, "page_cover", self.COVER_MS, frame, done,
              easing=ease_linear, fps=FPS_MOVE)

    def reveal(self, on_done=None):
        """字标先向上退场，随后左右幕布从中间缩窄。"""
        if not self._visible:
            if on_done is not None:
                on_done()
            return
        cancel_tween(self.parent, "page_cover")
        cancel_tween(self.parent, "page_logo")
        self._phase = "revealing"
        self._progress = 0.0
        self._show_halves()
        self._set_logo_final_colors()

        start_y = self._logo_y()
        travel = start_y + self._logo_canvas_h + px(24)

        def frame(_eased, raw):
            self._progress = clamp01(raw)
            # 前半段：字标向上退场。幕布仍完整，字标 Canvas 底色与幕布同色。
            logo_t = ease_out_cubic(min(1.0, self._progress / 0.42))
            self.logo.place_configure(
                y=int(round(start_y - travel * logo_t)))
            if self._progress >= 0.42:
                self.logo.place_forget()
            if self._progress >= 0.16:
                self.footer.place_forget()
            # 后半段：左右幕布从中间缩窄，页面从中间露出来。
            split = ease_in_out_cubic(
                clamp01((self._progress - 0.16) / 0.84))
            # 用“缩窄”而不是“整体向外移”：Tk 普通控件不会被父容器裁剪，
            # 半幕移出 page_host 会盖到侧栏或状态条上。
            half = self._w // 2
            shift = int(round(half * split))
            self.left.place_configure(
                x=0, y=0, width=max(1, half - shift), height=self._h)
            self.right.place_configure(
                x=half + shift, y=0,
                width=max(1, self._w - (half + shift)), height=self._h)
            self.left_edge.place_configure(x=half - shift - px(2))
            self.right_edge.place_configure(x=half + shift)

        def done():
            self._hide()
            if on_done is not None:
                on_done()

        tween(self.parent, "page_reveal", self.REVEAL_MS, frame, done,
              easing=ease_linear, fps=FPS_MOVE)

    def cancel(self):
        """立即撤掉幕布（无回调）。用于关窗、无动画切页、快速重入。"""
        for key in ("page_cover", "page_logo", "page_reveal"):
            cancel_tween(self.parent, key)
        self._hide()

    # ------------------------------------------------------------------
    # 几何 / 绘制
    # ------------------------------------------------------------------
    def _size_from_parent(self):
        try:
            w = max(1, int(self.parent.winfo_width()))
            h = max(1, int(self.parent.winfo_height()))
        except Exception:
            w, h = self._w, self._h
        if w > 1 and h > 1:
            self._w, self._h = w, h

    def _on_configure(self, event):
        if event.widget is not self.parent:
            return
        self._w = max(1, int(event.width))
        self._h = max(1, int(event.height))
        if not self._visible:
            return
        if self._phase == "revealing":
            self._show_halves()
        elif self._phase in ("covering", "holding"):
            self._place_cover(self._progress)
            if self._phase == "holding":
                self._place_footer()
                self.logo.place(x=self._logo_x(), y=self._logo_y(),
                                width=self._logo_canvas_w,
                                height=self._logo_canvas_h)

    def _place_cover(self, progress):
        """入场幕布：从 y=h 平滑升到 y=0。"""
        h = self._h
        w = self._w
        y = int(round(h * (1.0 - ease_in_out_cubic(progress))))
        # 幕布高度只到 page_host 底边：Tk 不会裁剪子控件，整块 Frame
        # 从下方移进来会溢出到状态条/窗口底部。
        if y >= h:
            self.panel.place_forget()
        else:
            self.panel.place(x=0, y=y, width=w, height=max(1, h - y))
        if 0 < y < h:
            self.edge.place(x=0, y=max(0, y - px(2)),
                            width=w, height=max(2, px(3)))
            self.edge.lift()
        else:
            self.edge.place_forget()
        # 动画期间前面可能残留出场用的半幕，统一收起来。
        for widget in (self.left, self.right,
                       self.left_edge, self.right_edge):
            widget.place_forget()

    def _show_halves(self):
        w = self._w
        h = self._h
        self.panel.place_forget()
        self.edge.place_forget()
        self.left.place(x=0, y=0, width=w // 2, height=h)
        self.right.place(x=w // 2, y=0, width=w - w // 2, height=h)
        self.left_edge.place(x=w // 2 - px(2), y=0,
                             width=max(2, px(3)), height=h)
        self.right_edge.place(x=w // 2, y=0,
                              width=max(2, px(3)), height=h)
        self.left.lift()
        self.right.lift()
        self.left_edge.lift()
        self.right_edge.lift()
        if self._visible and self._phase in ("holding", "revealing"):
            self.logo.tk.call("raise", self.logo._w)

    # ------------------------------------------------------------------
    # 字标
    # ------------------------------------------------------------------
    def _build_wordmark(self):
        """排一个长条形字标：细竖线 + Pulses Swap。

        逐字 draw 是为了自己控制字距；Tk Canvas 的 text 没有 letter-spacing。
        “Pulses” 用暖白，“Swap” 用低饱和青，读起来是一个完整的名字而不是缩写。
        """
        tracking = self._tracking
        gap = self._font.measure(" ") + px(5)
        letters = []
        for word, color in (("Pulses", C_COVER_TEXT),
                            ("Swap", C_COVER_ACCENT)):
            for ch in word:
                letters.append([ch, self._font.measure(ch), color])
        word_w = sum(item[1] for item in letters) + tracking * (len(letters) - 1)
        lock_w = word_w + gap
        bar_w = max(2, px(2))
        bar_gap = px(18)
        canvas_w = max(px(360), lock_w + bar_w + bar_gap + px(96))
        canvas_h = max(px(86), px(self.WORD_SIZE) + px(42))
        self._logo_canvas_w = canvas_w
        self._logo_canvas_h = canvas_h
        self.logo.configure(width=canvas_w, height=canvas_h)

        left = (canvas_w - (bar_w + bar_gap + lock_w)) // 2
        bar_x = left
        cy = canvas_h // 2
        self._bar = self.logo.create_rectangle(
            bar_x, cy - px(23), bar_x + bar_w, cy + px(23),
            fill=C_COVER_BG, outline="")
        x = bar_x + bar_w + bar_gap
        for index, (ch, width, color) in enumerate(letters):
            item = self.logo.create_text(
                x, cy, text=ch, anchor="w",
                fill=C_COVER_BG, font=self._font)
            self._glyphs.append((item, color, x))
            x += width + tracking
            if index == 5:          # Pulses 与 Swap 之间留呼吸
                x += gap
        self._logo_y_center = cy
        self._logo_left = left

    def _logo_y(self):
        return int(round(self._h / 2 - self._logo_canvas_h / 2))

    def _logo_x(self):
        return int(round((self._w - self._logo_canvas_w) / 2))

    def _show_logo(self):
        self.logo.itemconfigure(self._bar, state="normal", fill=C_COVER_BG)
        for item, _color, _x in self._glyphs:
            self.logo.itemconfigure(item, state="normal", fill=C_COVER_BG)
        self.logo.place(x=self._logo_x(), y=self._logo_y(),
                        width=self._logo_canvas_w,
                        height=self._logo_canvas_h)
        self.logo.tk.call("raise", self.logo._w)
        self._place_footer()
        self.footer.lift()

    def _set_logo_final_colors(self):
        self.logo.itemconfigure(self._bar, fill=C_COVER_ACCENT)
        for item, color, _x in self._glyphs:
            self.logo.itemconfigure(item, fill=color)
        self.footer.configure(fg=C_COVER_MUTED)

    def _hide_logo(self):
        for item, _color, _x in self._glyphs:
            try:
                self.logo.itemconfigure(item, state="hidden")
            except Exception:
                pass
        try:
            self.logo.itemconfigure(self._bar, state="hidden")
        except Exception:
            pass
        self.logo.place_forget()
        self.footer.place_forget()

    def _place_footer(self):
        try:
            self.footer.place(x=self._w // 2, y=self._h - px(34),
                              anchor="s")
        except Exception:
            pass

    def _logo_in(self):
        start = px(8)

        def frame(_eased, raw):
            # 字标从下往上轻轻落位；每个字从幕布色淡入。
            dy = int(round(start * (1.0 - ease_out_back(raw, 0.8))))
            cy = self._logo_y_center + dy
            bar_x = self._logo_left
            self.logo.coords(
                self._bar, bar_x, cy - px(23),
                bar_x + max(2, px(2)), cy + px(23))
            mix = min(1.0, raw * 3.4)
            for item, color, x in self._glyphs:
                self.logo.coords(item, x, cy)
                self.logo.itemconfigure(
                    item, fill=lerp_color(C_COVER_BG, color, mix))
            self.logo.itemconfigure(
                self._bar, fill=lerp_color(C_COVER_BG, C_COVER_ACCENT, mix))

        frame(0.0, 0.0)
        tween(self.parent, "page_logo", self.LOGO_MS, frame,
              easing=ease_out_back, fps=FPS_MOVE)

    def _hide(self):
        self._phase = "idle"
        self._visible = False
        self._progress = 0.0
        for widget in (self.panel, self.left, self.right,
                       self.edge, self.left_edge, self.right_edge):
            widget.place_forget()
        self._hide_logo()

    def _swallow(self, _event=None):
        return "break"
