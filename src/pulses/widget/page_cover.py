"""页面切换的 logo 覆盖层。

切页不再把整页位图/控件树横向推走，而是先用一块纯色幕布盖住工作区，
在幕布中央浮出品牌字标；页面在幕布下面完成切换和重排，再从中间
把幕布向两侧拉开。

为什么不是整块透明 Canvas：
  · Tk 的 Canvas 没有透明背景，幕布一旦移开就会露出 Canvas 底色；
  · 这里用两个原生 Frame 做左右幕布，中间留出的缝就是真正的页面；
  · logo 单独放在一个与幕布同色的小 Canvas 上，背景完全融合，看不出矩形。

动画只移动原生 Frame / 小 Canvas，不碰页面控件树，也不抓截图。
"""
from __future__ import annotations

from tkinter import Canvas, Frame, Label

from ..config import (
    C_ACCENT, C_COVER_BG, C_COVER_MUTED, C_COVER_TEXT,
    FONT_FAMILY,
)
from ..utils import px, resource_path, tk_font
from ..animation import (
    FPS_MOVE, cancel_tween, clamp01, ease_in_out_cubic, ease_linear,
    ease_out_back, ease_out_cubic, lerp_color, tween,
)


class PageCover:
    """覆盖在工作区上的纯色 logo 幕布。"""

    COVER_MS = 250
    LOGO_MS = 270
    REVEAL_MS = 380
    LOGO_PX = 112

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
        self.edge = Frame(parent, bg=C_ACCENT, bd=0, highlightthickness=0)
        self.left_edge = Frame(parent, bg=C_ACCENT, bd=0, highlightthickness=0)
        self.right_edge = Frame(parent, bg=C_ACCENT, bd=0, highlightthickness=0)
        for widget in (self.panel, self.left, self.right,
                       self.edge, self.left_edge, self.right_edge):
            widget.place_forget()
            widget.bind("<Button-1>", self._swallow)
            widget.bind("<ButtonRelease-1>", self._swallow)

        # logo 单独一个小 Canvas：底色与大幕布完全相同，边缘不可见。
        self.logo = Canvas(
            parent, bg=C_COVER_BG, highlightthickness=0, bd=0, takefocus=0)
        self.logo.place_forget()
        self.logo.bind("<Button-1>", self._swallow)
        self.logo.bind("<ButtonRelease-1>", self._swallow)
        self._logo_w = max(48, px(self.LOGO_PX))
        self._logo_h = max(28, int(round(self._logo_w * 0.52)))
        self._logo_photo = None
        self._logo_image_ok = False
        self._logo_canvas_w = 1
        self._logo_canvas_h = 1

        self._logo_item = self.logo.create_image(0, 0, anchor="center")
        self._fallback_text = self.logo.create_text(
            0, 0, text="SW", anchor="center", fill=C_COVER_TEXT,
            font=tk_font(FONT_FAMILY, 40, "bold"), state="hidden")
        self._word = self.logo.create_text(
            0, 0, text="PULSES SWAP", anchor="center",
            fill=C_COVER_BG, font=tk_font(FONT_FAMILY, 13, "bold"))
        self._rule = self.logo.create_line(
            0, 0, 0, 0, fill=C_COVER_BG, width=max(1, px(1)))
        self.footer = Label(
            parent, text="PULSES 0 Studio · NimShade & DS",
            bg=C_COVER_BG, fg=C_COVER_MUTED,
            font=tk_font(FONT_FAMILY, 11), bd=0,
            highlightthickness=0, padx=0, pady=0)
        self.footer.place_forget()
        self.footer.bind("<Button-1>", self._swallow)

        self._load_logo()
        self._layout_logo_canvas()

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
        """logo 先向上退场，随后左右幕布从中间拉开。"""
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
            # 前半段：logo 向上退场。幕布仍完整，logo 底色与幕布同色。
            logo_t = ease_out_cubic(min(1.0, self._progress / 0.42))
            self.logo.place_configure(
                y=int(round(start_y - travel * logo_t)))
            if self._progress >= 0.42:
                self.logo.place_forget()
            # 后半段：左右幕布向两侧拉开，页面从中间露出来。
            if self._progress >= 0.16:
                self.footer.place_forget()
            split = ease_in_out_cubic(
                clamp01((self._progress - 0.16) / 0.84))
            # 用“缩窄”而不是“整体向外移”：Tk 普通控件不会被父容器裁剪，
            # 半幕移出 page_host 会盖到侧栏或状态条上。宽度从中间向两边
            # 收掉，视觉上仍是幕布从中间拉开，但任何一帧都不会越界。
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
            # 窗口在动画中被缩放：按当前进度重画，避免半幕停在旧位置。
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

    def _layout_logo_canvas(self):
        """按字标大小排一个刚刚好的小 Canvas，留出足够留白。"""
        pad_top = px(30)
        self._logo_cy = pad_top + self._logo_h // 2
        self._word_y = self._logo_cy + self._logo_h // 2 + px(22)
        self._rule_y = self._word_y + px(20)
        self._logo_canvas_w = max(px(260), self._logo_w + px(96))
        self._logo_canvas_h = self._rule_y + px(26)
        self.logo.configure(width=self._logo_canvas_w,
                            height=self._logo_canvas_h)
        self._place_logo(0)

    def _logo_y(self):
        return int(round(self._h / 2 - self._logo_cy))

    def _logo_x(self):
        return int(round((self._w - self._logo_canvas_w) / 2))

    def _show_logo(self):
        if self._logo_image_ok:
            self.logo.itemconfigure(self._logo_item, state="normal")
        else:
            self.logo.itemconfigure(self._fallback_text, state="normal")
        self._place_logo(0)
        self.logo.itemconfigure(self._word, state="normal")
        self.logo.itemconfigure(self._rule, state="normal")
        self.logo.itemconfigure(self._word, fill=C_COVER_BG)
        self.logo.itemconfigure(self._rule, fill=C_COVER_BG)
        self.logo.place(x=self._logo_x(), y=self._logo_y(),
                        width=self._logo_canvas_w,
                        height=self._logo_canvas_h)
        self.logo.tk.call("raise", self.logo._w)
        self._place_footer()
        self.footer.lift()

    def _set_logo_final_colors(self):
        self.logo.itemconfigure(self._word, fill=C_COVER_TEXT)
        self.logo.itemconfigure(self._rule, fill=C_ACCENT)
        self.footer.configure(fg=C_COVER_MUTED)

    def _hide_logo(self):
        for item in (self._logo_item, self._fallback_text,
                     self._word, self._rule):
            try:
                self.logo.itemconfigure(item, state="hidden")
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

    def _place_logo(self, offset=0):
        cx = self._logo_canvas_w // 2
        cy = self._logo_cy + int(offset)
        self.logo.coords(self._logo_item, cx, cy)
        self.logo.coords(self._fallback_text, cx, cy)
        self.logo.coords(self._word, cx, self._word_y + int(offset))
        self.logo.coords(self._rule, cx - px(18), self._rule_y + int(offset),
                         cx + px(18), self._rule_y + int(offset))

    def _logo_in(self):
        start = px(9)

        def frame(_eased, raw):
            # 字标从下往上轻轻落位；文字从幕布色淡入，图片本身直接出现。
            self._place_logo(int(round(start * (1.0 - ease_out_back(raw, 0.8)))))
            mix = min(1.0, raw * 3.4)
            self.logo.itemconfigure(
                self._word, fill=lerp_color(C_COVER_BG, C_COVER_TEXT, mix))
            self.logo.itemconfigure(
                self._rule, fill=lerp_color(C_COVER_BG, C_ACCENT, mix))

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

    # ------------------------------------------------------------------
    # 资源
    # ------------------------------------------------------------------
    def _load_logo(self):
        """读取 icon.png，并把深色圆角底去掉，只留 S/W 字标。

        直接把整块 icon 贴上来会看到一圈深色方块，和幕布底色对不上。
        这里按亮度把背景像素做成透明，字标边缘保留抗锯齿；这样 logo
        是“长在”幕布上的，没有拼接矩形。
        """
        try:
            from PIL import Image
            from PIL import ImageTk
            path = resource_path("icon.png")
            img = Image.open(path).convert("RGBA")
            cleaned = []
            for r, g, b, alpha in img.getdata():
                # 图标背景是深墨绿（最大通道约 68）；S/W 是白色/浅青，
                # 最大通道 > 100。窄窄一段过渡用来保留字形抗锯齿。
                strength = max(0.0, min(1.0, (max(r, g, b) - 84) / 32.0))
                cleaned.append((r, g, b, int(alpha * strength)))
            img.putdata(cleaned)
            # 只按“真正有字”的 alpha 取边界：背景里残留的极淡像素
            # 会把 bbox 撑回整块 512 方图，字标就会被缩得很小。
            solid = img.getchannel("A").point(lambda v: 255 if v > 18 else 0)
            box = solid.getbbox()
            if box:
                img = img.crop(box)
            width = self._logo_w
            ratio = width / max(1, img.width)
            img = img.resize(
                (width, max(1, int(round(img.height * ratio)))),
                Image.LANCZOS)
            self._logo_w, self._logo_h = img.size
            self._logo_photo = ImageTk.PhotoImage(img)
            self.logo.itemconfigure(self._logo_item, image=self._logo_photo)
            self._logo_image_ok = True
        except Exception:
            self._logo_image_ok = False

    def _swallow(self, _event=None):
        return "break"
