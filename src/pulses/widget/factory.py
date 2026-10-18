"""控件工厂与列表滚动条。"""
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
from .button import AnimatedButton

# ==================== 控件工厂 ====================
def make_button(parent, text, command=None, width=None, state="normal",
                accent=False, height=None, font_size=None):
    """统一按钮工厂：返回的按钮自带 hover / 按下的曲线过渡。

    iOS 那套按钮只有两种：
      · 主操作 = 实心强调色、无描边
      · 其余   = 强调色文字（tinted），没有边框、没有白底
    高度/字号只在需要强调的地方传，其余保持一致，尺寸才不会各行其是。
    """
    kwargs = dict(
        text=text, command=command,
        text_color=C_TEXT_INVERSE if accent else C_ACCENT,
        border_width=0, corner_radius=R_CONTROL,
        font=(config.FONT_FAMILY, font_size or FS_BODY),
        height=height or H_CONTROL, state=state)
    if width is not None:
        kwargs['width'] = width
    if accent:
        # 按下要更沉一档：之前 press_color 直接用了 hover 色，按下去看不出变化
        return AnimatedButton(parent, C_ACCENT, C_ACCENT_HOVER,
                               press_color=C_ACCENT_PRESSED, **kwargs)
    # 次级按钮：白底 + 强调色文字，hover 浮一层浅绿。
    # 用白底而不是 "transparent"，是因为补间要在两个色值之间插值。
    return AnimatedButton(parent, C_CARD_BG, C_ACCENT_SOFT,
                           press_color=lerp_color(C_ACCENT_SOFT, C_ACCENT, 0.25),
                           **kwargs)


def make_section_header(parent, index, title, subtitle=""):
    """段落标题：一条竖强调条 + 标题 +（可选）右侧说明。

    之前是「数字徽章 + 标题 + 渐隐细线」，三件套堆在一起很像模板。
    现在只留一根 3×14 的强调色竖条做落款，其余靠字重和留白分层。
    index 保留在签名里（调用方还在传），不参与绘制。
    """
    row = ctk.CTkFrame(parent, fg_color="transparent")
    # iOS 分组列表的表头：一行安静的小号灰字，不加装饰。
    label = make_label(row, text=title, fg=C_TEXT_SECONDARY,
                       font_size=FS_SMALL, bold=True)
    label.pack(side=LEFT)
    if subtitle:
        make_label(row, text=subtitle, fg=C_TEXT_MUTED,
                   font_size=FS_TINY).pack(side=RIGHT)
    return row


def make_menu_button(parent, text="⋯", items=None, width=30):
    """把次要操作收进一个「⋯」弹出菜单，别在主界面铺一排按钮。

    items 传**函数**而不是列表：菜单在每次点开时才求值，
    这样切换玩家/开发者身份后，菜单里的项能立刻跟着变。
    项为 (文字, 回调)，回调为 None 表示这一条当前不可用；None 表示分隔线。
    """
    button = ctk.CTkButton(
        parent, text=text, width=width, height=H_CONTROL - 6,
        fg_color="transparent", hover_color=C_PANEL_ALT_BG,
        text_color=C_TEXT_MUTED, corner_radius=R_CONTROL - 6,
        border_width=0, font=(config.FONT_FAMILY, FS_BODY))

    def popup():
        try:
            menu = Menu(button, tearoff=0, borderwidth=0, relief="flat",
                        bg=C_PANEL_BG, fg=C_TEXT_MAIN,
                        activebackground=C_ACCENT_SOFT,
                        activeforeground=C_TEXT_MAIN,
                        font=tk_font(config.FONT_FAMILY, FS_SMALL))
            entries = items() if callable(items) else (items or [])
            for entry in entries:
                if entry is None:
                    menu.add_separator()
                    continue
                label, command = entry
                if command is None:
                    menu.add_command(label=label, state="disabled")
                else:
                    menu.add_command(label=label, command=command)
            menu.tk_popup(button.winfo_rootx(),
                          button.winfo_rooty() + button.winfo_height() + 2)
            menu.grab_release()
        except Exception:
            pass
        return "break"

    button.configure(command=popup)
    return button


