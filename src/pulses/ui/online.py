"""
在线同步界面：身份切换 / 来源绑定 / 检查更新 / 同步 / 发布。

所有网络动作都放在工作线程，回到主线程只通过 ``ui_call``，
所以这里看不到 ``root.after`` 的跨线程调用。
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
from tkinter import *

from .. import config
from ..config import *
from ..utils import *
from ..animation import *
from ..widget import *
from ..dialogs import *
from ..dialogs import _OVERLAY_STACK

try:
    from online import diff as online_diff
    from online.errors import CancelledError as OnlineCancelled
    from online.errors import OnlineError
    from online.service import OnlineService, PresetRef
    HAS_ONLINE = True
except Exception:                    # pragma: no cover - 只有打包漏文件才会走到
    HAS_ONLINE = False
    OnlineError = Exception
    OnlineService = None
    PresetRef = None
    online_diff = None
    OnlineCancelled = Exception


# 卡片状态点颜色
DOT_OK = C_SUCCESS
DOT_UPDATE = C_WARNING
DOT_ERROR = C_ERROR
DOT_IDLE = C_INFO
DOT_NONE = C_TEXT_MUTED

ACTION_COLORS = {
    "download": C_INFO,
    "repair": C_INFO,
    "upload": C_ACCENT,
    "skip": C_TEXT_MUTED,
    "delete_cloud": C_ERROR,
    "delete_local": C_ERROR,
    "ask_delete_local": C_WARNING,
    "blocked": C_ERROR,
}


def _clipboard_link(root) -> str:
    """剪贴板里正好是蓝奏云链接时拿来预填（读不到/不像就返回空串）。

    很多人的操作顺序就是「在浏览器复制分享链接 → 回来点添加」，这一步能省掉一次粘贴。
    """
    try:
        text = str(root.clipboard_get() or "").strip()
    except Exception:
        return ""
    if not text or len(text) > 300 or "\n" in text or " " in text:
        return ""
    if "lanzou" not in text.lower():
        return ""
    return text


def _human_size(num) -> str:
    try:
        value = float(num or 0)
    except (TypeError, ValueError):
        return "0 B"
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _short(text, limit=32) -> str:
    """卡片上的状态行放不下长句，截断加省略号（完整内容在详情/日志里）。"""
    value = str(text or "").strip().replace("\n", " ")
    return value if len(value) <= limit else value[:limit - 1] + "…"


def _time_ago(stamp) -> str:
    if not stamp:
        return ""
    delta = max(0, int(time.time() - float(stamp)))
    if delta < 60:
        return "刚刚"
    if delta < 3600:
        return f"{delta // 60} 分钟前"
    if delta < 86400:
        return f"{delta // 3600} 小时前"
    return f"{delta // 86400} 天前"


class OnlineMixin:
    """在线功能的界面部分。"""

    # ==================================================================
    # 初始化
    # ==================================================================
    def _init_online(self, db_path=None):
        self.online = None
        # 这两个缓存必须在早期就存在：还没选整合包时 _set_role 也会去清它们，
        # 之前放在 db_path 分支里，导致「没有整合包时切身份」直接崩
        self._preset_size_cache = getattr(self, "_preset_size_cache", {})
        self.online_states = {}
        self.online_checking = set()
        self.online_pending = {}
        self.online_queue = []
        self._online_recheck: set[str] = set()
        self._last_sync_result = None
        self._last_publish_result = None
        if not HAS_ONLINE:
            self.log_manager.log("在线模块未加载（打包缺少 online 包）", 'WARNING')
            return
        db_path = db_path or getattr(self, "online_db_path", None)
        if not db_path:
            return
        self.online_db_path = Path(db_path)
        self._preset_size_cache: dict[str, tuple[int, int]] = {}
        try:
            self.online = OnlineService(
                db_path, log=self._online_log, app_version=VERSION)
        except Exception as exc:
            self.log_manager.log(f"在线模块初始化失败: {exc}", 'ERROR')
            self.online = None
            return

        notes = self.online.recover_all()
        for note in notes:
            self.log_manager.log(f"在线：{note}", 'INFO', verbose=True)
        if self.online.has_account() and self.settings.role == "developer":
            threading.Thread(target=self._restore_account_thread,
                             daemon=True).start()
        self._update_identity_ui()

    def _shutdown_online(self):
        """关掉整合包：停掉在线服务，别让后台线程还拿着旧路径。"""
        self.online = None
        self.online_states = {}
        self._clear_check_timers()
        self.online_checking = set()
        self.online_pending = {}
        self.online_queue = []
        self._refresh_preset_cards()

    def _online_log(self, message: str, level: str = "INFO",
                    verbose: bool = False) -> None:
        """在线模块的日志出口：兼容 LogManager 的 (message, level, verbose)。"""
        try:
            self.log_manager.log(message, level, verbose=verbose)
        except TypeError:
            try:
                self.log_manager.log(message, level)
            except Exception:
                pass
        except Exception:
            pass

    def _restore_account_thread(self):
        ok = self.online.restore_account()
        ui_call(self.root, self._on_account_restored, ok)

    def _on_account_restored(self, ok: bool):
        if not ok and self.settings.role == "developer":
            self.log_manager.log("开发者身份已恢复，但账号需要重新认证", 'WARNING')
            try:
                self.toast("开发者账号需要重新登录一次", "warning")
            except Exception:
                pass
        self._update_identity_ui()

    # ==================================================================
    # 身份
    # ==================================================================
    @property
    def is_developer(self) -> bool:
        return str(getattr(self.settings, "role", "player")) == "developer"

    def _set_role(self, role: str) -> None:
        """切换身份并落盘（弹窗与测试共用）。

        两套界面的动作语义不同（下载 vs 上传），旧计划必须作废重算。
        """
        new_role = "developer" if str(role).startswith("dev") else "player"
        previous = getattr(self.settings, "role", "player")
        changed = new_role != previous
        self.settings.role = new_role
        try:
            self.settings.save()
        except Exception:
            pass
        if changed:
            # 换身份要整窗换配色（玩家青绿 / 开发者石板蓝），并重建设置页的
            # 数据库分区——里面的管理项只对开发者开放
            config.UI_ROLE = new_role
            try:
                self._apply_role_actions()
            except Exception:
                pass
            try:
                roots = [self.root]
                # 页面挂在 Canvas 的 window item 里，winfo_children 走不到，
                # 必须把每个页面 frame 也一起刷
                roots.extend(p for p in getattr(self, "pages", {}).values()
                             if p is not None)
                theme_widgets(roots, previous, new_role)
            except Exception:
                pass
            self._rebuild_settings_role_dependent()
        if changed:
            self.online_states = {}
            self._clear_check_timers()
            self._online_recheck.clear()
            self.online_pending.clear()
            self._preset_size_cache.clear()
        self._update_identity_ui()
        if changed and self.preset_manager:
            names = [n for n in self.preset_manager.presets
                     if self.online and (
                         self.online.is_bound(n)
                         or (new_role == "developer"
                             and self.online.cloud_path_of(n)))]
            if names:
                self.online_queue = names
                self._pump_online_queue()

    def _rebuild_settings_role_dependent(self) -> None:
        """身份变了：设置页里的「数据库管理」只对开发者显示，整块重建。"""
        page = getattr(self, "settings_page", None)
        if page is None:
            return
        tab = getattr(page, "tabs", {}).get("database")
        if tab is None:
            return
        try:
            for child in tab.winfo_children():
                child.destroy()
            page._build_database(tab)
            page.reload()
        except Exception:
            pass

    def _update_identity_ui(self) -> None:
        """侧边栏的身份徽标 + 账号（打码）+ 按钮文字。"""
        account = ""
        try:
            if self.is_developer:
                self.identity_badge.configure(text="开发者",
                                                text_color=C_ACCENT)
                if self.online is not None:
                    account = str(self.online.account_info().get("label") or "")
            else:
                self.identity_badge.configure(text="玩家",
                                                text_color=C_TEXT_SECONDARY)
            self.identity_btn.configure(text="切换身份")
        except Exception:
            pass
        # 账号单独占一行：侧边栏只有 200px，塞进徽标会挤成省略号
        try:
            label = getattr(self, "identity_account", None)
            if label is not None:
                if account:
                    label.configure(text=account, text_color=C_TEXT_MUTED)
                    label.pack(anchor=W, padx=PAD_CARD_X,
                               pady=(0, PAD_GAP))
                else:
                    label.pack_forget()
        except Exception:
            pass
        try:
            self._apply_role_actions()
        except Exception:
            pass
        self._refresh_preset_cards()

    def open_identity_dialog(self):
        if self.online is None:
            # 还没选整合包时在线服务是空的 —— 这不是"安装不完整"。
            # 开发者身份要能随时切回玩家，否则一旦以开发者退出就卡住了。
            if self.is_developer:
                self._set_role("player")
                self.toast("已切回玩家", "info")
                return
            show_info("先选择一个整合包",
                      "在线功能要等选好整合包（tacz 所在目录）之后才可用。\n\n"
                      "选好之后再点这里，就能登录蓝奏云切换为开发者。")
            return
        if self.is_developer:
            self._open_developer_card()
        else:
            self._open_become_developer_card()

    @staticmethod
    def _caps_lock_on() -> bool:
        """大写锁定是否开启（Windows 走 GetKeyState，其它平台一律 False）。"""
        if not IS_WINDOWS:
            return False
        try:
            import ctypes as _ct
            return bool(_ct.windll.user32.GetKeyState(0x14) & 1)
        except Exception:
            return False

    def _open_become_developer_card(self):
        card = make_card(self, None, width=540)
        card.add_title("切换为开发者")
        card.add_subtitle("发布预设需要蓝奏云账号认证。密码只保存在本机，用于下次自动登录。")

        info = self.online.account_info()
        saved = bool(info.get("saved"))
        # 账号框填的是登录名（手机号/邮箱）。旧版本存的是蓝奏的会话 ID，
        # 那个数字不是账号，不能填进来，更不能拿去登录。
        username = str(info.get("username") or "")
        uid_var = StringVar(value=username)
        pwd_var = StringVar(value="")
        remember_var = BooleanVar(value=True)

        form = ctk.CTkFrame(card.body, fg_color="transparent")
        form.pack(fill=X, pady=(PAD_TIGHT, 0))

        uid_field = FormField(
            form, "蓝奏账号", textvariable=uid_var,
            placeholder="手机号 / 邮箱",
            hint="上次登录的账号，换号直接改这里" if username else "")
        uid_field.frame.pack(fill=X)

        pwd_field = FormField(
            form, "密码", textvariable=pwd_var, password=True,
            placeholder="已保存过，可留空" if saved else "蓝奏云登录密码",
            hint="留空就用本机保存的密码" if saved else "")
        pwd_field.frame.pack(fill=X, pady=(PAD_GAP, 0))

        opts = ctk.CTkFrame(form, fg_color="transparent")
        opts.pack(fill=X, pady=(PAD_GAP, 0))
        remember = make_checkbox(opts, "记住账号（下次自动登录）", remember_var)
        remember.pack(side=LEFT)
        ctk.CTkButton(
            opts, text="打开蓝奏云", width=80, height=20,
            fg_color="transparent", hover_color=C_PANEL_ALT_BG,
            text_color=C_TEXT_MUTED, corner_radius=4,
            font=(config.FONT_FAMILY, FS_TINY, "bold"),
            command=lambda: open_url("https://www.lanzou.com")).pack(side=RIGHT)

        status = make_label(form, text=" ", fg=C_TEXT_MUTED, font_size=FS_TINY)
        status.pack(anchor=W, pady=(PAD_TIGHT, 0))

        bar = self._dialog_bar(card)
        make_button(bar, "取消", command=lambda: card.close(False)).pack(side=RIGHT)

        state = {"busy": False}

        def set_busy(busy, note=""):
            state["busy"] = busy
            uid_field.set_enabled(not busy)
            pwd_field.set_enabled(not busy)
            try:
                remember.configure(state="disabled" if busy else "normal")
                login_btn.configure(state="disabled" if busy else "normal",
                                    text="正在登录…" if busy else "登录并切换")
            except Exception:
                pass
            if note:
                status.configure(text=note, text_color=C_ACCENT)

        def fail(message):
            """登录失败：留在弹窗里，保住已填的内容，直接改密码重试。"""
            set_busy(False)
            status.configure(text=message, text_color=C_ERROR)
            # 先聚焦再标红：聚焦动画会抢描边，顺序反了红色就被盖掉了
            try:
                inner = getattr(pwd_field.entry, "_entry", None)
                if inner is not None:
                    inner.focus_set()
                    inner.selection_range(0, END)
            except Exception:
                pass
            pwd_field.mark_error()

        def do_login(event=None):
            if state["busy"]:
                return "break"
            uid_field.ok()
            pwd_field.ok()
            user = uid_var.get().strip()
            pwd = pwd_var.get()
            if not user:
                uid_field.focus()
                uid_field.error("填一下蓝奏云账号")
                return "break"
            if not pwd:
                if saved:
                    pwd = self.online.accounts.password() or ""
                if not pwd:
                    pwd_field.focus()
                    pwd_field.error("填一下密码")
                    return "break"
            status.configure(text=" ", text_color=C_TEXT_MUTED)
            set_busy(True, "正在登录，请稍等…")
            self._developer_login(user, pwd, card,
                                  remember=bool(remember_var.get()),
                                  on_fail=fail)
            return "break"

        login_btn = make_button(bar, "登录并切换", command=do_login, accent=True)
        login_btn.pack(side=RIGHT, padx=(0, PAD_TIGHT))

        def on_caps(_event=None):
            if state["busy"]:
                return
            pwd_field.hint("大写锁定已开启" if self._caps_lock_on() else "",
                           C_WARNING)

        card.register_focusable(uid_field.entry)
        card.register_focusable(pwd_field.entry)
        card.register_focusable(login_btn)
        uid_field.entry.bind("<Return>", lambda e: pwd_field.focus())
        pwd_field.entry.bind("<Return>", do_login)
        pwd_field.entry.bind("<KeyRelease>", on_caps, add="+")
        uid_field.focus()

    def _developer_login(self, username, password, card=None, *,
                         remember=True, on_fail=None):
        """登录并在成功后切换身份（弹窗与测试共用这一条路径）。"""
        def worker():
            try:
                self.online.login(username, password, remember=remember)
                ui_call(self.root, self._on_developer_login, card, None, on_fail)
            except OnlineError as exc:
                ui_call(self.root, self._on_developer_login, card, exc, on_fail)

        threading.Thread(target=worker, daemon=True).start()

    def _on_developer_login(self, card, error, on_fail=None):
        if error is not None:
            # 有表单就留在表单里报错，别把人填的内容一起关掉
            if on_fail is not None:
                try:
                    on_fail(str(error))
                    return
                except Exception:
                    pass
            if card is not None:
                try:
                    card.close(True)
                except Exception:
                    pass
            show_error("认证失败", str(error))
            return
        if card is not None:
            try:
                card.close(True)
            except Exception:
                pass
        self._set_role("developer")
        self.log_manager.log("已切换为开发者身份", 'SUCCESS')
        self.toast("已切换为开发者", "success")
        self._refresh_preset_cards()

    def _open_developer_card(self):
        card = make_card(self, None, width=460)
        card.add_title("开发者")
        info = self.online.account_info()
        account = str(info.get("label") or "")
        if account:
            card.add_text(f"已认证账号：{account}", fg=C_TEXT_MAIN,
                          font_size=FS_SMALL)
        else:
            card.add_text("已认证（本机保存了登录状态）", fg=C_TEXT_MAIN,
                          font_size=FS_SMALL)
        card.add_text("切回玩家后，开发者入口会隐藏，认证信息保留在本机。",
                      fg=C_TEXT_SECONDARY, font_size=FS_TINY)

        bar = self._dialog_bar(card)
        make_button(bar, "关闭", command=lambda: card.close(False)).pack(side=RIGHT)

        def switch_back():
            card.close(True)
            self._set_role("player")
            self.log_manager.log("已切换为玩家身份", 'INFO')
            self.toast("已切换为玩家", "info")

        def logout():
            # 退出认证会清掉本机保存的密码，属于不可逆操作，先确认
            if not ask_yes_no(
                    self.root, "退出认证",
                    "退出后会删除本机保存的蓝奏云账号和密码。\n"
                    "下次发布需要重新登录。"):
                return
            self.online.logout(forget=True)
            card.close(True)
            self._set_role("player")
            self.log_manager.log("已退出认证并清除本机凭据", 'INFO')
            self.toast("已退出认证", "info")

        make_button(bar, "退出认证", command=logout).pack(side=RIGHT,
                                                          padx=(0, PAD_TIGHT))
        make_button(bar, "切换为玩家", command=switch_back,
                    accent=True).pack(side=RIGHT, padx=(0, PAD_TIGHT))

    # ==================================================================
    # 预设 → 卡片数据
    # ==================================================================
    def _preset_ref(self, name: str):
        if not self.preset_manager or PresetRef is None:
            return None
        info = self.preset_manager.presets.get(name)
        if not info:
            return None
        path = str(info.get("path") or "")
        if not path:
            return None
        applied = bool(info.get("applied"))
        root = str(self.tacz_path) if (applied and self.tacz_path) else path
        return PresetRef(name=name, path=path, root=root, applied=applied)

    def _online_state(self, name: str) -> dict:
        return self.online_states.get(name) or {}

    def _preset_size(self, name: str, info: dict) -> tuple[int, int]:
        """(枪包数, 总体积)。index.json 里有就用，没有就轻量扫一层。

        轻量扫描只做 stat，不读文件内容；结果按预设缓存，
        列表刷新时统一清掉（见 _update_preset_list）。
        """
        gunpacks = info.get("gunpacks") or {}
        if gunpacks:
            size = 0
            for fingerprint in gunpacks.values():
                try:
                    size += int(fingerprint.get("size") or 0)
                except (TypeError, ValueError, AttributeError):
                    pass
            return len(gunpacks), size
        cached = self._preset_size_cache.get(name)
        if cached is not None:
            return cached
        root = str(self.tacz_path) if (info.get("applied") and self.tacz_path) \
            else str(info.get("path") or "")
        measured = _quick_measure(root)
        self._preset_size_cache[name] = measured
        return measured

    def _after_rename_preset(self, old: str, new: str) -> None:
        """改名后把在线状态、绑定、缓存一起搬到新名字。"""
        if not old or not new or old == new:
            return
        try:
            if self.online is not None:
                self.online.rename_preset(old, new)
        except Exception:
            pass
        for store in (self.online_states, self.online_pending):
            try:
                if old in store:
                    store[new] = store.pop(old)
            except Exception:
                pass
        try:
            if old in self._online_recheck:
                self._online_recheck.discard(old)
                self._online_recheck.add(new)
        except Exception:
            pass
        try:
            if old in self._preset_size_cache:
                self._preset_size_cache[new] = self._preset_size_cache.pop(old)
        except Exception:
            pass
        if getattr(self, "current_selected_preset", None) == old:
            self.current_selected_preset = new

    def _check_summary(self, name: str) -> str:
        """检查完成后的简短结论（来源页里显示）。"""
        state = self._online_state(name)
        plan = state.get("plan")
        if plan is None or online_diff is None:
            return ""
        offline = bool(getattr(plan, "offline", False))
        suffix = "（离线）" if offline else ""
        try:
            if self.is_developer:
                pending = (plan.count_of(online_diff.UPLOAD)
                           + plan.count_of(online_diff.DELETE_CLOUD))
                return ("云端已是最新" if not pending
                        else f"有 {pending} 项待发布{suffix}")
            updates = (plan.count_of(online_diff.DOWNLOAD)
                       + plan.count_of(online_diff.REPAIR))
            if not updates:
                return "已是最新" + suffix
            return f"有 {updates} 个更新{suffix}"
        except Exception:
            return ""

    def _preset_card_data(self, name: str) -> dict:
        info = (self.preset_manager.presets.get(name) if self.preset_manager
                else {}) or {}
        count, size = self._preset_size(name, info)
        version = str(info.get("version") or "v1.0.0")
        applied = bool(info.get("applied"))

        data = {"name": name, "applied": applied,
                "meta": f"{version} · {count} 个枪包 · {_human_size(size)}",
                "status": "", "status_color": C_TEXT_SECONDARY,
                "dot_color": DOT_NONE, "action": "", "action_kind": "",
                "badge": "已应用" if applied else ""}

        state = self._online_state(name)
        phase = state.get("phase") or ""
        plan = state.get("plan")
        error = state.get("error") or ""
        # 玩家看"有没有绑定分享"，开发者看"有没有填云端路径"
        bound = bool(self.online and (
            self.online.is_bound(name)
            or (self.is_developer and self.online.cloud_path_of(name))))

        if phase == "checking":
            data.update(status=str(state.get("phase_text") or "检查中…"),
                        status_color=C_ACCENT,
                        dot_color=DOT_IDLE, action="", action_kind="")
            return data

        if not bound:
            # 不在每张卡片上挂「绑定」按钮：双击进详情，「来源」页直接填
            data.update(status="未绑定云端源", status_color=C_TEXT_MUTED,
                        dot_color=DOT_IDLE, action="", action_kind="")
            return data

        if error:
            data.update(status=f"连接失败：{_short(error, 22)}",
                        status_color=C_ERROR,
                        dot_color=DOT_ERROR,
                        action="重试", action_kind="check")
            return data

        if plan is None:
            data.update(status="待检查", status_color=C_TEXT_SECONDARY,
                        dot_color=DOT_NONE,
                        action="检查", action_kind="check")
            return data

        if getattr(plan, "blocked", None):
            data.update(status=_short(plan.blocked[0], 30),
                        status_color=C_ERROR,
                        dot_color=DOT_ERROR, action="", action_kind="")
            return data

        if getattr(plan, "offline", False):
            # 云端这次没连上，计划来自缓存：只允许「重试」，不允许发布/同步
            data.update(status="无法连接（用缓存）", status_color=C_ERROR,
                        dot_color=DOT_ERROR, action="重试", action_kind="check")
            return data

        suffix = "（离线）" if getattr(plan, "offline", False) else ""
        if self.is_developer:
            pending = (plan.count_of(online_diff.UPLOAD)
                       + plan.count_of(online_diff.DELETE_CLOUD))
            if pending:
                data.update(
                    status=f"有 {pending} 项待发布{suffix}",
                    status_color=C_WARNING, dot_color=DOT_UPDATE,
                    action="发布", action_kind="publish", pulse=True)
            else:
                data.update(status=f"云端已是最新{suffix}",
                            status_color=C_SUCCESS, dot_color=DOT_OK,
                            action="", action_kind="")
            return data

        updates = (plan.count_of(online_diff.DOWNLOAD)
                   + plan.count_of(online_diff.REPAIR))
        if updates:
            data.update(
                status=f"有 {updates} 个更新 · {_human_size(plan.download_bytes)}"
                       f"{suffix}",
                status_color=C_WARNING, dot_color=DOT_UPDATE,
                action="更新", action_kind="sync", pulse=True)
        else:
            stamp = state.get("checked_at")
            when = _time_ago(stamp)
            data.update(status=f"已是最新{' · ' + when if when else ''}{suffix}",
                        status_color=C_SUCCESS, dot_color=DOT_OK,
                        action="", action_kind="")
        return data

    def _update_preset_online_label(self, name: str) -> None:
        """详情条的「云端」一行：和卡片状态保持一致。

        顺带决定那颗「同步 N 项」大按钮要不要出现 —— 只在真的有东西要下载时
        才浮出来，平时界面保持干净。
        """
        label = getattr(self, "preset_online_label", None)
        if label is None:
            return
        data = {}
        try:
            state = self._online_state(name)
            phase = str(state.get("phase") or "")
            data = self._preset_card_data(name)
            text = str(data.get("status") or "未绑定")
            color = data.get("status_color") or C_TEXT_MUTED
            # 详情条只放一句人话：连不上就是「无法连接」，具体原因在卡片/来源页。
            plan = state.get("plan")
            if phase == "error" or text.startswith("连接失败"):
                text, color = "无法连接", C_ERROR
            elif plan is not None and getattr(plan, "offline", False):
                # 有缓存所以还能列差异，但云端这次确实没连上
                text, color = "无法连接 · 用缓存", C_WARNING
            elif phase == "checking":
                text, color = str(state.get("phase_text") or "连接中…"), C_ACCENT
            else:
                # 左边已经写了「云端」，去掉状态里的「云端」前缀
                if text == "未绑定云端源":
                    text = "未绑定"
                elif text.startswith("云端"):
                    text = text[2:].lstrip(" ·")
            label.configure(text=_short(text, 26), text_color=color)
        except Exception:
            pass
        # 「填写链接」只在真没来源时出现；发布过/绑定过的预设显示「查看来源」
        btn = getattr(self, "source_btn", None)
        if btn is not None:
            try:
                bound = bool(self.online is not None and (
                    self.online.is_bound(name)
                    or (self.is_developer and self.online.cloud_path_of(name))))
                btn.configure(text="查看来源" if bound else "填写链接")
            except Exception:
                pass
        self._update_sync_button(name, data)

    def _update_sync_button(self, name, data=None) -> None:
        button = getattr(self, "sync_btn", None)
        if button is None:
            return
        try:
            if data is None:
                data = self._preset_card_data(name)
            plan = (self._online_state(name) or {}).get("plan")
            if self.is_developer:
                # 开发者没有「同步」这个动作；辅助行里的「一键替换」由
                # _apply_role_actions 负责，这里不能动 aux_row
                button.pack_forget()
                return
            if plan is not None and getattr(plan, "offline", False):
                button.pack_forget()
                alt = getattr(self, "apply_alt_btn", None)
                aux = getattr(self, "aux_row", None)
                if aux is not None and (alt is None or not alt.winfo_ismapped()):
                    aux.grid_remove()
                return
            pending = 0
            if plan is not None:
                for item in plan.items:
                    if item.action in (online_diff.DOWNLOAD, online_diff.REPAIR):
                        pending += 1
            show = bool(pending) and name == getattr(
                self, "current_selected_preset", None)
            if show:
                button.configure(text=f"同步 {pending} 项更新")
                button.pack(side=LEFT, fill=X, expand=True)
                aux = getattr(self, "aux_row", None)
                if aux is not None:
                    aux.grid()
            else:
                button.pack_forget()
                alt = getattr(self, "apply_alt_btn", None)
                aux = getattr(self, "aux_row", None)
                if aux is not None and (alt is None
                                        or not alt.winfo_ismapped()):
                    aux.grid_remove()
        except Exception:
            pass

    def _refresh_preset_cards(self) -> None:
        cards = getattr(self, "preset_cards", None)
        if cards is None or not self.preset_manager:
            return
        items = [self._preset_card_data(name)
                 for name in self.preset_manager.presets.keys()]
        cards.set_items(items)
        if self.current_selected_preset:
            cards.select(self.current_selected_preset, notify=False)
            # 卡片状态变了，右上角详情条也要跟着变（检查/发布完成后最容易漏）
            try:
                self._update_preset_online_label(self.current_selected_preset)
            except Exception:
                pass

    # ==================================================================
    # 检查更新
    # ==================================================================
    def _online_check(self, name: str, *, pending: str = "",
                      prompt: bool = True) -> None:
        if self.online is None:
            return
        if getattr(self, "is_applying", False):
            # 正在替换枪包时扫描，结果一定是半截的（文件正被搬来搬去）。
            # 应用结束会自己补一次检查。
            self.log_manager.log(f"替换进行中，跳过对「{name}」的检查", 'INFO',
                                 verbose=True)
            return
        if name in self.online_checking:
            # 正在检查时又要求检查：记一笔，等这次结束再补一次，
            # 否则刚同步完的卡片会一直停在旧状态上。
            self._online_recheck.add(name)
            if pending:
                self.online_pending[name] = pending
            return
        ref = self._preset_ref(name)
        if ref is None:
            return
        # 还没填来源：默认把用户带到「来源」页；但如果这次检查是保存之后
        # 自动触发的（prompt=False），就别再弹一层 —— 否则保存一下会多出
        # 一个一模一样的详情卡片叠在上面。
        if prompt:
            if not self.is_developer and not self.online.is_bound(name):
                self.open_source_dialog(name)
                return
            if self.is_developer and not self.online.cloud_path_of(name):
                self.open_source_dialog(name)
                return
        self.online_checking.add(name)
        if pending:
            self.online_pending[name] = pending
        # 每次检查一个自增 run id：完成/超时只认自己那次，避免旧定时器
        # 把后面的检查、挂起的同步/发布一起清掉。
        run = int(getattr(self, "_check_seq", 0)) + 1
        self._check_seq = run
        runs = getattr(self, "_check_runs", None)
        if runs is None:
            runs = self._check_runs = {}
        runs[name] = run
        state = self.online_states.setdefault(name, {})
        state["phase"] = "checking"
        state["phase_text"] = "连接云端…"
        state["error"] = ""
        self._refresh_preset_cards()

        # 捕获当前服务实例：检查期间用户可能关掉整合包（self.online 会变 None）
        service = self.online
        developer = self.is_developer

        def on_phase(text):
            # 工作线程里回调：只做数据标记，界面刷新切回主线程
            ui_call(self.root, self._check_phase, name, str(text))

        def worker():
            try:
                if developer:
                    plan = service.publish_plan(ref, on_phase=on_phase)
                else:
                    plan = service.check(ref, on_phase=on_phase)
                ui_call(self.root, self._on_check_done, name, plan, None, run)
            except OnlineError as exc:
                ui_call(self.root, self._on_check_done, name, None, exc, run)
            except Exception as exc:                    # noqa: BLE001
                ui_call(self.root, self._on_check_done, name, None,
                        OnlineError(f"检查失败：{exc}"), run)

        threading.Thread(target=worker, daemon=True).start()

        # 网络卡住时线程可能长期不返回：兜一层超时，别让卡片永远停在「检查中」
        def _timeout():
            if runs.get(name) != run:
                return                       # 这是上一次检查的定时器，别误伤
            if name not in self.online_checking:
                return
            self._cancel_check_timer(name)
            self.online_checking.discard(name)
            # 超时就把这次挂起的动作一起取消：否则用户下次随便点一下检查，
            # 迟到的结果会顺手把「发布」也执行了
            self.online_pending.pop(name, None)
            state = self.online_states.setdefault(name, {})
            if state.get("phase") == "checking":
                state["phase"] = "error"
                state["error"] = "检查超时（网络太慢或文件太多，稍后再试）"
                state["plan"] = None
                state["checked_at"] = time.time()
                self.log_manager.log(f"检查更新超时（{name}）", 'WARNING')
                self._refresh_preset_cards()

        try:
            self._cancel_check_timer(name)
            timers = getattr(self, "_check_timers", None)
            if timers is None:
                timers = self._check_timers = {}
            timers[name] = self.root.after(90000, _timeout)
        except Exception:
            pass

    def _clear_check_timers(self) -> None:
        for name in list(getattr(self, "_check_timers", {}) or {}):
            self._cancel_check_timer(name)
        runs = getattr(self, "_check_runs", None)
        if isinstance(runs, dict):
            runs.clear()

    def _cancel_check_timer(self, name: str) -> None:
        timers = getattr(self, "_check_timers", None)
        if not timers:
            return
        timer = timers.pop(name, None)
        if timer:
            try:
                self.root.after_cancel(timer)
            except Exception:
                pass

    def _check_phase(self, name: str, text: str) -> None:
        """检查过程中的阶段提示（连接云端 / 读取云端 / 扫描本地）。"""
        if name not in self.online_checking:
            return
        state = self.online_states.setdefault(name, {})
        state["phase_text"] = text
        self._refresh_preset_cards()

    def _on_check_done(self, name, plan, error, run=None):
        current = getattr(self, "_check_runs", {}).get(name)
        if run is not None and current is not None and run != current:
            # 过期的检查结果：界面/状态已经被新一次检查接管
            return
        self._cancel_check_timer(name)
        runs = getattr(self, "_check_runs", None)
        if runs is not None:
            runs.pop(name, None)
        self.online_checking.discard(name)
        # 关掉整合包 / 删掉预设之后，迟到的检查结果不要再写回界面状态
        if (self.online is None or self.preset_manager is None
                or name not in self.preset_manager.presets):
            self.online_pending.pop(name, None)
            try:
                self._online_recheck.discard(name)
            except Exception:
                pass
            return
        state = self.online_states.setdefault(name, {})
        state.pop("phase_text", None)
        state["checked_at"] = time.time()
        if error is not None:
            state["phase"] = "error"
            state["error"] = str(error)
            state["plan"] = None
            self.log_manager.log(f"检查更新失败（{name}）：{error}", 'WARNING')
        else:
            state["phase"] = "ready"
            state["error"] = ""
            state["plan"] = plan
            if plan.has_changes:
                self.log_manager.log(f"{name}：{plan.summary()}", 'INFO',
                                     verbose=True)
        self._refresh_preset_cards()

        if name in self._online_recheck:
            self._online_recheck.discard(name)
            self._online_check(name)
            return

        pending = self.online_pending.pop(name, "")
        if pending == "sync" and error is None:
            # 一路走到一键同步：这里再弹「要更新哪些」就又绕回去了
            self._sync_now(name)
        elif pending == "publish" and error is None:
            if bool(getattr(self.settings, "online_publish_preview", False)):
                self.open_publish_dialog(name)
            else:
                self._publish_now(name)
        elif pending == "source":
            self.open_source_dialog(name)
        self._pump_online_queue()

    def _online_check_all(self):
        if self.online is None or not self.preset_manager:
            return
        developer = self.is_developer
        names = [n for n in self.preset_manager.presets
                 if self.online.is_bound(n)
                 or (developer and self.online.cloud_path_of(n))]
        if not names:
            self.toast("还没有预设绑定云端源", "info")
            return
        self.online_queue = list(names)
        self.toast(f"正在检查 {len(names)} 个预设…", "info")
        self._pump_online_queue()

    def _pump_online_queue(self):
        """串行检查，别一次打一堆请求。"""
        while self.online_queue:
            name = self.online_queue.pop(0)
            if name in self.online_checking:
                self.online_queue.append(name)
                return
            if name not in (self.preset_manager.presets
                            if self.preset_manager else {}):
                continue
            self._online_check(name)
            return

    def _online_auto_check(self):
        """启动后台检查（玩家身份 + 绑定了源 + auto_check）。"""
        if self.online is None or self.is_developer or not self.preset_manager:
            return
        names = []
        for name in self.preset_manager.presets:
            source = self.online.source_of(name)
            if not (source.get("lanzou") or {}).get("url"):
                continue
            default_auto = bool(getattr(self.settings, "online_auto_check",
                                        True))
            if not source.get("auto_check", default_auto):
                continue
            names.append(name)
        if not names:
            return
        self.online_queue = names
        self._pump_online_queue()

    # ==================================================================
    # 从云端添加预设
    # ==================================================================
    def open_add_from_cloud(self):
        """新玩家没有本地预设时，直接从分享链接建一个。"""
        if self.online is None or self.preset_manager is None:
            show_warning("还没加载整合包", "先选一个整合包根目录，再添加云端预设。")
            return
        card = make_card(self, None, width=540)
        card.add_title("从云端添加预设")
        card.add_subtitle("粘贴发布者给的分享链接和密码，读到的预设会直接建在本地。")

        url_var = StringVar(value=_clipboard_link(self.root))
        pwd_var = StringVar(value="")
        form = ctk.CTkFrame(card.body, fg_color="transparent")
        form.pack(fill=X, pady=(PAD_TIGHT, 0))

        url_field = FormField(
            form, "分享链接", textvariable=url_var,
            placeholder="https://xxx.lanzoul.com/b0123456",
            hint="在蓝奏云「分享」里复制；剪贴板里有链接时会自动填好")
        url_field.frame.pack(fill=X)
        pwd_field = FormField(
            form, "分享密码", textvariable=pwd_var,
            placeholder="没有密码就留空", hint="发布者给的 4 位提取码")
        pwd_field.frame.pack(fill=X, pady=(PAD_GAP, 0))

        status = make_label(form, text=" ", fg=C_TEXT_MUTED, font_size=FS_TINY)
        status.pack(anchor=W, pady=(PAD_TIGHT, 0))

        bar = self._dialog_bar(card)
        make_button(bar, "取消", command=lambda: card.close(False)).pack(side=RIGHT)
        add_btn = make_button(bar, "读取并创建", accent=True,
                              command=lambda: do_inspect())
        add_btn.pack(side=RIGHT, padx=(0, PAD_TIGHT))

        state = {"busy": False}

        def fail(message):
            state["busy"] = False
            add_btn.configure(state="normal", text="读取并创建")
            url_field.set_enabled(True)
            pwd_field.set_enabled(True)
            status.configure(text=message, text_color=C_ERROR)

        def do_inspect(event=None):
            if state["busy"]:
                return "break"
            url = url_var.get().strip()
            url_field.ok()
            if not url:
                url_field.focus()
                url_field.error("先填分享链接")
                return "break"
            if "lanzou" not in url.lower():
                url_field.error("这不像蓝奏云的分享链接")
                return "break"
            state["busy"] = True
            add_btn.configure(state="disabled", text="正在读取…")
            url_field.set_enabled(False)
            pwd_field.set_enabled(False)
            status.configure(text="正在读取云端 manifest…", text_color=C_ACCENT)
            service = self.online
            # 主线程里先把输入读出来：Tk 变量不能在工作线程里 get()
            password = pwd_var.get()

            def worker():
                try:
                    info = service.inspect_share(url, password)
                    ui_call(self.root, self._on_inspect_share, card, info,
                            url, password, None)
                except OnlineError as exc:
                    ui_call(self.root, fail, str(exc))

            threading.Thread(target=worker, daemon=True).start()
            return "break"

        card.register_focusable(url_field.entry)
        card.register_focusable(pwd_field.entry)
        card.register_focusable(add_btn)
        url_field.entry.bind("<Return>", lambda e: pwd_field.focus())
        pwd_field.entry.bind("<Return>", do_inspect)
        url_field.focus()

    def _on_inspect_share(self, card, info, url, password, error):
        try:
            card.close(True)
        except Exception:
            pass
        if error is not None:
            show_error("读取失败", str(error))
            return
        name = safe_preset_name(info.get("name"), "云端预设")
        if name != str(info.get("name") or "").strip():
            self.log_manager.log(
                f"云端预设名不合法，已改为「{name}」", 'WARNING')
        if name in (self.preset_manager.presets if self.preset_manager else {}):
            show_warning("预设已存在",
                         f"本地已经有「{name}」了。\n"
                         f"想更新它的话，打开它的「来源」填这个链接即可。")
            return
        version = str(info.get("version") or "").strip()
        if version and not version.lower().startswith("v"):
            version = f"v{version}"
        version = version or "v1.0.0"
        if not self.preset_manager.create_preset(name, version):
            show_error("创建失败", f"没能创建预设「{name}」")
            return
        self.preset_manager.load_all_presets(use_cache=False)
        self._update_preset_list()
        self.preset_cards.select(name, notify=False)
        self.on_preset_selected(name)
        self.online.bind(name, url, password, auto_check=True)
        self.log_manager.log(
            f"已从云端添加预设「{name}」：{info.get('files', 0)} 个文件 · "
            f"{_human_size(info.get('total_bytes'))}", 'SUCCESS')
        self.toast(f"已添加「{name}」，准备同步", "success")
        self.online_states.pop(name, None)
        self._online_check(name, pending="sync")

    # ==================================================================
    # 来源绑定
    # ==================================================================
    def open_source_dialog(self, name: str):
        """保留旧入口：统一跳到详情页的「来源」——那里能直接填，不用再开一层弹窗。"""
        self.open_preset_detail(name, tab="source")

    def _save_source(self, name, url, password="", cloud_path="",
                     auto_check=True, fallback_url="", fallback_password=""):
        """保存来源并立刻检查一次（弹窗与测试共用）。"""
        if self.online is None:
            return False
        try:
            if url:
                self.online.bind(name, url, password, cloud_path=cloud_path,
                                 auto_check=bool(auto_check),
                                 fallback_url=fallback_url,
                                 fallback_password=fallback_password)
            elif cloud_path:
                self.online.set_cloud_path(name, cloud_path)
            else:
                return False
        except OnlineError as exc:
            show_error("保存失败", str(exc))
            return False
        self.log_manager.log(f"预设「{name}」的来源已保存", 'SUCCESS')
        self.toast("来源已保存", "success")
        self.online_states.pop(name, None)
        self._refresh_preset_cards()
        self._online_check(name, prompt=False)
        return True

    # ==================================================================
    # 预设详情（概览 / 枪包 / 来源 / 记录）
    # ==================================================================
    def open_preset_detail(self, name: str, tab: str = "overview"):
        """预设详情。tab 可以指定打开时停在哪一页（来源页现在能直接填链接）。"""
        info = (self.preset_manager.presets.get(name)
                if self.preset_manager else None)
        if not info:
            return
        card = make_card(self, None, width=720)
        card.add_title(name)

        tabs_items = [("overview", "概览"), ("packs", "枪包"),
                      ("source", "来源")]
        if self.is_developer:
            tabs_items.append(("history", "记录"))
        holder = ctk.CTkFrame(card.body, fg_color="transparent")
        holder.pack(fill=X, pady=(0, PAD_TIGHT))
        body = ctk.CTkFrame(card.body, fg_color="transparent")
        body.pack(fill=BOTH, expand=True)

        pages: dict[str, ctk.CTkFrame] = {}
        current = {"key": ""}

        def show(key):
            if current["key"] == key:
                return
            current["key"] = key
            for page in pages.values():
                page.pack_forget()
            page = pages.get(key)
            if page is None:
                page = self._build_detail_page(key, name, info, body)
                pages[key] = page
            page.pack(fill=BOTH, expand=True)

        tab_bar = CanvasSegmented(
            holder, tabs_items, command=show, orientation="horizontal",
            item_height=H_CONTROL, pad=8, gap=6, radius=R_CONTROL,
            bg_color=C_PANEL_BG, pill_color=C_ACCENT,
            hover_color=C_ACCENT_SOFT, text_color=C_TEXT_SECONDARY,
            active_text_color=C_TEXT_INVERSE, font_size=FS_BODY,
            bold_active=True, text_anchor="center", duration_ms=240)
        tab_bar.pack(fill=X, padx=PAD_XS, pady=PAD_XS)

        bar = self._dialog_bar(card)
        make_button(bar, "关闭", command=lambda: card.close(True)).pack(side=RIGHT)
        if self.is_developer:
            make_button(bar, "发布…",
                        command=lambda: (card.close(True),
                                         self.open_publish_dialog(name))).pack(
                side=RIGHT, padx=(0, PAD_TIGHT))
        else:
            make_button(bar, "同步…",
                        command=lambda: (card.close(True),
                                         self.open_sync_dialog(name))).pack(
                side=RIGHT, padx=(0, PAD_TIGHT))
        show(tab if any(k == tab for k, _ in tabs_items) else "overview")

    def _build_detail_page(self, key: str, name: str, info: dict,
                           parent):
        builders = {"overview": self._detail_overview,
                    "packs": self._detail_packs,
                    "source": self._detail_source,
                    "history": self._detail_history}
        return builders.get(key, self._detail_overview)(parent, name, info)

    def _detail_overview(self, parent, name, info):
        page = ctk.CTkFrame(parent, fg_color="transparent")

        # ===== 名称 / 版本：直接在这里改 =====
        meta = ctk.CTkFrame(page, fg_color="transparent")
        meta.pack(fill=X, pady=(0, PAD_GAP))
        name_var = StringVar(value=name)
        ver_var = StringVar(value=str(info.get("version") or ""))
        name_field = FormField(meta, "预设名称", textvariable=name_var,
                               hint="改名后列表立即更新")
        name_field.frame.pack(fill=X)
        ver_field = FormField(meta, "版本号", textvariable=ver_var,
                              hint="发布到云端时用这个版本号")
        ver_field.frame.pack(fill=X, pady=(PAD_TIGHT, 0))

        def save_meta():
            new_name = str(name_var.get() or "").strip()
            new_ver = str(ver_var.get() or "").strip()
            manager = self.preset_manager
            if not manager:
                return
            if not new_name:
                name_field.focus()
                name_field.error("名字不能为空")
                return
            if new_name != name and new_name in manager.presets:
                name_field.focus()
                name_field.error("这个名字已经存在")
                return
            target = name
            if new_name != name:
                if not manager.rename_preset(name, new_name):
                    name_field.error("改名失败")
                    return
                self._after_rename_preset(name, new_name)
                target = new_name
                if getattr(self, "current_selected_preset", None) == name:
                    self.current_selected_preset = new_name
            if new_ver and new_ver != str(info.get("version") or ""):
                try:
                    manager.update_preset_version(target, new_ver)
                except Exception:
                    pass
            try:
                self._update_preset_list()
            except Exception:
                pass
            # 详情条的版本/名称也要跟着变，否则改完还是显示旧版本
            try:
                if target == getattr(self, "current_selected_preset", None):
                    self.on_preset_selected(target)
            except Exception:
                pass
            try:
                _OVERLAY_STACK[-1].close(True)
            except Exception:
                pass
            self.toast("已保存", "success")

        make_button(meta, "保存修改", command=save_meta, accent=True,
                    width=96).pack(anchor=W, pady=(PAD_TIGHT, 0))
        count, size = self._preset_size(name, info)
        state = self._online_state(name)
        plan = state.get("plan")
        source = (self.online.source_of(name) if self.online else {}) or {}
        lanzou = source.get("lanzou") or {}

        if self.online is not None and self.online.is_bound(name):
            source_text = lanzou.get("url") or "已绑定"
        elif self.is_developer and source.get("cloud_path"):
            source_text = source.get("cloud_path")
        else:
            source_text = "未绑定"

        rows = [
            ("版本", str(info.get("version") or "v1.0.0")),
            ("状态", "已应用" if info.get("applied") else "未应用"),
            ("枪包", f"{count} 个 · {_human_size(size)}"),
            ("云端源", source_text),
            ("上次检查", _time_ago(state.get("checked_at")) or "还没有检查"),
        ]
        if plan is not None:
            rows.append(("差异", plan.summary()))

        grid = ctk.CTkFrame(page, fg_color="transparent")
        grid.pack(fill=X)
        grid.grid_columnconfigure(1, weight=1)
        for index, (label, value) in enumerate(rows):
            make_label(grid, text=label, fg=C_TEXT_MUTED,
                       font_size=FS_TINY).grid(row=index, column=0, sticky="w",
                                               pady=(0, PAD_TIGHT))
            make_label(grid, text=value, fg=C_TEXT_MAIN,
                       font_size=FS_SMALL).grid(row=index, column=1, sticky="w",
                                                padx=(PAD_CARD_X, 0),
                                                pady=(0, PAD_TIGHT))

        actions = ctk.CTkFrame(page, fg_color="transparent")
        actions.pack(fill=X, pady=(PAD_TIGHT, 0))
        make_button(actions, "检查更新",
                    command=lambda: self._online_check(name)).pack(side=LEFT)
        if self.is_developer:
            # 诊断 / 重扫差异是排障用的，玩家不需要考虑
            make_button(actions, "诊断",
                        command=lambda: self.open_diagnose_dialog(name)).pack(
                side=LEFT, padx=(PAD_TIGHT, 0))
            make_button(actions, "扫描差异",
                        command=lambda: self._online_check(name),
                        accent=True).pack(side=LEFT, padx=(PAD_TIGHT, 0))
        return page

    def _detail_packs(self, parent, name, info):
        page = ctk.CTkFrame(parent, fg_color="transparent")
        listing = InfoList(page, height=240, empty_text="这个预设还没有枪包")
        listing.pack(fill=BOTH, expand=True)

        plan = self._online_state(name).get("plan")
        rows = []
        if plan is not None:
            for item in plan.items:
                color = ACTION_COLORS.get(item.action, C_TEXT_MUTED)
                rows.append({
                    "name": item.display_name,
                    "tag": online_diff.ACTION_LABELS.get(item.action, ""),
                    "color": color,
                    "size": item.size,
                    "subtitle": item.reason,
                })
        else:
            gunpacks = info.get("gunpacks") or {}
            for pack_name, fingerprint in sorted(gunpacks.items()):
                kind = "文件夹" if fingerprint.get("type") == "folder" else "枪包"
                rows.append({"name": pack_name, "tag": kind,
                             "color": C_TEXT_MUTED,
                             "size": int(fingerprint.get("size") or 0)})
        listing.set_rows(rows)
        return page

    def _detail_source(self, parent, name, info):
        """来源页：直接在这里填 / 改链接，不用再跳一层弹窗。"""
        page = ctk.CTkFrame(parent, fg_color="transparent")
        source = (self.online.source_of(name) if self.online else {}) or {}
        lanzou = source.get("lanzou") or {}
        fallback = lanzou.get("fallback") or {}
        if not isinstance(fallback, dict):
            fallback = {}

        url_var = StringVar(value=lanzou.get("url") or "")
        pwd_var = StringVar(value=lanzou.get("password") or "")
        path_var = StringVar(value=source.get("cloud_path") or "")
        auto_var = BooleanVar(value=bool(source.get("auto_check", True)))
        fb_url_var = StringVar(value=fallback.get("url") or "")
        fb_pwd_var = StringVar(value=fallback.get("password") or "")

        url_field = FormField(
            page, "分享链接" if not self.is_developer else "分享链接（玩家用）",
            textvariable=url_var,
            placeholder="https://xxx.lanzoul.com/b0123456",
            hint=("玩家同步靠它；开发者可以留空，发布成功后会自己填上"
                  if not self.is_developer
                  else "开发者不需要填，发布后自动生成"))
        url_field.frame.pack(fill=X)

        pwd_field = FormField(
            page, "分享密码", textvariable=pwd_var, password=True,
            placeholder="没有密码就留空")
        pwd_field.frame.pack(fill=X, pady=(PAD_TIGHT, 0))

        if self.is_developer:
            path_field = FormField(
                page, "云端路径（发布用，必填）", textvariable=path_var,
                placeholder="test 或 /PulsesSwap/预设名",
                hint="网盘里的文件夹路径；写 test 就传到根目录的 test 里，不存在会自动建")
            path_field.frame.pack(fill=X, pady=(PAD_TIGHT, 0))
        else:
            path_field = None

        # 备用链接：默认收起，配过才展开
        fb_toggle = ctk.CTkButton(
            page, text="＋ 备用链接（主链接失效时自动降级）",
            anchor="w", height=22, width=1,
            fg_color="transparent", hover_color=C_PANEL_ALT_BG,
            text_color=C_TEXT_MUTED, corner_radius=4,
            font=(config.FONT_FAMILY, FS_TINY, "bold"))
        fb_toggle.pack(fill=X, pady=(PAD_TIGHT, 0))
        fb_box = ctk.CTkFrame(page, fg_color="transparent")
        fb_row = ctk.CTkFrame(fb_box, fg_color="transparent")
        fb_row.pack(fill=X)
        fb_row.grid_columnconfigure(0, weight=1)
        make_entry(fb_row, textvariable=fb_url_var,
                   placeholder="备用分享链接").grid(row=0, column=0, sticky="ew")
        make_entry(fb_row, textvariable=fb_pwd_var, width=96,
                   placeholder="密码").grid(row=0, column=1, padx=(PAD_TIGHT, 0))

        fb_open = {"value": False}

        def toggle_fallback():
            fb_open["value"] = not fb_open["value"]
            label = "备用链接（主链接失效时自动降级）"
            if fb_open["value"]:
                fb_box.pack(fill=X, pady=(PAD_TIGHT, 0))
                fb_toggle.configure(text="－ " + label)
            else:
                fb_box.pack_forget()
                fb_toggle.configure(text="＋ " + label)

        fb_toggle.configure(command=toggle_fallback)
        if fb_url_var.get().strip():
            toggle_fallback()

        opts = ctk.CTkFrame(page, fg_color="transparent")
        opts.pack(fill=X, pady=(PAD_TIGHT, 0))
        make_checkbox(opts, "启动时自动检查更新", auto_var).pack(side=LEFT)

        status = make_label(page, text=" ", fg=C_TEXT_MUTED, font_size=FS_TINY)
        status.pack(anchor=W, pady=(PAD_TIGHT, 0))

        # 保存后检查是在后台跑的：这张页自己盯着状态，别让"正在检查"一直挂着
        shown = {"key": None}

        def watch():
            try:
                if not status.winfo_exists():
                    return
            except Exception:
                return
            try:
                st = self._online_state(name)
                phase = str(st.get("phase") or "")
                if phase:
                    key = (phase, id(st.get("plan")),
                           str(st.get("phase_text") or ""))
                    if key != shown["key"]:
                        shown["key"] = key
                        if phase == "checking":
                            status.configure(
                                text=str(st.get("phase_text") or "检查中…"),
                                text_color=C_ACCENT)
                        elif phase == "error":
                            status.configure(
                                text=f"连接失败：{st.get('error') or '未知原因'}",
                                text_color=C_ERROR)
                        elif phase == "ready":
                            summary = self._check_summary(name)
                            if summary:
                                status.configure(
                                    text=summary,
                                    text_color=C_SUCCESS
                                    if summary.startswith(("云端", "已"))
                                    else C_WARNING)
            except Exception:
                pass
            try:
                status.after(700, watch)
            except Exception:
                pass

        try:
            status.after(700, watch)
        except Exception:
            pass

        actions = ctk.CTkFrame(page, fg_color="transparent")
        actions.pack(fill=X)

        state = {"busy": False}

        def set_busy(busy, note=""):
            state["busy"] = busy
            for widget in (test_btn, save_btn):
                try:
                    widget.configure(state="disabled" if busy else "normal")
                except Exception:
                    pass
            try:
                test_btn.configure(text="测试中…" if busy else "测试连接")
            except Exception:
                pass
            if note:
                status.configure(text=note, text_color=C_ACCENT)

        def save(event=None):
            if state["busy"]:
                return "break"
            url = url_var.get().strip()
            url_field.ok()
            if not url and not (self.is_developer and path_var.get().strip()):
                url_field.focus()
                url_field.error("填一个分享链接或云端路径")
                return "break"
            self._save_source(name, url, pwd_var.get(),
                              (path_var.get().strip() if path_field else ""),
                              bool(auto_var.get()),
                              fb_url_var.get().strip(), fb_pwd_var.get())
            status.configure(text="已保存，正在检查云端…", text_color=C_SUCCESS)
            return "break"

        def test(event=None):
            if state["busy"]:
                return "break"
            url = url_var.get().strip()
            path = path_var.get().strip() if path_field else ""
            url_field.ok()
            # 开发者只需要云端路径：没有分享链接时测「文件夹连不连得上」
            cloud_only = bool(self.is_developer and path and not url)
            if not url and not cloud_only:
                url_field.focus()
                url_field.error("先填分享链接")
                return "break"
            set_busy(True, "正在连接云端…")

            def done(info, error):
                set_busy(False)
                if error is not None:
                    status.configure(text=str(error), text_color=C_ERROR)
                    return
                if info.get("path"):
                    text = (f"连接成功 · {info['path']} · "
                            f"{info['files']} 个文件")
                    if not info.get("has_manifest"):
                        text += " · 还没有发布内容"
                    status.configure(text=text,
                                     text_color=C_SUCCESS if info.get("has_manifest")
                                     else C_INFO)
                    self.log_manager.log(text, 'INFO')
                    return
                if info.get("manifest_ok"):
                    text = (f"连接成功 · {info['count']} 个文件 · "
                            f"{_human_size(info['total_bytes'])} · 已发布")
                    color = C_SUCCESS
                elif info.get("has_manifest"):
                    text = "能连上，但云端 manifest 读不出来"
                    color = C_WARNING
                else:
                    text = f"能连上 · {info['count']} 个文件 · 还没有发布内容"
                    color = C_INFO
                status.configure(text=text, text_color=color)
                self.log_manager.log(text, 'INFO')

            # 同上：Tk 变量只在主线程读一次
            test_password = pwd_var.get()

            def worker():
                try:
                    if cloud_only:
                        info = self.online.test_cloud_path(path)
                    else:
                        info = self.online.test_source(url, test_password)
                    ui_call(self.root, done, info, None)
                except OnlineError as exc:
                    ui_call(self.root, done, None, exc)

            threading.Thread(target=worker, daemon=True).start()
            return "break"

        test_btn = make_text_button(actions, "测试连接", command=test)
        test_btn.pack(side=LEFT)

        if self.is_developer:
            def clear_source():
                if not ask_yes_no(
                        "清除云端绑定",
                        "会清掉这个预设的云端路径和分享链接（不影响本地/云端文件）。\n"
                        "之后需要重新填写才能发布。"):
                    return
                try:
                    self.online.clear_source(name)
                except Exception as exc:
                    show_error("清除失败", str(exc))
                    return
                path_var.set("")
                url_var.set("")
                pwd_var.set("")
                self.online_states.pop(name, None)
                self._update_preset_list()
                status.configure(text="已清除云端绑定", text_color=C_SUCCESS)

            make_text_button(actions, "清除云端绑定",
                             command=clear_source).pack(side=LEFT,
                                                        padx=(PAD_TIGHT, 0))
        save_btn = make_button(actions, "保存", command=save, accent=True,
                                width=76)
        save_btn.pack(side=LEFT, padx=(PAD_TIGHT, 0))
        for field in (url_field, pwd_field):
            field.entry.bind("<Return>", save)
        return page

    def _detail_history(self, parent, name, info):
        page = ctk.CTkFrame(parent, fg_color="transparent")
        listing = InfoList(page, height=240, empty_text="还没有发布记录")
        listing.pack(fill=BOTH, expand=True)
        records = self.online.publish_history(name) if self.online else []
        rows = []
        for record in records:
            stamp = record.get("at")
            when = (datetime.fromtimestamp(stamp).strftime("%Y-%m-%d %H:%M")
                    if stamp else "")
            rows.append({
                "name": f"v{record.get('version') or '?'}",
                "tag": f"#{record.get('generation') or 0}",
                "color": C_ACCENT,
                "size": int(record.get("bytes") or 0),
                "subtitle": f"{when} · 上传 {record.get('uploaded') or 0} 项",
            })
        listing.set_rows(rows)
        return page

    # ==================================================================
    # 诊断
    # ==================================================================
    def open_diagnose_dialog(self, name: str):
        """把"能不能同步"拆成一条条结果，失败时能一眼看出卡在哪。"""
        if self.online is None:
            show_warning("在线功能不可用", "在线模块没有加载成功。")
            return
        ref = self._preset_ref(name)
        if ref is None:
            return
        card = make_card(self, None, width=560)
        card.add_title(f"诊断 · {name}")
        status = make_label(card.body, text="正在检查…", fg=C_TEXT_SECONDARY,
                            font_size=FS_SMALL)
        status.pack(anchor=W, pady=(PAD_TIGHT, PAD_TIGHT))
        listing = InfoList(card.body, height=200, empty_text="等待结果")
        listing.pack(fill=BOTH, expand=True)
        bar = self._dialog_bar(card)
        make_button(bar, "关闭", command=lambda: card.close(True)).pack(side=RIGHT)

        service = self.online
        role = "developer" if self.is_developer else "player"

        def worker():
            try:
                result = service.diagnose(ref, role=role, deep=True)
                ui_call(self.root, self._on_diagnose_done, card, name, result,
                        None)
            except Exception as exc:                    # noqa: BLE001
                ui_call(self.root, self._on_diagnose_done, card, name, None,
                        exc)

        threading.Thread(target=worker, daemon=True).start()

    def _on_diagnose_done(self, card, name, result, error):
        if error is not None:
            try:
                card.close(False)
            except Exception:
                pass
            show_error("诊断失败", str(error))
            return
        try:
            listing = None
            for child in card.body.winfo_children():
                if isinstance(child, InfoList):
                    listing = child
                    break
            if listing is not None:
                rows = []
                for item in result.get("checks") or []:
                    rows.append({
                        "name": item["name"],
                        "tag": "通过" if item["ok"] else "异常",
                        "color": C_SUCCESS if item["ok"] else C_ERROR,
                        "size": 0,
                        "subtitle": item.get("detail") or "",
                    })
                listing.set_rows(rows)
            ok = bool(result.get("ok"))
            for child in card.body.winfo_children():
                if isinstance(child, ctk.CTkLabel) and \
                        str(child.cget("text")).startswith(("正在检查", "全部通过",
                                                            "发现问题")):
                    child.configure(
                        text="全部通过" if ok else "发现问题（见下面标红的项）",
                        text_color=C_SUCCESS if ok else C_ERROR)
                    break
        except Exception:
            pass
        ok = bool(result.get("ok"))
        for item in result.get("checks") or []:
            self.log_manager.log(
                f"诊断 · {name} · {item['name']}："
                f"{'通过' if item['ok'] else '异常'} {item.get('detail') or ''}",
                'INFO' if item["ok"] else 'WARNING', verbose=True)
        self.toast("诊断完成：全部通过" if ok else "诊断完成：发现问题",
                   "success" if ok else "warning")

    # ==================================================================
    # 同步
    # ==================================================================
    def _set_online_busy(self, busy: bool) -> None:
        self.online_busy = bool(busy)

    def _sync_now(self, name: str) -> None:
        """玩家点「更新」= 直接同步，不再弹「要更新哪些」的选择框。

        勾选策略放在设置里（同步时是否清理本地多余），默认只拉需要的东西；
        单个文件的取舍对普通玩家没有意义，问一次就是多一次操作。
        """
        if self.online is None:
            return
        # 玩家第一次从云端拉取时，预设必然是空的、也没法「先应用再更新」；
        # 「先应用才能执行」只约束开发者的发布。同步本身写的是预设目录
        # （已应用时写 tacz），两种状态都安全。
        if getattr(self, "is_applying", False):
            self.toast("正在替换枪包，完成后再更新", "warning")
            return
        state = self._online_state(name)
        plan = state.get("plan")
        if plan is None:
            self._online_check(name, pending="sync")
            self.toast("正在检查更新…", "info")
            return
        if getattr(plan, "blocked", None):
            show_warning("无法更新", plan.blocked[0])
            return
        if getattr(plan, "offline", False):
            self.toast("云端连不上，无法更新；先检查网络", "warning")
            return
        if not plan.has_changes:
            self.toast("已经是最新版本", "success")
            return
        clean = bool(getattr(self.settings, "online_sync_clean", False))
        selection = online_diff.selection_of(plan, include_deletes=clean)
        if not selection:
            self.toast("没有需要下载的内容", "info")
            return
        self._run_sync(name, plan, selection)

    def open_sync_dialog(self, name: str):
        if self.online is None:
            show_warning("在线功能不可用", "在线模块没有加载成功。")
            return
        if getattr(self, "is_applying", False):
            self.toast("正在替换枪包，完成后再更新", "warning")
            return
        state = self._online_state(name)
        plan = state.get("plan")
        if plan is None:
            self._online_check(name, pending="sync")
            self.toast("正在检查更新…", "info")
            return
        if getattr(plan, "blocked", None):
            show_warning("无法同步", plan.blocked[0])
            return
        if not plan.has_changes:
            self.toast("已经是最新版本", "success")
            return

        card = make_card(self, None, width=680)
        card.add_title(f"同步 · {name}")
        subtitle = (f"云端 v{plan.cloud_version or '未标注'} · "
                    f"generation {plan.cloud_generation}")
        if getattr(plan, "offline", False):
            subtitle += " · 离线（用的是上次缓存）"
        card.add_subtitle(subtitle)

        listing = DiffList(card.body, height=260)
        listing.pack(fill=BOTH, expand=True, pady=(PAD_TIGHT, 0))
        listing.set_items(plan.items)

        if plan.cloud_notes:
            card.add_text(f"更新说明：{plan.cloud_notes}",
                          fg=C_TEXT_SECONDARY, font_size=FS_TINY)

        bar = self._dialog_bar(card)
        make_button(bar, "取消", command=lambda: card.close(False)).pack(side=RIGHT)

        def start():
            selection = listing.selection()
            if not selection:
                self.toast("没有勾选任何项目", "info")
                return
            card.close(True)
            self._run_sync(name, plan, selection)

        make_button(bar, "开始同步", command=start, accent=True).pack(
            side=RIGHT, padx=(0, PAD_TIGHT))

    def _run_sync(self, name: str, plan, selection):
        ref = self._preset_ref(name)
        if ref is None:
            return
        card = make_card(self, None, width=560)
        card.add_title(f"正在同步 · {name}")
        panel = self._build_progress_panel(card.body)
        cancel_flag = {"stop": False}

        def do_cancel():
            cancel_flag["stop"] = True
            cancel_btn.configure(state="disabled", text="正在停止…")

        cancel_btn = make_button(panel["buttons"], "取消", command=do_cancel)
        cancel_btn.pack(side=RIGHT)
        panel["buttons"].pack(fill=X, pady=(PAD_DIALOG, 0))

        throttle = {"last": 0.0}

        def on_progress(done, total, index, count, entry):
            now = time.time()
            if now - throttle["last"] < 0.08 and done < total:
                return
            throttle["last"] = now
            ui_call(self.root, panel["update"], done, total, index, count,
                    str(entry.get("path") or ""))

        def on_item(index, total, entry, phase):
            if phase == "start":
                ui_call(self.root, panel["stage"],
                        f"[{index}/{total}] {entry.get('path')}")

        service = self.online
        self._set_online_busy(True)
        self.set_busy_state(True, "同步")

        def worker():
            try:
                result = service.sync(
                    ref, plan, selection, on_item=on_item,
                    on_progress=on_progress,
                    cancel=lambda: cancel_flag["stop"])
                ui_call(self.root, self._on_sync_done, card, name, result, None)
            except OnlineCancelled:
                ui_call(self.root, self._on_sync_done, card, name, None, None)
            except OnlineError as exc:
                ui_call(self.root, self._on_sync_done, card, name, None, exc)
            except Exception as exc:                    # noqa: BLE001
                ui_call(self.root, self._on_sync_done, card, name, None,
                        OnlineError(f"同步失败：{exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _on_sync_done(self, card, name, result, error):
        self._set_online_busy(False)
        self.set_busy_state(False, "")
        self._last_sync_result = result
        if card is not None:
            try:
                card.close(True)
            except Exception:
                pass
        if error is not None:
            show_error("同步失败", str(error))
            self.log_manager.log(f"同步失败（{name}）：{error}", 'ERROR')
            return
        if result is None:
            self.toast("已取消同步", "info")
            return
        if result.failed:
            detail = "\n".join(f"· {path}：{reason}"
                               for path, reason in result.failed[:6])
            show_warning("部分文件同步失败",
                         f"{result.summary()}\n\n{detail}")
        elif result.cancelled:
            self.toast("已取消同步", "info")
        else:
            self.toast(f"同步完成 · {result.summary()}", "success")
        self.log_manager.log(f"同步完成（{name}）：{result.summary()}",
                             'SUCCESS' if result.ok else 'WARNING')
        self._after_preset_changed(name)

    def _after_preset_changed(self, name: str):
        """同步/发布之后：重读预设、刷新卡片与详情。"""
        self._preset_size_cache.pop(name, None)
        try:
            if self.preset_manager:
                # 先重读 index.json：同步成功时 service._finish 已经把云端版本
                # 写进去了；先 reindex 会拿内存里的旧版本把它覆盖回去。
                self.preset_manager.reload_preset(name)
        except Exception:
            pass
        try:
            info = ((self.preset_manager.presets.get(name) or {})
                    if self.preset_manager else {})
            # 已应用的预设，内容真相在 tacz：按 tacz 重算枪包指纹，
            # 否则卡片还显示旧的枪包数，启动时还会误报「多余/变更」。
            if info.get("applied"):
                self.preset_manager.update_preset_index(name, from_tacz=True)
        except Exception:
            pass
        self.online_states.pop(name, None)
        self._update_preset_list()
        cards = getattr(self, "preset_cards", None)
        if cards is not None:
            cards.flash(name)
        if self.current_selected_preset == name:
            self.on_preset_selected(None)
        self._online_check(name)

    # ==================================================================
    # 发布
    # ==================================================================
    def _online_guard_applied(self, name: str, action: str) -> bool:
        """上传 / 更新前必须先应用该预设：云端的"真相"就是当前 tacz 里的内容。"""
        info = {}
        try:
            info = (self.preset_manager.presets.get(name) or {})
        except Exception:
            pass
        if info.get("applied"):
            return True
        self.toast(f"先应用「{name}」再{action}", "warning")
        try:
            show_warning(
                f"先应用这个预设",
                f"「{name}」还没有应用到 TACZ。\n\n"
                f"请先选它并点「一键替换」，把枪包换进 tacz 之后再{action}——\n"
                f"否则云端内容和本地实际状态对不上。")
        except Exception:
            pass
        return False

    def _preset_version_of(self, name: str) -> str:
        """发布用预设自己的版本号（开发者可在一键替换右侧改）。"""
        try:
            version = str((self.preset_manager.presets.get(name) or {})
                          .get("version") or "").strip()
        except Exception:
            version = ""
        if not version:
            version = datetime.now().strftime("v%Y.%m.%d")
        if not version.lower().startswith("v"):
            version = f"v{version}"
        return version

    def _publish_now(self, name: str) -> None:
        """开发者点「发布到云端」= 直接发，不再弹差异清单。

        要逐项确认可以在设置里打开「发布前预览」。
        """
        if self.online is None:
            return
        if getattr(self, "is_applying", False) or getattr(self, "online_busy", False):
            self.toast("正在处理，完成后再发布", "warning")
            return
        if not self._online_guard_applied(name, "发布"):
            return
        state = self._online_state(name)
        plan = state.get("plan")
        if plan is None:
            self._online_check(name, pending="publish")
            self.toast("正在检查云端…", "info")
            return
        if getattr(plan, "blocked", None):
            show_warning("无法发布", plan.blocked[0])
            return
        if getattr(plan, "offline", False):
            show_warning("云端连不上",
                         "这次计划来自上次的缓存，可能已经过时。\n"
                         "先检查网络，重新检查云端后再发布。")
            return
        selection = online_diff.selection_of(plan, include_deletes=True)
        if not plan.has_changes or not selection:
            self.toast("云端已是最新", "success")
            return
        # 一键发布沿用上次的更新说明/最低版本，不静默清空
        source = (self.online.source_of(name) if self.online else {}) or {}
        self._run_publish(name, plan, selection,
                          self._preset_version_of(name),
                          str(source.get("last_notes") or ""),
                          str(source.get("last_min_app") or ""))

    def open_publish_dialog(self, name: str):
        if self.online is None:
            show_warning("在线功能不可用", "在线模块没有加载成功。")
            return
        if not self.is_developer:
            self.open_identity_dialog()
            return
        if not self._online_guard_applied(name, "发布"):
            return
        if not self.online.has_account():
            self.open_identity_dialog()
            return
        if not self.online.cloud_path_of(name):
            self.toast("先填云端路径", "info")
            self.open_source_dialog(name)
            return

        state = self._online_state(name)
        plan = state.get("plan")
        if plan is None:
            self._online_check(name, pending="publish")
            self.toast("正在扫描差异…", "info")
            return
        if getattr(plan, "offline", False):
            show_warning("云端连不上",
                         "这次计划来自上次的缓存，可能已经过时。\n"
                         "先检查网络，重新检查云端后再发布。")
            return

        card = make_card(self, None, width=680)
        card.add_title(f"发布 · {name}")
        card.add_subtitle(
            f"云端当前 generation {plan.cloud_generation}，"
            f"发布后变成 {plan.cloud_generation + 1}。")

        form = ctk.CTkFrame(card.body, fg_color="transparent")
        form.pack(fill=X, pady=(PAD_TIGHT, PAD_TIGHT))
        source = (self.online.source_of(name) if self.online else {}) or {}
        version_var = StringVar(value=self._preset_version_of(name))
        notes_var = StringVar(value=str(source.get("last_notes") or ""))
        min_app_var = StringVar(value=str(source.get("last_min_app") or ""))

        row = ctk.CTkFrame(form, fg_color="transparent")
        row.pack(fill=X)
        make_label(row, text="版本号", fg=C_TEXT_SECONDARY,
                   font_size=FS_SMALL).pack(side=LEFT)
        make_entry(row, textvariable=version_var, width=140).pack(
            side=LEFT, padx=(PAD_TIGHT, PAD_TIGHT))
        make_label(row, text="更新说明", fg=C_TEXT_SECONDARY,
                   font_size=FS_SMALL).pack(side=LEFT)
        make_entry(row, textvariable=notes_var,
                   placeholder="这次改了什么（可留空）").pack(
            side=LEFT, fill=X, expand=True, padx=(PAD_TIGHT, 0))

        row2 = ctk.CTkFrame(form, fg_color="transparent")
        row2.pack(fill=X, pady=(PAD_TIGHT, 0))
        make_label(row2, text="最低程序版本", fg=C_TEXT_SECONDARY,
                   font_size=FS_SMALL).pack(side=LEFT)
        make_entry(row2, textvariable=min_app_var, width=120,
                   placeholder="可留空，例如 2.5.0").pack(
            side=LEFT, padx=(PAD_TIGHT, 0))

        listing = DiffList(card.body, height=240)
        listing.pack(fill=BOTH, expand=True)
        listing.set_items(plan.items)

        bar = self._dialog_bar(card)
        make_button(bar, "取消", command=lambda: card.close(False)).pack(side=RIGHT)

        def preview():
            selection = listing.selection()
            items = plan.selected_items(selection)
            uploads = [i for i in items if i.action == online_diff.UPLOAD]
            deletes = [i for i in items if i.action == online_diff.DELETE_CLOUD]
            total = sum(i.size for i in uploads)
            lines = [f"将上传 {len(uploads)} 项（{_human_size(total)}）",
                     f"将删除云端 {len(deletes)} 项",
                     "最后替换云端 manifest"]
            show_info("发布预演", "\n".join(lines))

        def start():
            selection = listing.selection()
            version = version_var.get().strip() or datetime.now().strftime(
                "v%Y.%m.%d")
            card.close(True)
            self._run_publish(name, plan, selection, version,
                              notes_var.get().strip(),
                              min_app_var.get().strip())

        make_button(bar, "预演", command=preview).pack(side=RIGHT,
                                                       padx=(0, PAD_TIGHT))
        make_button(bar, "开始发布", command=start, accent=True).pack(
            side=RIGHT, padx=(0, PAD_TIGHT))

    def _run_publish(self, name, plan, selection, version, notes,
                     min_app: str = ""):
        # 最底层再守一道：任何入口（卡片/右键/预览）都不能绕过「先应用」
        if not self._online_guard_applied(name, "发布"):
            return
        if getattr(plan, "offline", False):
            show_warning("云端连不上", "计划来自缓存，不能发布；请先重新检查云端。")
            return
        ref = self._preset_ref(name)
        if ref is None:
            return
        card = make_card(self, None, width=560)
        card.add_title(f"正在发布 · {name}")
        panel = self._build_progress_panel(card.body)
        cancel_flag = {"stop": False}

        def do_cancel():
            cancel_flag["stop"] = True
            cancel_btn.configure(state="disabled", text="正在停止…")

        cancel_btn = make_button(panel["buttons"], "取消", command=do_cancel)
        cancel_btn.pack(side=RIGHT)
        panel["buttons"].pack(fill=X, pady=(PAD_DIALOG, 0))

        throttle = {"last": 0.0}

        def on_progress(done, total, entry_name):
            now = time.time()
            if now - throttle["last"] < 0.08 and done < total:
                return
            throttle["last"] = now
            ui_call(self.root, panel["update"], done, total, 0, 0,
                    str(entry_name))

        service = self.online
        self._set_online_busy(True)
        self.set_busy_state(True, "发布")

        def worker():
            try:
                result = service.publish(
                    ref, plan, selection, version=version, notes=notes,
                    min_app=min_app,
                    on_progress=on_progress,
                    cancel=lambda: cancel_flag["stop"])
                ui_call(self.root, self._on_publish_done, card, name, result,
                        None)
            except OnlineCancelled:
                ui_call(self.root, self._on_publish_done, card, name, None, None)
            except OnlineError as exc:
                ui_call(self.root, self._on_publish_done, card, name, None, exc)
            except Exception as exc:                    # noqa: BLE001
                ui_call(self.root, self._on_publish_done, card, name, None,
                        OnlineError(f"发布失败：{exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _on_publish_done(self, card, name, result, error):
        self._set_online_busy(False)
        self.set_busy_state(False, "")
        self._last_publish_result = result
        if card is not None:
            try:
                card.close(True)
            except Exception:
                pass
        if error is not None:
            show_error("发布失败", str(error))
            return
        if result is None:
            self.toast("已取消发布", "info")
            return
        if not result.ok:
            detail = "\n".join(f"· {path}：{reason}"
                               for path, reason in result.failed[:6])
            show_error("发布失败", f"{result.summary()}\n\n{detail}")
            return
        self.log_manager.log(
            f"发布完成（{name}）：v{result.version} · {result.summary()}",
            'SUCCESS')
        self._after_preset_changed(name)
        self._show_share_result(name, result)

    def _show_share_result(self, name, result):
        card = make_card(self, None, width=520)
        card.add_title("发布完成")
        card.add_subtitle(f"v{result.version} · generation {result.generation}"
                          f" · {_human_size(result.bytes_uploaded)}")
        card.add_text(f"上传 {len(result.uploaded)} 项 · "
                      f"{_human_size(result.bytes_uploaded)}",
                      fg=C_TEXT_SECONDARY, font_size=FS_TINY)

        if result.share_url:
            box = ctk.CTkFrame(card.body, fg_color=C_PANEL_ALT_BG,
                               corner_radius=R_CONTROL)
            box.pack(fill=X, pady=(PAD_TIGHT, 0))
            url_label = make_label(box, text=result.share_url,
                                   fg=C_TEXT_MAIN, font_size=FS_SMALL)
            url_label.pack(anchor=W, padx=PAD_INNER, pady=(PAD_INNER, PAD_MICRO))
            pwd_label = make_label(
                box, text=f"密码：{result.share_password or '无'}",
                fg=C_TEXT_SECONDARY, font_size=FS_TINY)
            pwd_label.pack(anchor=W, padx=PAD_INNER, pady=(0, PAD_INNER))

            def copy_share():
                text = result.share_url
                if result.share_password:
                    text += f"  密码：{result.share_password}"
                self._copy(text)
                self.toast("分享信息已复制", "success")

            bar0 = ctk.CTkFrame(card.body, fg_color="transparent")
            bar0.pack(fill=X, pady=(PAD_TIGHT, 0))
            make_button(bar0, "复制分享信息", command=copy_share,
                        accent=True).pack(side=RIGHT)
        else:
            card.add_text("没能取到分享链接，去蓝奏网页版手动复制即可。",
                          fg=C_WARNING, font_size=FS_TINY)

        bar = self._dialog_bar(card)
        make_button(bar, "完成", command=lambda: card.close(True)).pack(side=RIGHT)

    # ==================================================================
    # 通用小组件
    # ==================================================================
    def _build_progress_panel(self, parent) -> dict:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill=X, pady=(PAD_TIGHT, 0))

        stage = make_label(frame, text="准备中…", fg=C_TEXT_MAIN,
                           font_size=FS_SMALL)
        stage.pack(anchor=W)

        bar = ctk.CTkProgressBar(frame, height=px(H_PROGRESS),
                                 corner_radius=R_PROGRESS,
                                 fg_color=C_PANEL_ALT_BG,
                                 progress_color=C_ACCENT)
        bar.set(0)
        bar.pack(fill=X, pady=(PAD_TIGHT, PAD_MICRO))

        detail = make_label(frame, text="", fg=C_TEXT_SECONDARY,
                            font_size=FS_TINY)
        detail.pack(anchor=W)

        buttons = ctk.CTkFrame(parent, fg_color="transparent")
        state = {"start": time.time(), "last_bytes": 0, "last_time": time.time(),
                 "speed": 0.0}

        def update(done, total, index, count, entry_name):
            try:
                ratio = (done / total) if total else 0.0
                target = max(0.0, min(1.0, ratio))
                start = float(bar.get())
                if abs(target - start) > 0.001:
                    def frame(e, _raw, a=start, b=target):
                        try:
                            bar.set(a + (b - a) * e)
                        except Exception:
                            pass
                    # 补间过去，别一格一格跳
                    tween(bar, "progress", 200, frame, easing=ease_out_cubic)
                now = time.time()
                elapsed = max(0.001, now - state["last_time"])
                if elapsed >= 0.4:
                    delta = max(0, done - state["last_bytes"])
                    instant = delta / elapsed
                    state["speed"] = (instant if not state["speed"]
                                      else state["speed"] * 0.7 + instant * 0.3)
                    state["last_bytes"] = done
                    state["last_time"] = now
                speed = state["speed"]
                remain = ""
                if speed > 1024 and total > done:
                    remain = f" · 剩余约 {int((total - done) / speed)} 秒"
                try:
                    percent.configure(text=f"{int(ratio * 100)}%")
                except Exception:
                    pass
                detail.configure(
                    text=f"{_human_size(done)} / {_human_size(total)}"
                         f" · {_human_size(speed)}/s{remain}")
                if entry_name:
                    prefix = f"[{index}/{count}] " if count else ""
                    stage.configure(text=f"{prefix}{entry_name}")
            except Exception:
                pass

        return {"frame": frame, "update": update, "buttons": buttons,
                "stage": lambda text: _safe_config(stage, text=text)}

    def _dialog_bar(self, card):
        """弹窗底部按钮条：上方压一条发丝线，和内容分开。"""
        try:
            ctk.CTkFrame(card.body, fg_color=C_DIVIDER, height=1).pack(
                fill=X, pady=(PAD_DIALOG, PAD_INNER))
        except Exception:
            pass
        bar = ctk.CTkFrame(card.body, fg_color="transparent")
        bar.pack(fill=X)
        return bar

    def _copy(self, text: str) -> None:
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except Exception:
            pass


def _safe_config(widget, **kwargs):
    try:
        widget.configure(**kwargs)
    except Exception:
        pass


_META_NAMES = {"index.json", "version.txt", "description.txt",
               "tacz-pre.toml", "blacklist.txt", "tacz_default_gun"}
_MAX_SCAN_FILES = 20000


def _quick_measure(root: str) -> tuple[int, int]:
    """轻量统计：一层条目数 + 递归字节数（只 stat，不读内容）。"""
    if not root or not os.path.isdir(root):
        return 0, 0
    count = 0
    size = 0
    files = 0
    try:
        entries = list(os.scandir(root))
    except OSError:
        return 0, 0
    for entry in entries:
        name = entry.name
        if name.startswith(".") or name in _META_NAMES:
            continue
        count += 1
        try:
            if entry.is_file(follow_symlinks=False):
                size += entry.stat(follow_symlinks=False).st_size
                files += 1
            elif entry.is_dir(follow_symlinks=False):
                for dirpath, _dirnames, filenames in os.walk(entry.path):
                    for filename in filenames:
                        try:
                            size += os.path.getsize(os.path.join(dirpath,
                                                                filename))
                        except OSError:
                            continue
                        files += 1
                        if files >= _MAX_SCAN_FILES:
                            return count, size
        except OSError:
            continue
    return count, size
