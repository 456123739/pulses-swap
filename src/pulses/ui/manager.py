"""管理页：云端文件树 / 上传下拉 / 新建文件夹 / 本地枪包 / 完整日志。

这一页只在「管理」导航项下出现，不抢主界面的操作路径；但它必须能在
没有加载整合包时独立工作（开发者先登录、先管云端）。
"""
from __future__ import annotations

import os
import threading
import time
import traceback
from pathlib import Path
from tkinter import *
from tkinter import filedialog

import customtkinter as ctk

from ..config import *
from ..utils import *
from ..animation import *
from ..widget import *
from ..dialogs import *
from ..dialogs import _OVERLAY_STACK
from ..managers import *

try:
    from online.errors import CancelledError as OnlineCancelled
    from online.errors import OnlineError
except Exception:                    # pragma: no cover
    OnlineError = Exception
    OnlineCancelled = Exception


def _cloud_path_join(parent: str, name: str) -> str:
    parent = str(parent or "").replace("\\", "/").strip("/")
    name = str(name or "").strip("/")
    return ("/" + parent + "/" + name) if parent else ("/" + name)


class CloudBrowser(ctk.CTkFrame):
    """懒加载的云端文件树。

    只展开用户点开的文件夹，不递归拉整棵树（大网盘递归会非常慢）。
    所有网络请求都在工作线程，回到主线程只做一次重绘。
    """

    ROW_H = 27

    def __init__(self, parent, app, on_path=None):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.on_path = on_path
        self._service = None
        self._root_path = "/"
        self._current = "/"
        self._expanded: set[str] = set()
        self._cache: dict[str, dict] = {}
        self._loading: set[str] = set()
        self._error: dict[str, str] = {}
        self._render_token = 0
        self._enabled = False
        self._disabled_hint = "登录开发者账号后可浏览云端文件"

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill=X)
        self.path_label = make_label(head, text="/", fg=C_TEXT_MAIN,
                                      font_size=FS_SMALL, bold=True)
        self.path_label.pack(side=LEFT, fill=X, expand=True)
        make_text_button(head, "刷新", command=self.reload).pack(side=RIGHT)
        make_text_button(head, "上一级", command=self.up).pack(
            side=RIGHT, padx=(0, PAD_TIGHT))

        self.status = make_label(self, text="", fg=C_TEXT_MUTED,
                                  font_size=FS_TINY)
        self.status.pack(anchor=W, pady=(PAD_MICRO, PAD_TIGHT))

        self.tree = ctk.CTkScrollableFrame(
            self, fg_color=C_CARD_BG, corner_radius=R_CONTROL,
            scrollbar_button_color=C_BORDER_SOFT,
            scrollbar_button_hover_color=C_BORDER)
        self.tree.pack(fill=BOTH, expand=True)

    # ---------- 对外 ----------
    def set_service(self, service):
        self._service = service

    def has_data(self):
        return bool(self._cache)

    def set_enabled(self, enabled, hint=""):
        self._enabled = bool(enabled)
        if hint:
            self._disabled_hint = hint
        if not self._enabled:
            self._cache.clear()
            self._expanded.clear()
            self._error.clear()
        self._render()

    def path(self):
        return self._current or self._root_path or "/"

    def set_path(self, path):
        clean = self._normalize(path)
        self._root_path = clean
        self._current = clean
        self._expanded = {clean}
        self._cache.clear()
        self._error.clear()
        self._render()
        if self._enabled:
            self._fetch(clean)

    def reload(self):
        path = self._current or self._root_path
        self._cache.clear()
        self._error.clear()
        self._expanded.add(path)
        self._render()
        if self._enabled:
            self._fetch(path, force=True)

    def up(self):
        path = self.path()
        if path in ("", "/"):
            return
        parent = "/" + "/".join([p for p in path.split("/") if p][:-1])
        self.set_path(parent)

    # ---------- 数据 ----------
    @staticmethod
    def _normalize(path):
        parts = [p for p in str(path or "").replace("\\", "/").split("/") if p]
        return "/" + "/".join(parts) if parts else "/"

    def _fetch(self, path, force=False):
        if not self._enabled:
            return
        service = self._service or getattr(self.app, "online", None)
        if service is None:
            self._error[path] = "在线模块未启用"
            self._render()
            return
        if path in self._loading:
            return
        if not force and path in self._cache:
            return
        self._loading.add(path)
        self._render()

        def worker():
            try:
                data = service.cloud_browse(path)
                ui_call(self.app.root, self._on_data, path, data, None)
            except Exception as exc:                # noqa: BLE001
                ui_call(self.app.root, self._on_data, path, None, exc)

        threading.Thread(target=worker, daemon=True).start()

    def _on_data(self, path, data, error):
        self._loading.discard(path)
        if error is not None:
            self._error[path] = str(error)
            if path == self._current:
                self.status.configure(text=f"读取失败：{error}",
                                      text_color=C_ERROR)
                self.app.set_status(f"云端读取失败：{error}", "error")
        else:
            self._cache[path] = data
            self._error.pop(path, None)
            if path == self._current:
                self.status.configure(
                    text=f"{len(data.get('folders') or [])} 个文件夹 · "
                         f"{len(data.get('files') or [])} 个文件",
                    text_color=C_TEXT_MUTED)
                self.app.set_status(
                    f"云端已连接 · {self._normalize(path)} · "
                    f"{len(data.get('files') or [])} 个文件", "success")
        try:
            if path == "/":
                self.app._update_manage_summary()
        except Exception:
            pass
        self._render()

    # ---------- 渲染 ----------
    def _render(self):
        for child in list(self.tree.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass
        path = self._current
        self.path_label.configure(text=path)
        if self.on_path is not None:
            try:
                self.on_path(path)
            except Exception:
                pass
        if not self._enabled:
            self.status.configure(text=self._disabled_hint,
                                  text_color=C_TEXT_MUTED)
            self._add_hint(self._disabled_hint)
            return
        if path != "/":
            self._add_nav_row("返回上一级", lambda: self.up())
        node = self._cache.get(path)
        if path in self._loading and node is None:
            self._add_hint("正在读取云端…")
            return
        if path in self._error and node is None:
            self._add_hint(f"读取失败：{self._error[path]}")
            return
        if node is None:
            self._add_hint("等待读取…")
            return
        folders = node.get("folders") or []
        files = node.get("files") or []
        if not folders and not files:
            self._add_hint("这个文件夹是空的")
            return
        for folder in folders:
            child_path = _cloud_path_join(path, folder.get("name") or "")
            self._add_folder_row(path, child_path, str(folder.get("name") or ""),
                                 depth=0)
        for item in files:
            self._add_file_row(path, str(item.get("name") or ""),
                               str(item.get("size") or ""), depth=0,
                               file_id=item.get("id"))

    def _add_hint(self, text):
        make_label(self.tree, text=text, fg=C_TEXT_MUTED,
                   font_size=FS_TINY).pack(anchor=W, padx=PAD_GAP,
                                            pady=PAD_GAP)

    def _add_nav_row(self, text, command):
        row = ctk.CTkButton(
            self.tree, text=text, anchor="w", height=self.ROW_H,
            fg_color="transparent", hover_color=C_PANEL_ALT_BG,
            text_color=C_ACCENT, corner_radius=6, border_width=0,
            font=(FONT_FAMILY, FS_SMALL, "bold"), command=command)
        row.pack(fill=X, pady=1, padx=2)

    def _add_folder_row(self, parent_path, path, name, depth, file_id=None):
        expanded = path in self._expanded
        row = ctk.CTkFrame(self.tree, fg_color=("transparent"
                                                 if path != self._current
                                                 else C_ACCENT_SOFT),
                           height=self.ROW_H)
        row.pack(fill=X, pady=1, padx=2)
        row.pack_propagate(False)
        if depth:
            ctk.CTkFrame(row, fg_color="transparent",
                         width=depth * px(14)).pack(side=LEFT)
        toggle = make_text_button(
            row, "▾" if expanded else "▸",
            command=lambda p=path: self._toggle(p))
        toggle.configure(width=px(18), height=self.ROW_H - 2)
        toggle.pack(side=LEFT)
        btn = ctk.CTkButton(
            row, text=name, anchor="w", height=self.ROW_H - 2,
            fg_color="transparent", hover_color=C_ACCENT_SOFT,
            text_color=C_TEXT_MAIN, corner_radius=6, border_width=0,
            font=(FONT_FAMILY, FS_SMALL),
            command=lambda p=path: self._select_folder(p))
        btn.pack(side=LEFT, fill=X, expand=True)
        make_label(row, text="文件夹", fg=C_TEXT_MUTED,
                   font_size=FS_TINY).pack(side=RIGHT, padx=(PAD_TIGHT,
                                                             PAD_TIGHT))
        if not expanded:
            return
        data = self._cache.get(path)
        if path in self._loading and data is None:
            self._add_hint_indented("正在读取…", depth + 1)
            return
        if data is None and path not in self._error:
            self._fetch(path)
            self._add_hint_indented("正在读取…", depth + 1)
            return
        if path in self._error and data is None:
            self._add_hint_indented(f"读取失败：{self._error[path]}", depth + 1)
            return
        if data is None:
            return
        folders = data.get("folders") or []
        files = data.get("files") or []
        if not folders and not files:
            self._add_hint_indented("空文件夹", depth + 1)
        for child in folders:
            child_path = _cloud_path_join(path, child.get("name") or "")
            self._add_folder_row(path, child_path,
                                 str(child.get("name") or ""), depth + 1)
        for item in files:
            self._add_file_row(path, str(item.get("name") or ""),
                               str(item.get("size") or ""), depth + 1,
                               file_id=item.get("id"))

    def _add_hint_indented(self, text, depth):
        frame = ctk.CTkFrame(self.tree, fg_color="transparent",
                             height=self.ROW_H)
        frame.pack(fill=X, pady=1, padx=2)
        ctk.CTkFrame(frame, fg_color="transparent",
                     width=depth * px(14)).pack(side=LEFT)
        make_label(frame, text=text, fg=C_TEXT_MUTED,
                   font_size=FS_TINY).pack(side=LEFT, padx=PAD_XS)

    def _add_file_row(self, parent_path, name, size, depth, file_id=None):
        row = ctk.CTkFrame(self.tree, fg_color="transparent",
                           height=self.ROW_H)
        row.pack(fill=X, pady=1, padx=2)
        row.pack_propagate(False)
        if depth:
            ctk.CTkFrame(row, fg_color="transparent",
                         width=depth * px(14) + px(18)).pack(side=LEFT)
        make_label(row, text=name, fg=C_TEXT_SECONDARY,
                   font_size=FS_SMALL).pack(side=LEFT, fill=X, expand=True,
                                            padx=(PAD_XS, 0))
        if size:
            make_label(row, text=size, fg=C_TEXT_MUTED,
                       font_size=FS_TINY).pack(side=RIGHT, padx=PAD_TIGHT)

    def _select_folder(self, path):
        self._current = path
        self._expanded.add(path)
        self._render()
        if path not in self._cache:
            self._fetch(path)
        self.app.set_status(f"云端文件夹：{path}", "info")

    def _toggle(self, path):
        if path in self._expanded:
            self._expanded.discard(path)
        else:
            self._expanded.add(path)
            if path not in self._cache:
                self._fetch(path)
        self._current = path
        self._render()


class ManagePresetList(ctk.CTkFrame):
    """管理页的全局预设总览：一行一个预设，直接给动作。"""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.area = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=C_BORDER_SOFT,
            scrollbar_button_hover_color=C_BORDER)
        self.area.pack(fill=BOTH, expand=True)
        self._rows = []
        self.empty_box = ctk.CTkFrame(self, fg_color="transparent")
        self.empty_title = make_label(
            self.empty_box, text="还没有可管理的预设", fg=C_TEXT_SECONDARY,
            font_size=FS_SMALL, bold=True)
        self.empty_title.pack(anchor="center")
        self.empty_hint = make_label(
            self.empty_box, text="", fg=C_TEXT_MUTED, font_size=FS_TINY,
            justify="center")
        self.empty_hint.pack(anchor="center", pady=(PAD_MICRO, PAD_TIGHT))
        self.empty_btn = make_button(
            self.empty_box, "去主界面", command=self._empty_action,
            accent=True, height=30, width=104, font_size=FS_SMALL)
        self.empty_btn.pack(anchor="center")

    def _empty_action(self):
        if getattr(self.app, "is_developer", False) and not getattr(
                self.app, "preset_manager", None):
            try:
                self.app.show_page("manage")
                self.app._manage_show_tab("files")
            except Exception:
                pass
            return
        if not getattr(self.app, "is_developer", False) and not getattr(
                self.app, "preset_manager", None):
            try:
                self.app.show_page("home")
            except Exception:
                pass
            return
        try:
            self.app.show_page("home")
        except Exception:
            pass

    def set_rows(self, rows, empty_text="还没有预设"):
        for row in self._rows:
            try:
                row.destroy()
            except Exception:
                pass
        self._rows = []
        if not rows:
            dev = bool(getattr(self.app, "is_developer", False))
            no_pack = not getattr(self.app, "preset_manager", None)
            if dev and no_pack:
                hint = "先加载整合包；也可以直接在「云端文件」里上传"
                label = "去云端文件"
            elif (not dev) and no_pack:
                hint = "先加载整合包，之后才能从云端添加"
                label = "去加载整合包"
            else:
                hint = empty_text
                label = "去主界面"
            try:
                self.empty_hint.configure(text=hint)
                self.empty_btn.configure(text=label)
                self.empty_box.place(relx=0.5, rely=0.42, anchor="center")
            except Exception:
                pass
            return
        try:
            self.empty_box.place_forget()
        except Exception:
            pass
        for spec in rows:
            name = str(spec.get("name") or "")
            row = ctk.CTkFrame(self.area, fg_color=C_CARD_BG,
                               corner_radius=R_CONTROL, border_width=1,
                               border_color=C_DIVIDER)
            row.pack(fill=X, pady=(0, PAD_MICRO), padx=0)
            left = ctk.CTkFrame(row, fg_color="transparent")
            left.pack(side=LEFT, fill=X, expand=True, padx=PAD_GAP,
                      pady=PAD_TIGHT)
            title = name + ("  · 已应用" if spec.get("applied") else "")
            make_label(left, text=title, fg=C_TEXT_MAIN,
                       font_size=FS_SMALL, bold=True).pack(anchor=W)
            meta = " · ".join(str(x) for x in (
                spec.get("version") or "", spec.get("meta") or "",
                spec.get("path") or "") if x)
            make_label(left, text=meta or "—", fg=C_TEXT_MUTED,
                       font_size=FS_TINY).pack(anchor=W, pady=(1, 0))
            status = str(spec.get("status") or "")
            if status:
                make_label(left, text=status,
                           fg=spec.get("color") or C_TEXT_MUTED,
                           font_size=FS_TINY).pack(anchor=W, pady=(1, 0))
            action = str(spec.get("action") or "详情")
            btn = make_text_button(
                row, action,
                command=lambda n=name, k=spec.get("kind") or "detail":
                self.app._manage_preset_action(n, k))
            btn.pack(side=RIGHT, padx=(0, PAD_GAP))
            for widget in (row, left) + tuple(left.winfo_children()):
                try:
                    widget.bind(
                        "<Button-1>",
                        lambda e, n=name: self.app._manage_select(n),
                        add="+")
                except Exception:
                    pass
            self._rows.append(row)