def make_text_button(parent, text, command=None, state="normal", color=None,
                     bold=False):
    """扁平文字按钮：无边框、无底色，hover 才浮出一层浅底。

    一行里放四五个带描边的白色小方块会非常吵；次要操作统一用这个。
    宽度自适应文字，适合密集的工具行。
    """
    return ctk.CTkButton(
        parent, text=text, command=command, width=1, height=H_CONTROL - 6,
        fg_color="transparent", hover_color=C_PANEL_ALT_BG,
        text_color=color or C_ACCENT, corner_radius=R_CONTROL - 6,
        border_width=0, state=state,
        font=(config.FONT_FAMILY, FS_SMALL, "bold" if bold else "normal"))


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
    entry = ctk.CTkEntry(parent, **kwargs)
    attach_entry_focus(entry)
    attach_entry_menu(entry)
    return entry


def attach_entry_focus(entry, base_color=None, accent_color=None):
    """输入框的"聚焦发光 + 填入时呼吸一下"。

    · 获得焦点：描边从发丝色弹到强调色（弹簧，末端轻微过冲）
    · 第一次填进内容：强调色呼吸一次再落定，给"填上了"一个正反馈
    · 失焦：弹回发丝色
    全部走补间，不改变布局，也不会和 CTk 自己的绘制打架。
    """
    base = base_color or C_BORDER_SOFT
    accent = accent_color or C_ACCENT
    # base 会被校验错误临时改成红色（见 FormField.error），失焦时回到这里记录的值
    state = {"color": base, "focus": False, "filled": False, "base": base}

    def _to(target, duration=200, easing=None):
        start = state["color"]
        if start == target:
            return

        def frame(e, _raw):
            state["color"] = lerp_color(start, target, e)
            try:
                entry.configure(border_color=state["color"])
            except Exception:
                pass

        frame(0.0, 0.0)
        tween(entry, "focus", duration, frame,
              easing=easing or ease_out_soft_spring, fps=FPS_COLOR)

    def _text() -> str:
        try:
            return str(entry.get() or "")
        except Exception:
            return ""

    def _pulse():
        _to(accent, 120, ease_out_cubic)

        def settle():
            _to(accent if state["focus"] else base, 280,
                ease_out_soft_spring)

        try:
            entry.after(130, settle)
        except Exception:
            settle()

    def _on_focus(_event=None):
        state["focus"] = True
        # 校验失败的红色不能被聚焦动画盖掉：聚焦事件是排队投递的，
        # 会在 error() 之后才到，所以这里要看 alert 标志
        _to(state["base"] if state.get("alert") else accent,
            200, ease_out_soft_spring)

    def _on_blur(_event=None):
        state["focus"] = False
        _to(state["base"], 220, ease_out_soft_spring)

    def _on_key(_event=None):
        text = _text()
        if not text:
            state["filled"] = False
            return
        if state["filled"]:
            return
        state["filled"] = True
        _pulse()

    for sequence, handler in (("<FocusIn>", _on_focus),
                              ("<FocusOut>", _on_blur),
                              ("<KeyRelease>", _on_key)):
        try:
            entry.bind(sequence, handler, add="+")
        except Exception:
            pass

    def set_base(color, respect_focus=True):
        """改「常态描边色」并立刻过渡过去（校验失败要变红，通过要变回来）。

        respect_focus=True 时，若当前有焦点就过渡到强调色 —— 否则会出现
        「正在输入却是灰色描边」的错位感。
        """
        state["base"] = color
        state["alert"] = not respect_focus
        _to(accent if (respect_focus and state["focus"]) else color,
            200, ease_out_soft_spring)

    entry._focus_ctl = {"set_base": set_base,
                        "focused": lambda: bool(state["focus"])}
    return entry


