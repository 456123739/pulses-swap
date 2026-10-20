"""自绘弹出菜单：替代 tk.Menu，和应用内的卡片同一套样式。

原生 tk.Menu 在 Windows 上是方角、灰边、系统字，和整个界面完全不是一套。
这里用 CTkFrame 画一张小卡片，放在主窗口的覆盖层宿主里，点外面或 ESC 收起。
"""
from __future__ import annotations

import customtkinter as ctk
from tkinter import END, W

from .. import config
from ..config import (C_ACCENT, C_ACCENT_SOFT, C_DIVIDER, C_PANEL_BG,
                      C_TEXT_MAIN, C_TEXT_MUTED, FS_SMALL, R_CONTROL)
from ..utils import px

ROW_H = 30
PAD = 6


class PopupMenu:
    """一次性弹出菜单；构造即显示，选择/点外/ESC 自动销毁。"""

    _open: "PopupMenu | None" = None

    def __init__(self, host, items, x_root: int, y_root: int, width: int = 150):
        PopupMenu.close_current()
        self.host = host
        # 调用方经常直接传按钮（make_menu_button）。CTkButton 没有 .root /
        # .overlay_host，之前这里抛 AttributeError 又被外层吞掉，表现为
        # “所有「更多/上传」下拉菜单点了没反应”。统一从 Tk 顶层窗口取 root。
        try:
            self.root = host.winfo_toplevel()
        except Exception:
            self.root = getattr(host, "root", None)
        if self.root is None:
            return
        self._closed = False

        holder = getattr(host, "overlay_host", None) or self.root
        # 宽度必须在构造时给：CTk 控件不允许在 place() 里传 width/height
        self.panel = ctk.CTkFrame(holder, fg_color=C_PANEL_BG,
                                   corner_radius=R_CONTROL,
                                   border_width=1, border_color=C_DIVIDER,
                                   width=width)
        body = ctk.CTkFrame(self.panel, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=PAD, pady=PAD)

        height = PAD * 2
        for item in items:
            if item is None:
                line = ctk.CTkFrame(body, fg_color=C_DIVIDER, height=1)
                line.pack(fill="x", pady=4)
                height += 9
                continue
            label, command = item[0], item[1]
            enabled = command is not None
            row = ctk.CTkButton(
                body, text=label, anchor="w", width=width - PAD * 2,
                height=ROW_H, corner_radius=6, border_width=0,
                fg_color="transparent",
                # CTk 不接受 "transparent" 作为 hover_color，禁用项用底色代替
                hover_color=C_ACCENT_SOFT if enabled else C_PANEL_BG,
                text_color=C_TEXT_MAIN if enabled else C_TEXT_MUTED,
                font=(config.FONT_FAMILY, FS_SMALL,
                      "normal" if enabled else "normal"),
                command=(lambda c=command: self._pick(c)))
            row.pack(fill="x")
            if not enabled:
                row.configure(state="disabled")
            height += ROW_H

        # 贴到鼠标位置，并夹在窗口内
        try:
            hx = holder.winfo_rootx()
            hy = holder.winfo_rooty()
            hw, hh = holder.winfo_width(), holder.winfo_height()
            x = max(0, min(int(x_root) - hx, hw - width - 4))
            y = max(0, min(int(y_root) - hy, hh - height - 4))
        except Exception:
            x = y = 0
        self.panel.place(x=x, y=y)
        self.panel.lift()

        self._bind_id = self.root.bind("<Button-1>", self._on_click_outside,
                                        add="+")
        self._esc_id = self.root.bind("<Escape>", self._on_escape, add="+")
        PopupMenu._open = self

    # ---------- 关闭 ----------
    def _pick(self, command):
        self.close()
        try:
            command()
        except Exception:
            pass

    def _on_click_outside(self, event=None):
        # 点在菜单内部时不能关：root 的 <Button-1> 绑定会先于按钮的
        # <ButtonRelease> 触发，直接 close 会让所有菜单项都点不中。
        widget = getattr(event, "widget", None)
        while widget is not None:
            if widget is self.panel:
                return
            widget = getattr(widget, "master", None)
        self.close()

    def _on_escape(self, _event=None):
        self.close()
        return "break"

    def close(self):
        if self._closed:
            return
        self._closed = True
        for funcid in (getattr(self, "_bind_id", None),
                       getattr(self, "_esc_id", None)):
            if funcid:
                try:
                    self.root.unbind("<Button-1>", funcid)
                except Exception:
                    pass
                try:
                    self.root.unbind("<Escape>", funcid)
                except Exception:
                    pass
        try:
            self.panel.destroy()
        except Exception:
            pass
        if PopupMenu._open is self:
            PopupMenu._open = None

    @classmethod
    def close_current(cls):
        if cls._open is not None:
            cls._open.close()


def popup_menu(host, items, x_root=None, y_root=None, width: int = 150):
    """在鼠标位置弹一个自绘菜单。items: [(文字, 回调) | None]。"""
    try:
        if x_root is None or y_root is None:
            x_root, y_root = host.root.winfo_pointerxy()
        return PopupMenu(host, items, int(x_root), int(y_root), width=width)
    except Exception:
        return None
