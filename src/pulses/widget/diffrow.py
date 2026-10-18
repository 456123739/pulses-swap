"""
差异清单控件：同步框 / 发布框里逐项勾选的列表。

一行 = 复选框 + 动作色点 + 名字 + 动作标签 + 体积。
点击整行也能切换勾选，勾选状态变化时行底色做轻微过渡。
"""
from __future__ import annotations

import customtkinter as ctk

from .. import config
from ..animation import (ease_out_cubic, ease_out_soft_spring, lerp_color,
                         tween)
from ..config import (C_ACCENT, C_ACCENT_SOFT, C_BORDER_SOFT, C_CARD_BG,
                      C_ERROR, C_INFO, C_PANEL_ALT_BG, C_SUCCESS,
                      C_TEXT_MAIN, C_TEXT_MUTED, C_TEXT_SECONDARY, C_WARNING,
                      FS_SMALL, FS_TINY, R_CONTROL)
from ..utils import px
from .button import AnimatedButton
from .cards import ScrollArea

H_ROW = 34

# 动作 → (颜色, 标签)
ACTION_STYLE = {
    "download": (C_INFO, "下载"),
    "repair": (C_INFO, "修复"),
    "upload": (C_ACCENT, "上传"),
    "skip": (C_TEXT_MUTED, "一致"),
    "delete_cloud": (C_ERROR, "删除云端"),
    "delete_local": (C_ERROR, "删除本地"),
    "ask_delete_local": (C_WARNING, "本地多余"),
    "blocked": (C_ERROR, "无法处理"),
}


def format_bytes(num) -> str:
    try:
        value = float(num or 0)
    except (TypeError, ValueError):
        return "0 B"
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


class DiffRow(ctk.CTkFrame):
    """一条差异。"""

    def __init__(self, parent, item, *, on_toggle=None):
        super().__init__(parent, fg_color=C_CARD_BG, corner_radius=R_CONTROL,
                         border_width=0, height=H_ROW)
        self.pack_propagate(False)
        self.item = item
        self._on_toggle = on_toggle
        self._checked = bool(item.default_checked)
        self._enabled = item.action not in ("skip", "blocked")

        color, label = ACTION_STYLE.get(item.action,
                                        (C_TEXT_MUTED, item.action))

        self.var = ctk.BooleanVar(master=self, value=self._checked)
        self.check = ctk.CTkCheckBox(
            self, text="", width=18, height=18,
            checkbox_width=16, checkbox_height=16,
            corner_radius=4, border_width=2,
            fg_color=C_ACCENT, hover_color=C_ACCENT,
            border_color=C_BORDER_SOFT,
            checkmark_color="#FFFFFF",
            variable=self.var, command=self._on_check)
        self.check.pack(side="left", padx=(8, 6))
        if not self._enabled:
            self.check.configure(state="disabled")

        self.dot = ctk.CTkLabel(self, text="●", text_color=color,
                                font=(config.FONT_FAMILY, FS_TINY),
                                width=12)
        self.dot.pack(side="left")

        self.name_label = ctk.CTkLabel(
            self, text=item.display_name, anchor="w",
            text_color=C_TEXT_MAIN if self._enabled else C_TEXT_MUTED,
            font=(config.FONT_FAMILY, FS_SMALL))
        self.name_label.pack(side="left", fill="x", expand=True, padx=(4, 0))

        self.tag = ctk.CTkLabel(
            self, text=label, text_color=color,
            font=(config.FONT_FAMILY, FS_TINY), width=56, anchor="e")
        self.tag.pack(side="left", padx=(4, 4))

        self.size_label = ctk.CTkLabel(
            self, text=format_bytes(item.size) if item.size else "",
            text_color=C_TEXT_MUTED, font=(config.FONT_FAMILY, FS_TINY),
            width=64, anchor="e")
        self.size_label.pack(side="left", padx=(0, 8))

        for widget in (self, self.name_label, self.dot, self.tag,
                       self.size_label):
            try:
                widget.bind("<Button-1>", self._toggle_click, add="+")
                widget.bind("<Enter>", self._hover_on, add="+")
                widget.bind("<Leave>", self._hover_off, add="+")
            except Exception:
                pass
        self._hovering = False
        self._paint()

    # ---------- 交互 ----------
    def _on_check(self):
        self._checked = bool(self.var.get())
        self._paint()
        if self._on_toggle is not None:
            self._on_toggle(self.item, self._checked)

    def _hover_on(self, _event=None):
        if not self._enabled or self._checked:
            return
        self._hovering = True
        self._paint()

    def _hover_off(self, _event=None):
        self._hovering = False
        self._paint()

    def _toggle_click(self, _event=None):
        if not self._enabled:
            return
        self.var.set(not self.var.get())
        self._on_check()

    def _paint(self):
        if self._checked:
            target = C_ACCENT_SOFT
        elif getattr(self, "_hovering", False) and self._enabled:
            target = C_PANEL_ALT_BG
        else:
            target = C_CARD_BG
        current = self.cget("fg_color")
        if current == target:
            return

        def frame(e, _raw):
            try:
                self.configure(fg_color=lerp_color(current, target, e))
            except Exception:
                pass

        frame(0.0, 0.0)
        tween(self, "row", 170, frame, easing=ease_out_soft_spring)

    # ---------- 状态 ----------
    @property
    def checked(self) -> bool:
        return self._checked

    def set_checked(self, value: bool) -> None:
        if not self._enabled:
            return
        self.var.set(bool(value))
        self._checked = bool(value)
        self._paint()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled) and self.item.action not in ("skip",
                                                                   "blocked")
        try:
            self.check.configure(state="normal" if self._enabled else "disabled")
            self.name_label.configure(
                text_color=C_TEXT_MAIN if self._enabled else C_TEXT_MUTED)
        except Exception:
            pass