def attach_entry_menu(entry):
    """给输入框挂右键菜单（剪切 / 复制 / 粘贴 / 全选 / 清空）。

    Tk 的 Entry 在 Windows 上默认只有快捷键，右键什么都不出 —— 用户从浏览器
    复制分享链接过来时第一反应就是右键，没反应会以为界面卡住了。
    注意 CTkEntry.bind() 会把事件转发到内部真正的 tk.Entry，所以这里
    也要把菜单命令打到那个内部控件上。
    """
    inner = getattr(entry, "_entry", entry)
    try:
        menu = Menu(entry, tearoff=0, borderwidth=0, relief="flat",
                    bg=C_PANEL_BG, fg=C_TEXT_MAIN,
                    activebackground=C_ACCENT_SOFT, activeforeground=C_TEXT_MAIN,
                    font=tk_font(config.FONT_FAMILY, FS_SMALL))
    except Exception:
        return entry

    def run(action):
        try:
            inner.focus_set()
        except Exception:
            pass
        try:
            if action == "select":
                inner.selection_range(0, END)
                inner.icursor(END)
            elif action == "clear":
                inner.delete(0, END)
            else:
                inner.event_generate(f"<<{action}>>")
        except Exception:
            pass
        return "break"

    for label, action in (("剪切", "Cut"), ("复制", "Copy"), ("粘贴", "Paste"),
                          ("全选", "select"), ("清空", "clear")):
        try:
            menu.add_command(label=label, command=lambda a=action: run(a))
        except Exception:
            pass

    def popup(event):
        try:
            inner.focus_set()
            menu.tk_popup(event.x_root, event.y_root)
        except Exception:
            pass
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass
        return "break"

    for sequence in ("<Button-3>", "<Button-2>"):
        try:
            entry.bind(sequence, popup, add="+")
        except Exception:
            pass
    # Ctrl+A：部分 Tk 版本没绑，统一补上（返回 break 避免插入控制字符）
    try:
        entry.bind("<Control-a>", lambda e: run("select"), add="+")
        entry.bind("<Control-A>", lambda e: run("select"), add="+")
    except Exception:
        pass
    return entry


def make_checkbox(parent, text, variable, command=None, font_size=FS_SMALL):
    """统一样式的复选框。

    注意尺寸用**原始令牌**：CTk 控件自己会按 DPI 缩放，再套 px() 就是双重缩放
    （150% 下会变成 1.5 倍的 24px 方块，明显比文字大一圈）。
    """
    return ctk.CTkCheckBox(
        parent, text=text, variable=variable, command=command,
        text_color=C_TEXT_SECONDARY,
        font=(config.FONT_FAMILY, font_size),
        checkbox_width=18, checkbox_height=18, corner_radius=5,
        border_width=2, fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER,
        border_color=C_BORDER, checkmark_color=C_TEXT_INVERSE)


