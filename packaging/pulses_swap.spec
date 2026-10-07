# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 —— 同时用于 Windows 安装器与 Linux 单文件版。

CI 用法：
    pyinstaller packaging/pulses_swap.spec --noconfirm --clean

产物：
    Windows -> dist/PulsesSwap/PulsesSwap.exe   （目录版，交给 Inno Setup 做安装器）
    Linux   -> dist/PulsesSwap                  （单文件可执行）
"""
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent          # noqa: F821  (SPECPATH 由 PyInstaller 注入)
ENTRY = ROOT / "src" / "pulses_swap.py"

# tkinterdnd2 带 tkdnd 二进制，必须显式收进来，否则拖拽功能在打包后失效
datas = collect_data_files("tkinterdnd2")

# 窗口图标：运行时由 pulses_swap.resource_path() 从 sys._MEIPASS 读取。
# 不加进 datas 的话，打包后 icon.ico / icon.png 不存在，窗口会退回 Tk 默认羽毛图标。
for _icon_name in ("icon.ico", "icon.png"):
    _icon_path = ROOT / "packaging" / _icon_name
    if _icon_path.exists():
        datas.append((str(_icon_path), "."))

hiddenimports = collect_submodules("tkinterdnd2") + ["watchdog.observers", "PIL._tkinter_finder"]

a = Analysis(
    [str(ENTRY)],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["numpy", "matplotlib", "pytest", "setuptools", "pip"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PulsesSwap",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                 # GUI 程序，不要控制台窗口
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "packaging" / "icon.ico") if (ROOT / "packaging" / "icon.ico").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="PulsesSwap",
)