class InfoRow(ctk.CTkFrame):
    """只读信息行：名字 + 标签 + 体积（详情页的枪包列表用）。"""

    def __init__(self, parent, name, *, tag="", color=None, size=0,
                 subtitle=""):
        super().__init__(parent, fg_color=C_CARD_BG, corner_radius=R_CONTROL,
                         border_width=0, height=H_ROW)
        self.pack_propagate(False)
        text_box = ctk.CTkFrame(self, fg_color="transparent")
        text_box.pack(side="left", fill="x", expand=True, padx=(10, 0))
        self.name_label = ctk.CTkLabel(
            text_box, text=name, anchor="w", text_color=C_TEXT_MAIN,
            font=(config.FONT_FAMILY, FS_SMALL))
        self.name_label.pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(text_box, text=subtitle, anchor="w",
                         text_color=C_TEXT_MUTED,
                         font=(config.FONT_FAMILY, FS_TINY)).pack(anchor="w")
        self.tag = ctk.CTkLabel(
            self, text=tag or "", text_color=color or C_TEXT_MUTED,
            font=(config.FONT_FAMILY, FS_TINY), width=56, anchor="e")
        self.tag.pack(side="left", padx=(4, 4))
        self.size_label = ctk.CTkLabel(
            self, text=format_bytes(size) if size else "",
            text_color=C_TEXT_MUTED, font=(config.FONT_FAMILY, FS_TINY),
            width=64, anchor="e")
        self.size_label.pack(side="left", padx=(0, 10))
        self._hover = C_CARD_BG
        for widget in (self, self.name_label, self.tag, self.size_label):
            try:
                widget.bind("<Enter>", self._on_enter, add="+")
                widget.bind("<Leave>", self._on_leave, add="+")
            except Exception:
                pass

    def _tint(self, target):
        start = self._hover
        if start == target:
            return
        self._hover = target

        def frame(e, _raw):
            try:
                self.configure(fg_color=lerp_color(start, target, e))
            except Exception:
                pass

        tween(self, "hover", 140, frame, easing=ease_out_cubic)

    def _on_enter(self, _event=None):
        self._tint(C_PANEL_ALT_BG)

    def _on_leave(self, _event=None):
        self._tint(C_CARD_BG)


class InfoList(ctk.CTkFrame):
    """只读列表（可滚动）。"""

    def __init__(self, parent, *, height=220, empty_text="没有内容"):
        super().__init__(parent, fg_color=C_CARD_BG, corner_radius=R_CONTROL,
                         border_width=1, border_color=C_BORDER_SOFT,
                         height=height)
        self.pack_propagate(False)
        self.area = ScrollArea(self, bg=C_CARD_BG)
        self.area.pack(fill="both", expand=True, padx=2, pady=4)
        self.empty = ctk.CTkLabel(self.area.inner, text=empty_text,
                                  text_color=C_TEXT_MUTED,
                                  font=(config.FONT_FAMILY, FS_SMALL))
        self._rows: list[ctk.CTkFrame] = []

    def set_rows(self, rows: list[dict]) -> None:
        for row in self._rows:
            try:
                row.destroy()
            except Exception:
                pass
        self._rows = []
        if not rows:
            self.empty.pack(pady=20)
            return
        self.empty.pack_forget()
        for spec in rows:
            row = InfoRow(self.area.inner, spec.get("name", ""),
                          tag=spec.get("tag", ""),
                          color=spec.get("color"),
                          size=spec.get("size", 0),
                          subtitle=spec.get("subtitle", ""))
            row.pack(fill="x", pady=(0, 2), padx=2)
            self._rows.append(row)