class FormField:
    """一行表单字段：标签 + 输入框 + 底部提示行。

    · 提示行**始终占位**（没有提示就放一个空格），出错时变红不会把下面的
      控件整体顶下去 —— 弹窗里跳一下很难看；
    · password=True 时自动加「显示 / 隐藏」，放在提示行右端，
      这样所有输入框宽度一致，不会因为多一个按钮而参差不齐；
    · 自带右键菜单与聚焦动效（make_entry 里已经挂好）。
    """

    def __init__(self, parent, label, placeholder="", textvariable=None,
                 hint="", password=False, width=None):
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.label = make_label(self.frame, text=label, fg=C_TEXT_SECONDARY,
                                font_size=FS_SMALL)
        self.label.pack(anchor=W)
        row = ctk.CTkFrame(self.frame, fg_color="transparent")
        row.pack(fill=X, pady=(PAD_MICRO, 0))
        self.entry = make_entry(row, textvariable=textvariable,
                                placeholder=placeholder, width=width)
        self.entry.pack(side=LEFT, fill=X, expand=True)

        # 提示行：左提示 + 右「显示密码」，始终占位，出错时不会顶动布局
        self._hint_default = hint
        self._wrap_last = -1
        self._toggle = None
        self._hint_row = ctk.CTkFrame(self.frame, fg_color="transparent")
        self._hint_row.pack(fill=X, pady=(PAD_MICRO, 0))
        self._hint = make_label(self._hint_row, text=hint or " ",
                                fg=C_TEXT_MUTED, font_size=FS_TINY)
        self._hint.pack(side=LEFT, fill=X, expand=True)
        self._shown = False          # False = 密码被打码（默认）
        self._has_error = False
        if password:
            self.entry.configure(show="●")
            self._toggle = ctk.CTkButton(
                self._hint_row, text="显示", width=36, height=16,
                fg_color="transparent", hover_color=C_PANEL_ALT_BG,
                text_color=C_TEXT_MUTED, corner_radius=4,
                font=(config.FONT_FAMILY, FS_TINY),
                command=self.toggle_password)
            self._toggle.pack(side=RIGHT)
        self._hint_row.bind("<Configure>", self._on_hint_resize, add="+")
        # 重新开始输入就把红色校验态撤掉，不用等下次提交
        try:
            self.entry.bind("<KeyRelease>", self._clear_error, add="+")
        except Exception:
            pass

    def _on_hint_resize(self, event=None):
        """提示行跟着宽度换行：长报错（接口返回的原文）不会被截掉。"""
        try:
            avail = int(getattr(event, "width", 0) or self._hint_row.winfo_width())
        except Exception:
            return
        width = max(80, avail - (44 if self._toggle is not None else 0) - 4)
        if abs(width - self._wrap_last) < 8:
            return
        self._wrap_last = width
        try:
            self._hint.configure(wraplength=width, justify=LEFT)
        except Exception:
            pass

    # ---------- 状态 ----------
    def toggle_password(self):
        self._shown = not self._shown
        try:
            self.entry.configure(show="" if self._shown else "●")
            self._toggle.configure(text="隐藏" if self._shown else "显示")
        except Exception:
            pass

    def hint(self, text="", color=None):
        """写提示行；text 为空时回到默认提示。"""
        try:
            self._hint.configure(text=(text or self._hint_default or " "),
                                 text_color=color or C_TEXT_MUTED)
        except Exception:
            pass

    def _paint(self, color, respect_focus=True):
        """走 attach_entry_focus 的补间改常态色，别和聚焦动画抢描边。"""
        ctl = getattr(self.entry, "_focus_ctl", None)
        if ctl is not None:
            try:
                ctl["set_base"](color, respect_focus)
                return
            except Exception:
                pass
        try:
            self.entry.configure(border_color=color)
        except Exception:
            pass

    def _clear_error(self, _event=None):
        if self._has_error and self.value():
            self.ok()

    def error(self, text):
        self._has_error = True
        self.hint(text, C_ERROR)
        self._paint(C_ERROR, respect_focus=False)

    def mark_error(self):
        """只把描边标红，不动提示行（后端报错时用）。"""
        self._has_error = True
        self._paint(C_ERROR, respect_focus=False)

    def ok(self):
        self._has_error = False
        self.hint("")
        self._paint(C_BORDER_SOFT)

    def focus(self):
        try:
            self.entry.focus_set()
        except Exception:
            pass

    def value(self) -> str:
        try:
            return str(self.entry.get() or "")
        except Exception:
            return ""

    def set_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        try:
            self.entry.configure(state=state)
        except Exception:
            pass


_MEASURE_FONTS = {}


def _measure_font(font_tuple):
    """按负数字号（像素）取一个可测量的 Font 对象，按元组缓存。"""
    key = tuple(font_tuple)
    cached = _MEASURE_FONTS.get(key)
    if cached is not None:
        return cached
    from tkinter import font as tkfont
    family = key[0]
    size = key[1] if len(key) > 1 else FS_BODY
    weight = key[2] if len(key) > 2 else "normal"
    try:
        created = tkfont.Font(family=family, size=size, weight=weight)
    except Exception:
        return None
    _MEASURE_FONTS[key] = created
    return created


def ellipsize(text, font_tuple, max_px) -> str:
    """把文字截到 max_px 以内，末尾加省略号。

    CTkLabel 不会自己省略：宽度不够时直接从字形中间切掉，看起来像渲染坏了。
    这里用同一套字体量一遍，二分找到最长的可放前缀。
    """
    text = str(text or "")
    if not text:
        return text
    if max_px <= 8:
        return ""
    font = _measure_font(font_tuple)
    if font is None:
        return text
    try:
        if font.measure(text) <= max_px:
            return text
        low, high = 0, len(text)
        while low < high:
            mid = (low + high + 1) // 2
            if font.measure(text[:mid] + "…") <= max_px:
                low = mid
            else:
                high = mid - 1
        return (text[:low] + "…") if low > 0 else "…"
    except Exception:
        return text


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


def open_url(url: str) -> bool:
    """用系统默认浏览器打开链接（登录/注册帮助用）。"""
    try:
        import webbrowser
        return bool(webbrowser.open(str(url)))
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