class ManagerPageMixin:
    """管理页装配 / 云端上传 / 角色隔离。"""

    # ==================================================================
    # 页面
    # ==================================================================
    def _build_manage_page(self):
        page = ctk.CTkFrame(self.stack.canvas, fg_color=C_WINDOW_BG)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=0)
        page.grid_rowconfigure(1, weight=1)

        # ===== 顶部：标题 + 三个总览数字 =====
        head = ctk.CTkFrame(page, fg_color=C_CARD_BG, corner_radius=R_CARD,
                            border_width=BORDER_W,
                            border_color=C_BORDER_SOFT)
        head.grid(row=0, column=0, sticky="ew", pady=(0, PAD_GAP))
        title_row = ctk.CTkFrame(head, fg_color="transparent")
        title_row.pack(fill=X, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        make_label(title_row, text="管理", fg=C_TEXT_MAIN,
                   font_size=FS_TITLE, bold=True).pack(side=LEFT)
        make_label(title_row, text="全局预设操作", fg=C_TEXT_MUTED,
                   font_size=FS_TINY).pack(side=LEFT, padx=(PAD_GAP, 0))
        self.manage_role_label = make_label(
            title_row, text="玩家", fg=C_TEXT_SECONDARY, font_size=FS_SMALL,
            bold=True)
        self.manage_role_label.pack(side=LEFT, padx=(PAD_GAP, 0))
        self.manage_account_label = make_label(
            title_row, text="未登录", fg=C_TEXT_MUTED, font_size=FS_TINY)
        self.manage_account_label.pack(side=RIGHT)

        summary = ctk.CTkFrame(head, fg_color="transparent")
        summary.pack(fill=X, padx=PAD_CARD_X, pady=(0, PAD_CARD_Y))
        self.manage_stat_local = self._manage_stat(
            summary, "本地预设", "0")
        self.manage_stat_cloud = self._manage_stat(
            summary, "云端预设", "0")
        self.manage_stat_pending = self._manage_stat(
            summary, "待处理", "0")

        # ===== 主体：左侧总览/云端文件，右侧快捷操作 + 日志 =====
        body = ctk.CTkFrame(page, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew")
        self.manage_body = body
        body.grid_columnconfigure(0, weight=3, minsize=px(560))
        body.grid_columnconfigure(1, weight=2, minsize=px(380))
        body.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(body, fg_color=C_CARD_BG,
                             corner_radius=R_CARD, border_width=0)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, PAD_GAP))
        self.manage_left = left
        self.manage_cloud_card = left
        left_head = ctk.CTkFrame(left, fg_color="transparent")
        left_head.pack(fill=X, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        make_section_header(left_head, 1, "预设总览").pack(side=LEFT)
        self.manage_tab_bar = CanvasSegmented(
            left_head, [("overview", "总览"), ("files", "云端文件")],
            command=self._manage_show_tab, orientation="horizontal",
            item_height=26, pad=3, gap=3, radius=R_CONTROL,
            bg_color=C_CARD_BG, pill_color=C_ACCENT, hover_color=C_ACCENT_SOFT,
            text_color=C_TEXT_SECONDARY, active_text_color=C_TEXT_INVERSE,
            font_size=FS_TINY, bold_active=True, text_anchor="center",
            duration_ms=200, width=190, height=32,
            track_color=C_PANEL_ALT_BG)
        self.manage_tab_bar.pack(side=RIGHT)
        try:
            self.manage_tab_bar.select("overview", animate=False)
        except Exception:
            pass

        self.manage_content = ctk.CTkFrame(left, fg_color="transparent")
        self.manage_content.pack(fill=BOTH, expand=True, padx=PAD_CARD_X,
                                 pady=(0, PAD_CARD_Y))
        self.manage_overview = ManagePresetList(self.manage_content, self)
        self.manage_files_frame = ctk.CTkFrame(
            self.manage_content, fg_color="transparent")
        self.manage_browser = CloudBrowser(
            self.manage_files_frame, self, on_path=self._on_manage_path)
        self.manage_browser.pack(fill=BOTH, expand=True)
        self.manage_overview.pack(fill=BOTH, expand=True)

        right = ctk.CTkFrame(body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        quick = ctk.CTkFrame(right, fg_color=C_CARD_BG,
                              corner_radius=R_CARD, border_width=0)
        quick.grid(row=0, column=0, sticky="ew", pady=(0, PAD_GAP))
        self.manage_quick = quick
        quick_head = ctk.CTkFrame(quick, fg_color="transparent")
        quick_head.pack(fill=X, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        make_section_header(quick_head, 2, "快捷操作").pack(side=LEFT)
        self.manage_current_label = make_label(
            quick_head, text="未选择预设", fg=C_TEXT_MUTED,
            font_size=FS_TINY)
        self.manage_current_label.pack(side=RIGHT)

        self.manage_primary_btn = make_button(
            quick, "从云端添加", command=self._manage_primary_action,
            accent=True, height=36, font_size=FS_SMALL)
        self.manage_primary_btn.pack(fill=X, padx=PAD_CARD_X,
                                      pady=(0, PAD_TIGHT))

        self.manage_dev_actions = ctk.CTkFrame(quick, fg_color="transparent")
        self.manage_dev_actions.pack(fill=X, padx=PAD_CARD_X)
        self.manage_path_row = ctk.CTkFrame(self.manage_dev_actions,
                                             fg_color="transparent")
        self.manage_path_row.pack(fill=X, pady=(0, PAD_TIGHT))
        make_label(self.manage_path_row, text="云端路径", fg=C_TEXT_MUTED,
                   font_size=FS_TINY).pack(anchor=W)
        path_line = ctk.CTkFrame(self.manage_path_row, fg_color="transparent")
        path_line.pack(fill=X, pady=(1, 0))
        self.manage_path_var = StringVar(value="/")
        self.manage_path_entry = make_entry(
            path_line, textvariable=self.manage_path_var,
            placeholder="例如 /PulsesSwap/SSR预设")
        self.manage_path_entry.pack(side=LEFT, fill=X, expand=True,
                                     padx=(0, PAD_TIGHT))
        self.manage_path_entry.bind("<Return>", lambda e: self._manage_goto())
        make_text_button(path_line, "打开",
                         command=self._manage_goto).pack(side=RIGHT)

        dev_btns = ctk.CTkFrame(self.manage_dev_actions,
                                 fg_color="transparent")
        dev_btns.pack(fill=X)
        self.manage_upload_menu = make_menu_button(
            dev_btns, text="上传 ▾", as_text=True,
            items=lambda: [
                ("上传文件…", self._manage_upload_files),
                ("上传文件夹…", self._manage_upload_folder),
                None,
                ("新建云端文件夹…", self._manage_new_folder),
            ])
        self.manage_upload_menu.pack(side=LEFT)
        make_text_button(dev_btns, "刷新",
                         command=self._manage_refresh).pack(
            side=LEFT, padx=(PAD_TIGHT, 0))
        self.manage_tacz_btn = make_text_button(
            dev_btns, "打开 TACZ", command=self.open_tacz_folder,
            state="disabled")
        self.manage_tacz_btn.pack(side=LEFT, padx=(PAD_TIGHT, 0))
        make_text_button(dev_btns, "清理缓存",
                         command=self._manage_clean_cache).pack(
            side=LEFT, padx=(PAD_TIGHT, 0))

        self.manage_player_actions = ctk.CTkFrame(quick,
                                                   fg_color="transparent")
        self.manage_player_actions.pack(fill=X, padx=PAD_CARD_X)
        player_btns = ctk.CTkFrame(self.manage_player_actions,
                                    fg_color="transparent")
        player_btns.pack(fill=X)
        make_text_button(player_btns, "从云端添加",
                         command=self.open_add_from_cloud).pack(side=LEFT)
        make_text_button(player_btns, "同步当前",
                         command=self._manage_sync_current).pack(
            side=LEFT, padx=(PAD_TIGHT, 0))
        make_text_button(player_btns, "检查更新",
                         command=self._manage_check_current).pack(
            side=LEFT, padx=(PAD_TIGHT, 0))
        make_text_button(player_btns, "刷新",
                         command=self._manage_refresh).pack(
            side=LEFT, padx=(PAD_TIGHT, 0))
        make_text_button(player_btns, "清理缓存",
                         command=self._manage_clean_cache).pack(
            side=LEFT, padx=(PAD_TIGHT, 0))

        self.manage_status = make_label(
            quick, text="", fg=C_TEXT_MUTED, font_size=FS_TINY)
        self.manage_status.pack(anchor=W, padx=PAD_CARD_X,
                                 pady=(PAD_TIGHT, PAD_CARD_Y))

        log_card = ctk.CTkFrame(right, fg_color=C_CARD_BG,
                                 corner_radius=R_CARD, border_width=0)
        log_card.grid(row=1, column=0, sticky="nsew")
        log_head = ctk.CTkFrame(log_card, fg_color="transparent")
        log_head.pack(fill=X, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        make_label(log_head, text="完整日志", fg=C_TEXT_SECONDARY,
                   font_size=FS_SMALL, bold=True).pack(side=LEFT)
        make_text_button(log_head, "清空", command=self.clear_log).pack(
            side=RIGHT)
        self.manage_log_text = ctk.CTkTextbox(
            log_card, fg_color=C_PANEL_BG, border_color=C_BORDER_SOFT,
            border_width=BORDER_W, corner_radius=R_CONTROL,
            text_color=C_TEXT_SECONDARY, font=(FONT_FAMILY_MONO, FS_TINY),
            wrap="word")
        self.manage_log_text.pack(fill=BOTH, expand=True, padx=PAD_CARD_X,
                                   pady=(0, PAD_CARD_Y))
        try:
            self.log_manager.attach(self.manage_log_text)
        except Exception:
            pass

        # 兼容旧调用：本地枪包卡已并入“预设总览”，不再单独占一块空白
        self.manage_pack_list = None
        self.manage_pack_card = None
        self._manage_show_tab("overview")
        self._update_manage_role()
        return page

    def _manage_stat(self, parent, caption, value):
        tile = ctk.CTkFrame(parent, fg_color=C_PANEL_ALT_BG,
                             corner_radius=R_CONTROL)
        tile.pack(side=LEFT, fill=X, expand=True, padx=(0, PAD_GAP))
        make_label(tile, text=caption, fg=C_TEXT_MUTED,
                   font_size=FS_TINY).pack(anchor=W, padx=PAD_GAP,
                                            pady=(PAD_TIGHT, 0))
        num = make_label(tile, text=value, fg=C_TEXT_MAIN,
                          font_size=FS_TITLE, bold=True)
        num.pack(anchor=W, padx=PAD_GAP, pady=(0, PAD_TIGHT))
        return num

    def _manage_show_tab(self, key):
        if key not in ("overview", "files"):
            return
        try:
            self.manage_tab_bar.select(key, animate=True, notify=False)
        except Exception:
            pass
        self._manage_active_tab = key
        if key == "overview":
            try:
                self.manage_files_frame.pack_forget()
                self.manage_overview.pack(fill=BOTH, expand=True)
            except Exception:
                pass
            self._update_manage_overview()
        else:
            try:
                self.manage_overview.pack_forget()
                self.manage_files_frame.pack(fill=BOTH, expand=True)
            except Exception:
                pass
            if not bool(getattr(self, "is_developer", False)):
                self.manage_browser.set_enabled(
                    False, "玩家从分享链接下载，不需要登录开发者网盘")
            elif getattr(self, "online", None) is None or \
                    not self.online.has_account():
                self.manage_browser.set_enabled(
                    False, "还没有登录蓝奏云 · 点侧边栏「登录」后浏览")
            else:
                self.manage_browser.set_enabled(True)
                target = self.manage_path_var.get().strip() or "/"
                if (not self.manage_browser.has_data()
                        or target != self.manage_browser.path()):
                    self.manage_browser.set_path(target)

    # ==================================================================
    # 状态同步
    # ==================================================================
    def _update_manage_role(self):
        dev = bool(getattr(self, "is_developer", False))
        try:
            self.manage_role_label.configure(
                text="开发者" if dev else "玩家",
                text_color=C_ACCENT if dev else C_TEXT_SECONDARY)
        except Exception:
            pass
        try:
            if dev:
                self.manage_player_actions.pack_forget()
                if not self.manage_dev_actions.winfo_manager():
                    self.manage_dev_actions.pack(fill=X, padx=PAD_CARD_X)
                if not self.manage_tab_bar.winfo_manager():
                    self.manage_tab_bar.pack(side=RIGHT)
            else:
                self.manage_dev_actions.pack_forget()
                if not self.manage_player_actions.winfo_manager():
                    self.manage_player_actions.pack(fill=X, padx=PAD_CARD_X)
                # 玩家没有开发者网盘，不需要“云端文件”这个 Tab
                if self.manage_tab_bar.winfo_manager():
                    self.manage_tab_bar.pack_forget()
                if getattr(self, "_manage_active_tab", "overview") == "files":
                    self._manage_show_tab("overview")
        except Exception:
            pass
        try:
            self.manage_tacz_btn.configure(
                state="normal" if self.tacz_path else "disabled")
        except Exception:
            pass
        try:
            online = getattr(self, "online", None)
            self.manage_browser.set_service(online)
            if dev:
                logged = bool(online is not None and online.has_account())
                self.manage_browser.set_enabled(
                    logged, "还没有登录蓝奏云 · 点侧边栏「登录」后浏览")
                if logged:
                    target = self.manage_path_var.get().strip() or "/"
                    if not self.manage_browser.has_data():
                        self.manage_browser.set_path(target)
            else:
                self.manage_browser.set_enabled(
                    False, "玩家从分享链接下载，不需要登录开发者网盘")
        except Exception:
            pass
        self._update_manage_account()
        try:
            if dev:
                state = getattr(self, "_cloud_conn_state", "unknown")
                self.manage_status.configure(
                    text=("云端已连接" if state == "online"
                          else "云端无法连接" if state == "offline"
                          else "未登录蓝奏云"),
                    text_color=(C_SUCCESS if state == "online"
                                else C_ERROR if state == "offline"
                                else C_TEXT_MUTED))
            else:
                self.manage_status.configure(
                    text="玩家模式 · 从分享链接下载", text_color=C_TEXT_MUTED)
        except Exception:
            pass
        # 身份变了，空态文案/按钮也要跟着变
        self._manage_overview_sig = None
        self._update_manage_overview()
        self._update_manage_summary()
        self._update_manage_current()

    def _update_manage_account(self):
        label = getattr(self, "manage_account_label", None)
        if label is None:
            return
        online = getattr(self, "online", None)
        if online is None:
            label.configure(text="在线模块未启用", text_color=C_TEXT_MUTED)
            return
        if not self.is_developer:
            label.configure(text="玩家 · 使用分享链接", text_color=C_TEXT_MUTED)
            return
        info = online.account_info()
        text = str(info.get("label") or "")
        if text:
            label.configure(text=text, text_color=C_TEXT_SECONDARY)
        else:
            label.configure(text="未登录", text_color=C_WARNING)

    # ---------- 总览列表 ----------
    def _manage_overview_rows(self):
        rows = []
        if self.preset_manager is not None:
            for name, info in self.preset_manager.presets.items():
                data = self._preset_card_data(name)
                source = {}
                try:
                    source = self.online.source_of(name) if self.online else {}
                except Exception:
                    source = {}
                path = str(source.get("cloud_path") or "")
                status = str(data.get("status") or "")
                action = str(data.get("action") or "")
                kind = str(data.get("action_kind") or "")
                if not action:
                    bound = bool(self.online and (
                        self.online.is_bound(name)
                        or (self.is_developer and path)))
                    action = "检查" if bound else "绑定"
                    kind = "check" if bound else "source"
                rows.append({
                    "name": name,
                    "version": "",
                    "meta": str(data.get("meta") or ""),
                    "path": path,
                    "status": status,
                    "color": data.get("status_color") or C_TEXT_MUTED,
                    "action": action,
                    "kind": kind,
                    "applied": bool(data.get("applied")),
                })
            return rows
        if self.is_developer:
            for folder in list(getattr(self, "_cloud_root_cache", []) or []):
                path = "/" + str(folder.get("name") or "")
                rows.append({
                    "name": str(folder.get("name") or ""),
                    "version": "",
                    "meta": "云端文件夹",
                    "path": path,
                    "status": "未加载整合包，仅浏览",
                    "color": C_INFO,
                    "action": "浏览",
                    "kind": "browse",
                    "applied": False,
                })
        return rows

    def _update_manage_overview(self):
        listing = getattr(self, "manage_overview", None)
        if listing is None:
            return
        rows = self._manage_overview_rows()
        signature = tuple((r["name"], r["status"], r["action"], r["meta"],
                           r["path"], r["applied"], r["color"]) for r in rows)
        if signature == getattr(self, "_manage_overview_sig", None):
            return
        self._manage_overview_sig = signature
        empty = ("先加载一个整合包，或从云端添加预设"
                 if not self.is_developer
                 else "还没有预设；先加载整合包，或先在「云端文件」里上传")
        listing.set_rows(rows, empty)

    def _update_manage_summary(self):
        local = len(self.preset_manager.presets) if self.preset_manager else 0
        cloud = 0
        pending = 0
        if self.preset_manager:
            for name in self.preset_manager.presets:
                if self.online is not None and (
                        self.online.is_bound(name)
                        or (self.is_developer
                            and self.online.cloud_path_of(name))):
                    cloud += 1
                data = self._preset_card_data(name)
                if data.get("action_kind") in ("publish", "sync"):
                    pending += 1
        elif self.is_developer:
            cloud = len(getattr(self, "_cloud_root_cache", []) or [])
            if not cloud:
                try:
                    root = (getattr(self.manage_browser, "_cache", {}) or {}).get("/") or {}
                    cloud = len(root.get("folders") or [])
                except Exception:
                    cloud = 0
        for widget, value in ((getattr(self, "manage_stat_local", None), local),
                              (getattr(self, "manage_stat_cloud", None), cloud),
                              (getattr(self, "manage_stat_pending", None),
                               pending)):
            try:
                widget.configure(text=str(value))
            except Exception:
                pass

    def _update_manage_current(self):
        label = getattr(self, "manage_current_label", None)
        btn = getattr(self, "manage_primary_btn", None)
        if label is None or btn is None:
            return
        name = getattr(self, "current_selected_preset", None)
        info = {}
        try:
            if self.preset_manager and name:
                info = self.preset_manager.presets.get(name) or {}
        except Exception:
            info = {}
        if not name:
            self._manage_last_preset = None
            label.configure(text="未选择预设")
            if self.is_developer:
                if not self.preset_manager:
                    btn.configure(text="浏览云端文件", state="normal")
                    self._manage_primary_kind = "files"
                else:
                    btn.configure(text="先选择预设", state="normal")
                    self._manage_primary_kind = "home"
            else:
                if not self.preset_manager:
                    btn.configure(text="去加载整合包", state="normal")
                    self._manage_primary_kind = "home"
                else:
                    btn.configure(text="从云端添加", state="normal")
                    self._manage_primary_kind = "add"
            return
        label.configure(text=name)
        applied = bool(info.get("applied"))
        if name != getattr(self, "_manage_last_preset", None):
            self._manage_last_preset = name
            if self.is_developer and self.online is not None:
                try:
                    cloud_path = self.online.cloud_path_of(name)
                    if cloud_path:
                        self.manage_path_var.set(cloud_path)
                except Exception:
                    pass
        data = self._preset_card_data(name)
        if self.is_developer:
            if applied:
                btn.configure(text="发布到云端", state="normal")
                self._manage_primary_kind = "publish"
            else:
                btn.configure(text="先应用当前预设", state="normal")
                self._manage_primary_kind = "apply"
        else:
            if not applied:
                btn.configure(text="一键替换", state="normal")
                self._manage_primary_kind = "apply"
            elif data.get("action_kind") == "sync":
                btn.configure(text="同步更新", state="normal")
                self._manage_primary_kind = "sync"
            else:
                btn.configure(text="打开详情", state="normal")
                self._manage_primary_kind = "detail"

    def _update_manage_pack_list(self):
        # 旧入口保留：管理页已改成总览，不再单独维护枪包卡
        self._update_manage_overview()
        self._update_manage_summary()
        self._update_manage_current()

    def _manage_select(self, name):
        if self.preset_manager and name in self.preset_manager.presets:
            try:
                self.preset_cards.select(name, notify=False)
                self.on_preset_selected(name)
            except Exception:
                pass
            self._update_manage_current()
            return
        for folder in list(getattr(self, "_cloud_root_cache", []) or []):
            if str(folder.get("name") or "") == name:
                self._manage_show_tab("files")
                self.manage_browser.set_path("/" + name)
                return

    def _manage_preset_action(self, name, kind):
        if kind == "browse":
            self._manage_show_tab("files")
            self.manage_browser.set_path("/" + name)
            return
        if self.preset_manager and name in self.preset_manager.presets:
            try:
                self.preset_cards.select(name, notify=False)
                self.on_preset_selected(name)
            except Exception:
                pass
        if kind == "publish":
            self.open_publish_dialog(name)
        elif kind == "sync":
            self._sync_now(name)
        elif kind == "check":
            self._online_check(name)
        elif kind == "apply":
            self.apply_preset()
        elif kind == "source":
            self.open_source_dialog(name)
        else:
            self.open_preset_detail(name)

    def _manage_primary_action(self):
        if _OVERLAY_STACK:
            return
        name = getattr(self, "current_selected_preset", None)
        kind = getattr(self, "_manage_primary_kind", "")
        if kind == "files":
            self._manage_show_tab("files")
            return
        if kind == "home":
            self.show_page("home")
            return
        if kind == "add":
            self.open_add_from_cloud()
            return
        if not name:
            return
        if kind == "publish":
            self.open_publish_dialog(name)
        elif kind == "sync":
            self._sync_now(name)
        elif kind == "apply":
            self.apply_preset()
        elif kind == "detail":
            self.open_preset_detail(name)

    def _manage_goto(self):
        path = ""
        try:
            path = self.manage_path_var.get().strip() or "/"
        except Exception:
            pass
        self._manage_show_tab("files")
        self.manage_browser.set_path(path)
        self.set_status(f"正在读取云端：{path}", "busy", progress=0.1)

    def _on_manage_path(self, path):
        try:
            self.manage_path_var.set(path)
        except Exception:
            pass

    def _manage_clean_cache(self):
        service = getattr(self, "online", None)
        if service is None:
            self.toast("在线模块未启用", "warning")
            return
        try:
            freed = service.clear_caches()
        except Exception as exc:                    # noqa: BLE001
            self.toast(f"清理失败：{exc}", "error")
            return
        self.toast(f"已清理 {format_size(freed)}", "success")
        self.set_status(f"已清理缓存 {format_size(freed)}", "success")

    def _manage_refresh(self):
        self._update_manage_role()
        self._update_manage_account()
        self._update_manage_pack_list()
        try:
            self.manage_browser.reload()
        except Exception:
            pass
        self.set_status("管理面板已刷新", "success")

    def _manage_sync_current(self):
        name = getattr(self, "current_selected_preset", None)
        if not name:
            self.toast("先选择一个预设", "warning")
            return
        self._sync_now(name)

    def _manage_check_current(self):
        name = getattr(self, "current_selected_preset", None)
        if not name:
            self.toast("先选择一个预设", "warning")
            return
        self._online_check(name)

    # ==================================================================
    # 上传 / 新建文件夹（仅开发者）
    # ==================================================================
    def _manage_guard_developer(self):
        if not bool(getattr(self, "is_developer", False)):
            self.toast("上传只对开发者开放", "warning")
            return False
        if getattr(self, "online", None) is None:
            show_warning("在线功能不可用", "在线模块没有加载成功。")
            return False
        if not self.online.has_account():
            self.toast("先登录蓝奏云", "info")
            self.open_identity_dialog()
            return False
        if getattr(self, "online_busy", False):
            self.toast("正在上传/同步，完成后再试", "warning")
            return False
        return True

    def _manage_target_path(self):
        """上传/新建文件夹的目标：路径框优先（用户可改），其次当前预设。"""
        try:
            path = self.manage_path_var.get().strip()
            if path:
                return path
        except Exception:
            pass
        try:
            if self.is_developer and self.current_selected_preset and self.online:
                path = self.online.cloud_path_of(self.current_selected_preset)
                if path:
                    return path
        except Exception:
            pass
        try:
            return self.manage_browser.path() or "/"
        except Exception:
            return "/"

    def _manage_upload_files(self):
        if not self._manage_guard_developer():
            return
        paths = filedialog.askopenfilenames(title="选择要上传到云端的文件")
        if paths:
            self._start_cloud_upload(list(paths))

    def _manage_upload_folder(self):
        if not self._manage_guard_developer():
            return
        folder = filedialog.askdirectory(title="选择要上传到云端的文件夹")
        if folder:
            self._start_cloud_upload([folder])

    def _manage_new_folder(self):
        if not self._manage_guard_developer():
            return
        name = ask_text(self, "新建云端文件夹", "文件夹名称",
                        placeholder="例如 SSR预设", ok_text="创建")
        if not name or not str(name).strip():
            return
        parent = self._manage_target_path()
        service = self.online
        self.set_status("正在创建云端文件夹…", "busy", progress=0.2)

        def worker():
            try:
                result = service.cloud_mkdir(parent, str(name).strip())
                ui_call(self.root, self._on_new_folder_done, result, None)
            except Exception as exc:                # noqa: BLE001
                ui_call(self.root, self._on_new_folder_done, None, exc)

        threading.Thread(target=worker, daemon=True).start()

    def _on_new_folder_done(self, result, error):
        if error is not None:
            self.set_status(f"新建文件夹失败：{error}", "error")
            show_error("新建文件夹失败", str(error))
            return
        path = result.get("path") if result else ""
        self.toast(f"已创建 {path}", "success")
        self.set_status(f"已创建云端文件夹：{path}", "success")
        try:
            self.manage_browser.set_path(path)
        except Exception:
            pass
        self._refresh_sidebar_clouds()

    def _start_cloud_upload(self, local_paths):
        if not self._manage_guard_developer():
            return
        target = self._manage_target_path()
        service = self.online
        card = make_card(self, None, width=560)
        card.add_title("正在上传到云端")
        card.add_subtitle(f"目标：{target}")
        panel = self._build_progress_panel(card.body)
        cancel_flag = {"stop": False}

        def do_cancel():
            cancel_flag["stop"] = True
            cancel_btn.configure(state="disabled", text="正在停止…")

        cancel_btn = make_button(panel["buttons"], "取消", command=do_cancel)
        cancel_btn.pack(side=RIGHT)
        panel["buttons"].pack(fill=X, pady=(PAD_DIALOG, 0))

        throttle = {"last": 0.0}

        def on_progress(done, total, name):
            now = time.time()
            if now - throttle["last"] < 0.08 and done < total:
                return
            throttle["last"] = now
            ui_call(self.root, panel["update"], done, total, 0, 0, str(name))

        def on_item(index, total, name, phase):
            if phase == "start":
                ui_call(self.root, panel["stage"], f"[{index}/{total}] {name}")
                ui_call(self.root, self.set_status,
                        f"上传中 [{index}/{total}] {name}", "busy")

        self._set_online_busy(True)
        self.set_busy_state(True, "上传")

        def worker():
            try:
                result = service.cloud_upload(
                    target, local_paths, on_item=on_item,
                    on_progress=on_progress,
                    cancel=lambda: cancel_flag["stop"])
                ui_call(self.root, self._on_cloud_upload_done, card, result,
                        None)
            except OnlineCancelled:
                ui_call(self.root, self._on_cloud_upload_done, card, None, None)
            except Exception as exc:                # noqa: BLE001
                ui_call(self.root, self._on_cloud_upload_done, card, None, exc)

        threading.Thread(target=worker, daemon=True).start()

    def _on_cloud_upload_done(self, card, result, error):
        self._set_online_busy(False)
        self.set_busy_state(False, "")
        try:
            card.close(True)
        except Exception:
            pass
        if error is not None:
            self.set_status(f"上传失败：{error}", "error")
            show_error("上传失败", str(error))
            return
        if result is None:
            self.set_status("已取消上传", "warning")
            self.toast("已取消上传", "info")
            return
        failed = result.get("failed") or []
        count = len(result.get("uploaded") or [])
        if failed:
            detail = "\n".join(f"· {name}：{reason}" for name, reason in failed[:6])
            self.set_status(f"上传完成，失败 {len(failed)} 项", "warning")
            show_warning("部分文件上传失败", f"成功 {count} 项\n\n{detail}")
        else:
            self.set_status(f"上传完成 · {count} 项", "success")
            self.toast(f"已上传 {count} 项", "success")
        self.log_manager.log(
            f"云端上传：成功 {count} 项，失败 {len(failed)} 项",
            "SUCCESS" if not failed else "WARNING")
        try:
            self.manage_browser.reload()
        except Exception:
            pass
        self._refresh_sidebar_clouds()
