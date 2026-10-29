# -*- mode: python ; coding: utf-8 -*-
"""Pulses Swap 3.x PyWebView 打包配置（Windows / Linux）。"""
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"
WEB_DIST = SRC / "pulses_web" / "web" / "dist"
PKG = ROOT / "packaging"

datas = [
    (str(WEB_DIST), "pulses_web/web/dist"),
]
for name in ("icon.ico", "icon.png", "icon.icns"):
    path = PKG / name
    if path.exists():
        datas.append((str(path), "."))
# pywebview 的平台桥接和本地化数据
datas += collect_data_files("webview")
# customtkinter 只用于旧核心模块的 import 兼容，不创建窗口
try:
    datas += collect_data_files("customtkinter")
except Exception:
    pass

hiddenimports = collect_submodules("webview")
hiddenimports += [
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    "webview.platforms.gtk",
    "webview.http",
    "clr_loader",
    "pythonnet",
    "pulses_web.main",
    "pulses_web.api",
    "pulses_web.controller",
    "pulses_web.events",
]

a = Analysis(
    [str(SRC / "pulses_web_main.py")],
    pathex=[str(SRC), str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "PySide2", "PySide6", "matplotlib", "numpy"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="PulsesSwap", debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False, disable_windowed_traceback=False,
    icon=str(PKG / "icon.ico") if (PKG / "icon.ico").exists() else None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
               name="PulsesSwap")
