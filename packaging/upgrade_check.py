"""
升级自检：模拟 2.5.3 升级上来的本机状态（开发者身份 + 旧 account.json）。

旧版本把蓝奏的会话 ID 当昵称存进 account.json，界面上会显示
「开发者 · 4654636」，用户以为登错了号。这里验证：

  · 旧文件读出来不再显示那个数字
  · 重新登录后账号行显示打码手机号
  · 开发者 → 玩家切换正常，主按钮回到玩家动作

    python packaging/upgrade_check.py
"""
import json
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

TMP = Path(tempfile.mkdtemp(prefix="ps_legacy_"))
PACK = TMP / "pack"
(PACK / "tacz").mkdir(parents=True)
DB = PACK / "PulsesSwap_database"
preset = DB / "SSR预设包"
preset.mkdir(parents=True)
with zipfile.ZipFile(preset / "gun.zip", "w") as z:
    z.writestr("pack.json", "{}")
(preset / "index.json").write_text(
    '{"name":"SSR预设包","version":"v1.2.0","gunpacks":{},"applied":true}',
    encoding="utf-8")
(DB / ".settings.json").write_text(json.dumps({"role": "developer"}),
                                   encoding="utf-8")
online = DB / ".online"
online.mkdir(parents=True)
(online / "account.json").write_text(json.dumps({
    "version": 1, "uid": "4654636", "nickname": "4654636",
    "secret": "badsecret"}), encoding="utf-8")

import pulses_swap as ps

for mod in (ps.dialogs, ps.utils, ps.app, ps.pages, ps.managers):
    for name in ("show_info", "show_warning", "show_error", "ask_yes_no",
                 "ask_ok_cancel", "show_message"):
        if hasattr(mod, name):
            setattr(mod, name, lambda *a, **k: None)
    if hasattr(mod, "DatabaseLocatorDialog"):
        mod.DatabaseLocatorDialog.show = lambda self: None
ps.DatabaseLocator.load_db_path = staticmethod(lambda: DB)
import pulses.ui.packs as packs_mod
packs_mod.ask_text = lambda *a, **k: "自动测试"

root = ps.ctk.CTk()
ps.apply_font_fallbacks()
ps.sync_ui_scale(root)
root.geometry("1280x900")
root.update()

FAIL = []
def check(label, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + label + ("" if cond else f"  {detail}"))
    if not cond: FAIL.append(label)

def pump(ms=400):
    end = time.time() + ms / 1000
    while time.time() < end:
        root.update(); time.sleep(0.01)

app = ps.PulsesSwapApp(root)
pump(1500)
app.load_pack(PACK)
pump(2500)

check("开发者身份从设置里恢复", app.is_developer, app.settings.role)
check("徽标是「开发者」而不是数字",
      app.identity_badge.cget("text") == "开发者",
      app.identity_badge.cget("text"))
check("旧会话 ID 不再显示",
      "4654636" not in app.identity_badge.cget("text"))
check("旧文件读出来不带账号行",
      app.identity_account.winfo_ismapped() == 0,
      app.identity_account.cget("text"))
info = app.online.account_info()
check("username 已丢弃（旧格式）", info.get("username") == "", info)

# 重新登录一次 → 账号行出现打码手机号
app.online.accounts.set("4654636", "x", username="18651999816")
app._update_identity_ui()
pump(200)
check("重新登录后显示打码账号",
      app.identity_account.winfo_ismapped() == 1
      and app.identity_account.cget("text") == "186****9816",
      app.identity_account.cget("text"))

# 切回玩家
app._set_role("player")
pump(300)
check("能切回玩家", not app.is_developer and app.settings.role == "player")
check("玩家不再显示账号行", app.identity_account.winfo_ismapped() == 0)
check("主按钮回到玩家动作",
      app.apply_btn.winfo_ismapped() == 1
      and app.publish_btn.winfo_ismapped() == 0,
      (app.apply_btn.winfo_ismapped(), app.publish_btn.winfo_ismapped()))

print("\n" + ("FAIL" if FAIL else "全部通过"))
root.destroy()
sys.exit(1 if FAIL else 0)
