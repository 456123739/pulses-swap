# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 —— Windows / macOS / Linux 共用一份。

CI 用法：
    pyinstaller packaging/pulses_swap.spec --noconfirm --clean

产物：
    Windows -> dist/PulsesSwap/PulsesSwap.exe   （目录版，交给 Inno Setup 做安装器）
    macOS   -> dist/PulsesSwap.app              （可直接拖进"应用程序"）
    Linux   -> dist/PulsesSwap                  （单文件可执行）

平台差异只在这几处：
    · 图标：Windows 用 .ico，macOS 用 .icns，Linux 不要图标
    · macOS 需要 BUNDLE 才是真正的 .app（有 Dock 图标、能被 Finder 双击）
    · macOS 必须声明 NSHighResolutionCapable，否则 Retina 上是模糊的位图放大
"""
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent          # noqa: F821  (SPECPATH 由 PyInstaller 注入)
ENTRY = ROOT / "src" / "main.py"
PKG = ROOT / "packaging"

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")


def _version() -> str:
    """版本号只在 core/paths.py 里定义一处，打包时读出来给安装器 / .app 用。"""
    try:
        text = (ROOT / "src" / "pulses" / "core" / "paths.py").read_text(
            encoding="utf-8")
        found = re.search(r'VERSION\s*=\s*"([^"]+)"', text)
        if found:
            return found.group(1)
    except Exception:
        pass
    return "0.0.0"


VERSION = _version()

# tkinterdnd2 带 tkdnd 二进制，必须显式收进来，否则拖拽功能在打包后失效
datas = collect_data_files("tkinterdnd2")

# 窗口图标：运行时由 resource_path() 从 sys._MEIPASS 读取。
# 不加进 datas 的话，打包后图标不存在，窗口会退回 Tk 默认羽毛图标。
for _icon_name in ("icon.ico", "icon.png", "icon.icns"):
    _icon_path = PKG / _icon_name
    if _icon_path.exists():
        datas.append((str(_icon_path), "."))

hiddenimports = collect_submodules("tkinterdnd2") + ["watchdog.observers", "PIL._tkinter_finder"]

# online/ 是与 pulses/ 并列的顶层包，显式列出来最稳
# （它在 pulses/ui/online.py 里是 try 导入，隐式分析有可能漏）
hiddenimports += [
    "online", "online.acw", "online.diff", "online.downloader",
    "online.errors", "online.hashing", "online.manifest", "online.packing",
    "online.paths", "online.provider_lanzou", "online.provider_lanzou_account",
    "online.publisher", "online.service", "online.trash", "online.updater",
]

a = Analysis(
    [str(ENTRY)],
    pathex=[str(ROOT / "src")],  # 让 pulses/ 包可被找到,
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["numpy", "matplotlib", "pytest", "setuptools", "pip"],
    noarchive=False,
)
pyz = PYZ(a.pure)

# Windows / Linux 用 .ico；macOS 的 .app 只认 .icns（EXE 的 icon 在 mac 上会被忽略）
if IS_MAC:
    _icon = PKG / "icon.icns"
else:
    _icon = PKG / "icon.ico"
ICON = str(_icon) if _icon.exists() else None

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PulsesSwap",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                     # UPX 压缩过的 exe 更容易被杀软误报
    console=False,                 # GUI 程序，不要控制台窗口
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="PulsesSwap",
)

if IS_MAC:
    # 没有 BUNDLE 的话 mac 上只会得到一个 Unix 可执行文件：没有 Dock 图标，
    # Finder 里也不能直接双击，用户会以为「下载坏了」。
    app = BUNDLE(
        coll,
        name="PulsesSwap.app",
        icon=ICON,
        bundle_identifier="Pulses0Studio.PulsesSwap",
        info_plist={
            "CFBundleName": "Pulses Swap",
            "CFBundleDisplayName": "Pulses Swap",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,      # Retina 下不糊
            "LSMinimumSystemVersion": "10.15",
            "NSRequiresAquaSystemAppearance": False,
            "LSApplicationCategoryType": "public.app-category.utilities",
        },
    )