class DiffList(ctk.CTkFrame):
    """差异清单：可滚动 + 全选/全不选 + 统计行。"""

    def __init__(self, parent, *, height=260, on_change=None):
        super().__init__(parent, fg_color=C_CARD_BG, corner_radius=R_CONTROL,
                         border_width=1, border_color=C_BORDER_SOFT,
                         height=height)
        self.pack_propagate(False)
        self._on_change = on_change
        self._rows: list[DiffRow] = []

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=8, pady=(6, 0))
        self.summary = ctk.CTkLabel(
            head, text="", anchor="w", text_color=C_TEXT_SECONDARY,
            font=(config.FONT_FAMILY, FS_TINY))
        self.summary.pack(side="left")
        AnimatedButton(head, C_PANEL_ALT_BG, C_ACCENT_SOFT,
                       press_color=lerp_color(C_ACCENT_SOFT, C_ACCENT, 0.45),
                       text="全选", width=48, height=22,
                       corner_radius=R_CONTROL, border_width=0,
                       text_color=C_TEXT_SECONDARY,
                       font=(config.FONT_FAMILY, FS_TINY),
                       command=lambda: self.set_all(True)).pack(side="right")
        AnimatedButton(head, C_PANEL_ALT_BG, C_ACCENT_SOFT,
                       press_color=lerp_color(C_ACCENT_SOFT, C_ACCENT, 0.45),
                       text="全不选", width=56, height=22,
                       corner_radius=R_CONTROL, border_width=0,
                       text_color=C_TEXT_SECONDARY,
                       font=(config.FONT_FAMILY, FS_TINY),
                       command=lambda: self.set_all(False)).pack(
                           side="right", padx=(0, 4))

        self.area = ScrollArea(self, bg=C_CARD_BG)
        self.area.pack(fill="both", expand=True, padx=2, pady=(2, 4))
        self.empty = ctk.CTkLabel(
            self.area.inner, text="没有差异", text_color=C_TEXT_MUTED,
            font=(config.FONT_FAMILY, FS_SMALL))

    # ---------- 数据 ----------
    def set_items(self, items) -> None:
        for row in self._rows:
            try:
                row.destroy()
            except Exception:
                pass
        self._rows = []
        if not items:
            self.empty.pack(pady=20)
            self._refresh_summary()
            return
        self.empty.pack_forget()
        for item in items:
            row = DiffRow(self.area.inner, item, on_toggle=self._toggled)
            row.pack(fill="x", pady=(0, 2), padx=2)
            self._rows.append(row)
        self._refresh_summary()

    def _toggled(self, _item, _checked):
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        checked = [r for r in self._rows if r.checked]
        total = sum(r.item.size for r in checked)
        counts = {}
        for row in self._rows:
            counts[row.item.action] = counts.get(row.item.action, 0) + 1
        bits = []
        for action, label in (("download", "下载"), ("repair", "修复"),
                              ("upload", "上传"),
                              ("ask_delete_local", "本地多余"),
                              ("delete_cloud", "云端多余"),
                              ("skip", "一致"), ("blocked", "无法处理")):
            if counts.get(action):
                bits.append(f"{label} {counts[action]}")
        head = " · ".join(bits) or "没有差异"
        if checked:
            head += f"　|　已选 {len(checked)} 项，{format_bytes(total)}"
        self.summary.configure(text=head)
        if self._on_change is not None:
            self._on_change(self.selection())

    # ---------- 选择 ----------
    def set_all(self, value: bool) -> None:
        for row in self._rows:
            row.set_checked(value)
        self._refresh_summary()

    def selection(self) -> set[str]:
        return {row.item.path for row in self._rows if row.checked}

    def set_enabled(self, enabled: bool) -> None:
        for row in self._rows:
            row.set_enabled(enabled)
