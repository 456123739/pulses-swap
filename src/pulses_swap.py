"""
Pulses Swap - 快速枪包切换器
作者: NimShade
版本: 2.4.14
描述: Minecraft Tacz 模组枪包快速切换工具
UI风格: Pulses 水墨淡色主题（customtkinter 圆角版本）

v2.4.14 更新（真正的元凶：「最近」下拉面板）:
  - 用户指着 Step 1 的「最近」按钮反馈：展开/收起又慢、中间帧控件全白
  - 真因：面板是 pack 在卡片里的，展开/收起每帧都在改高度 ——
    每改一次高度，整页（137 个控件）都要重新布局，Windows 上就是
    又慢又闪白
  - 改成「不参与布局」的下拉浮层：用 place 挂在按钮行下方，
    place 不影响 pack/grid 排版 —— 实测展开前后卡片请求高度 254 → 254
    完全不变、兄弟控件零位移，只有面板自己在动
  - 顺带：设置页新增「动画」开关（流畅 / 关闭），关掉后所有补间一帧到位；
    开关状态写进 .settings.json，重启后保持

v2.4.13 更新（中间帧控件闪白的根治：切页只搬位图）:
  - 现象：切换页面时中间某一帧所有控件变成白色（用户说的「插帧」）
  - 机制：Tk 会把移出 Canvas 可视区的窗口项 unmap，滑回来时再 remap；
    remap 那一下控件重新绘制，在 Windows 上就是一片白
  - 修法：切页动画期间只搬两张**静态位图快照**，活的控件树一动不动 ——
    不触发 unmap/remap，任何平台都不会闪白。页面每次落定后自动补拍快照
    （延后 180ms 等布局绘制落定），拍不到就退回原路径，功能不受影响
  - 配合 v2.4.12 的定时器精度（1ms）与 40/60fps 分档，动画应当既顺且稳

v2.4.12 更新（Windows 上卡顿的两处根源）:
  - Windows 默认定时器精度约 15.6ms：after(17) 实际会变成 ~31ms，
    60fps 的补间直接掉到 30fps —— 观感就是「一卡一卡」。
    启动时 timeBeginPeriod(1) 把精度提到 1ms（退出时还回去）
  - 切页动画改成「覆盖式」：旧页留在原地当背景（整页不透明，天然铺满
    视口），只搬新页 —— 每帧只搬一棵控件树，开销是对开推入的一半
  - 新增实测帧率日志（完整日志模式可见）：「动画实测: N 帧 ·
    平均帧间隔 X ms (≈Y fps)」，卡不卡用数字说话

v2.4.11 更新（逐个动画审计中间帧）:
  - 新增中间帧不变量审计：把每个动画逐帧采样，断言几何/颜色不变量
    （两页严格拼接、滑块不越界、面板高度单调、颜色单调过渡、Toast 收掉…）
  - 修：Toast 入场方向反了 —— _offset 的符号写错，变成「从里往外弹」，
    应该是从屏幕右边缘外滑进来（改成 _slide 28 → 0）
  - 修：Toast 关闭后 app._toast 仍指向已销毁的浮层（现在 close() 里清引用）
  - 顺带固化进真机测试：滑动过程中「旧页y - 新页y 必须等于视口高度」
    （任意中间帧都无缝、不重叠）

v2.4.10 更新（动画撕裂的真因：隐藏的页面尺寸是错的）:
  - 撕裂根因：Canvas 窗口项在 state="hidden" 期间不会被 Tk 调整尺寸，
    实测设置页/日志页停在 384x483（CTk 默认尺寸），一显示就带着这个尺寸
    滑进来 —— 四周露出下面那页的内容，看起来就是撕裂/割裂
  - 改成「停到视口外」而不是隐藏：三页始终 map，尺寸永远等于画布
    （实测三页都是 1064x883）；切换时两页对开推入，任意时刻正好铺满
    视口，既不露底色也不重叠
  - 这样也顺带消掉了「首次显示要重新布局」的开销，配合预热，切页不再延迟

v2.4.9 更新（切页「延迟很久」与「关闭后选不了包」）:
  - 切页延迟的真因：Canvas 窗口项第一次被 map 时，Tk 要跑一遍整棵控件树
    的布局（实测设置页 78 个控件约 41ms，主页 137 个更久，Windows 还要
    翻倍），这一下正好卡在切换动画的第一帧 —— 表现就是「点了没反应，
    过一会儿才切页」。现在启动时把三页 + 设置页三个选项卡各预热一次，
    首次切换的触发开销从 41ms 降到 1.3~2.6ms
  - 修：关闭整合包后「选择」变灰点不了 —— close_pack() 末尾调了
    _disable_buttons(True) 把包括「选择」「数据库」在内的所有按钮全禁用，
    之后没有任何地方再解开。改成只禁用「依赖已加载整合包」的那批按钮
    （关闭 / 打开TACZ / 一键替换 / 预设相关），「选择 / 数据库」始终可用
  - 切换被打断时先让上一段动画落位，避免状态与画面不一致

v2.4.8 更新（滑动动画恢复成真滑动 + 方向映射修正）:
  - 撤掉 v2.4.6 的「幕布扫过」：观感像一条灰带子、像淡入淡出，
    不是滑动。恢复成真滑动 —— 新页从进入侧滑到正位，旧页原地不动
    （只搬一棵控件树，帧开销减半，也不会在中间露出空白）
    实测 54fps（帧间隔中位 18.4ms，其中 16.7ms 是设定的帧周期）
  - 修方向映射：点左边的选项内容要往左走（新页从右侧进来），
    原先把 index 增大映射成了 direction=-1，方向正好相反；
    侧边栏（竖排）与设置页选项卡（横排）两处都改

v2.4.7 更新（列表看着「两个都选中」+ 导入框被裁）:
  - 预设列表里「已应用」原来用浅绿底色标注，和「选中」高亮是同一个色，
    看起来像两个都被选中。改成文字前缀「✓ 名字」（绿色字），
    底色只留给选中态；读取处统一走 preset_name_of() 剥前缀
  - 导入框文字被裁：CTkScrollbar 默认 200x200，加滚动条时没压高度，
    把列表容器的请求高度顶到 208，Step2 卡下限因此虚高 140px。
    滚动条改 height=1（实际高度由 fill="y" 决定）
  - 左列三张卡下限按实测重设：258 / 292 / 190（原 215/275/138 偏小）
  - 预设/枪包/最近列表初始行数 6/10/5 → 4/6/4（请求高度只是下限，
    实际仍随窗口拉伸）
  - 窗口默认 1280x900、最小 1140x812；启动尺寸按屏幕收口
    （高分屏下窗口会被放大，避免比屏幕还高）

v2.4.6 更新（动画又慢又撕裂的真因：动画本身太贵）:
  - 页面切换原来是把 Canvas 里的「页面窗口项」整棵控件树搬来搬去，
    实测 3.6ms/帧（普通画布矩形只要 0.26ms，差 14 倍），Windows 上
    子窗口重排更贵 → 掉帧 + 撕裂。改成「幕布扫过」：只动一块画布矩形，
    到中点时才换页，实测 0.015ms/帧（快 240 倍）
  - 颜色类补间单独降到 40fps（大卡片描边实测 3.05ms/帧、按钮 1.71ms/帧，
    每帧都要让 CTk 重画控件；40fps 观感一样顺，开销减半）；
    位置类（滑块、幕布）保持 60fps
  - 启动入场不再搬页面控件树，只保留导航滑块淡入
  - 新增 _activate()：幕布切换与瞬时切换共用同一套「贴正位/隐藏其余」逻辑

v2.4.5 更新（列表显示不全 / 滚动卡顿的真因）:
  - 修：高分屏（125%/150%）下内容撑不出窗口 —— 只按 DPI 放大了控件，
    窗口尺寸没跟着放大，于是布局溢出：列表被撑得很大、下面的一键替换和
    日志被挤出窗口，看起来就是「强制展示所有枪包、不允许被裁切」。
    现在 set_window_scaling(UI_SCALE) 一起放大窗口（150% 下 1280x840
    → 1920x1260），实测日志卡底部 1247 < 1260，内容完整在窗口内
  - 滚轮改成逐帧滑动：Tk 的 Listbox 只能整行滚，直接 yview_scroll 会一顿
    一顿的；现在换算成视图比例后用 140ms 补间滑过去

v2.4.4 更新（两个真 bug + 列表滚动）:
  - 修：按钮点下去什么都不执行 —— AnimatedButton 用了和 CTkButton 同名的
    私有方法 _on_enter/_on_leave/_on_release，把 CTk 内部「执行 command」
    的那段覆盖掉了。改名成 _anim_* 后恢复
  - 修：按钮按下无反馈 —— 普通按钮的 press_color 默认取了 hover 色；
    强调按钮按下改用 C_ACCENT_PRESSED，普通按钮按下混向强调色 45%
  - 修：hover_color 交给 CTk 用「目标色」，避免 CTk 的进出/点击动画把
    逐帧混出来的中间色顶掉
  - 三个列表框（枪包 / 预设 / 最近）都配了细滚动条，滚轮改成 3 行/格
    （Tk 默认一格一行，条目多时手感很卡）
  - 兜底：加载/刷新结束时无条件解除按钮禁用，避免中途出错把界面锁死
  - 去掉新手引导的绿色描边（Step 1 那圈绿边），引导只留日志文案

v2.4.3 更新（需求澄清）:
  - 之前把「去掉图标和动画」理解成整个动效层都关掉 —— 实际要去掉的是
    「图标动画」，页面/选项卡的滑动、按钮 hover、卡片描边、进度条、
    Toast 这些全部恢复（ANIMATIONS_ENABLED 重新打开）
  - 两条循环动效（加载小圆点、引导描边呼吸）一并恢复；开关关掉时它们
    会自动降级为静态一次到位，不会自递归
  - 图标仍然保持去掉（侧边栏纯文字）
  - 修：按钮按下没有反馈 —— 普通按钮的 press_color 默认取了 hover 色，
    按下与悬停一模一样；现在强调按钮按下用 C_ACCENT_PRESSED（更深一档），
    普通按钮按下混向强调色 45%，按下/松开都有明确的下压感
  - 去掉新手引导的绿色描边高亮（Step 1 卡片那圈绿边），引导只留日志文案

v2.4.2 更新（按反馈集中修四类问题）:
  - Win11 窗口变半透明：DWMWA_SYSTEMBACKDROP_TYPE 原来设的是 0(AUTO)，
    窗口失焦（有弹窗在前面）时系统就自己上 Mica/Acrylic，壁纸透进来。
    改成 1(DWMSBT_NONE)，并额外关掉未公开的 DWMWA_MICA_EFFECT(1029) 兜底
  - 字又小又糊：启动时先声明进程 DPI 感知（CTk 自己做太晚，窗口已按未感知
    建好，仍被系统拉伸 → 糊）；字号整体 +1~2pt；自绘 Canvas / grid minsize /
    Listbox 字号按 CTk 的缩放系数同步放大，避免高分屏下与 CTk 控件错位
  - 报错很多：root.after() 从 worker 线程调用会抛
    RuntimeError("main thread is not in main loop")，加载预设的线程当场死掉、
    UI 永远卡在「加载中」。改成线程安全队列投递（ui_call + 主线程轮询），
    29 处调用点统一替换
  - 「本次启动不再提醒」勾了没用：原来只在点「确定/导出」时读勾选框，
    用 ESC 或窗口 ✕ 关掉就白勾了。改成不管怎么关都会读
  - 数据库定位对话框改成独立小窗口（640x520），不再铺满主窗口
  - 新增端到端流程测试（假整合包 → 加载 → 建预设 → 刷新 → 替换 → 导出 →
    关闭 → 重开 → 设置自动保存 → 日志），全程零 Traceback

v2.4.1 更新:
  - 新增 Windows 绿色版（免安装）：Release 里多一个
    PulsesSwap-Portable-<版本>.zip，解压即用、不写注册表，
    数据存在同目录的 PulsesSwap_database\，整个文件夹拷走即搬家
    （数据目录优先级本来就是「程序目录可写 → 写在程序旁边」，
    这次只是把它打成 zip 并附上使用说明）
  - 启动日志补一行「运行模式: 绿色版 / 安装版」，便于确认当前形态

v2.4.0 更新（方向调整：去掉图标与动画）:
  - 侧边栏导航改为纯文字（主界面 / 设置 / 日志），不再有任何图标；
    选中态是一块静态圆角药丸
  - 全部过渡动画关闭：页面切换、选项卡切换、按钮 hover、卡片描边、
    进度条、Toast 入场……（v2.4.3 已重新打开：去掉的只是图标动画）
  - 随之删掉：自绘矢量图标引擎、烘制脚本 packaging/make_icons.py、
    packaging/icons/ 下的 SVG、以及两条循环动效（加载脉冲、引导呼吸）
  - 保留之前的结构性改动：无顶栏、侧边栏 200px 宽、设置项即时自动保存、
    设置项无解释性小字、主界面右列「枪包列表 → 一键替换 → 分割线 → 日志」、
    侧边栏底部状态卡、日志分级

v2.3.6 及以前（历史）:
  - 图标几经迭代（emoji → 自绘矢量 → 官方图标集 → 指定填充图标），
    最终按需求整体去掉；相关实现见 git 历史

v2.3.1 更新:
  - 修：侧边栏 sticky="nsw" 不横向拉伸 → 一直只有 124px 宽（显得又窄又挤），
    改为 "nsew" 后按 200px 正常铺开
  - 页面切换方向按「点哪边内容就往哪边走」：点下面/右面的选项内容往下/右走，
    点上面/左面的往上/左走；侧边栏是竖排，页面就竖着滑
  - 切换曲线换成 S 曲线（ease_in_out_cubic）并把时长拉到 420ms，
    原来的 easeOutQuint 前 20% 就走完 2/3，看着像瞬切
  - 主界面右列改为：枪包列表 + 一键替换 → 分割线 → 日志栏（与日志页同一份日志流）
  - 设置页简洁化：删掉所有解释性小字，选项改成带动画的分段控件
  - 设置页底部常态只留「自动保存」，改动时短暂回显「✓ 已自动保存」
  - 图标点击动画：主界面轻跳 / 设置齿轮转 45°（切走转回）/ 日志轻摆
  - 日志分级：过程流水默认不占显示位，只保留最近一条有意义的状态；
    「设置已保存 / 已切换到 xx 模式」这类回显只在完整日志模式显示

v2.3.0 更新:
  - 顶栏（原生菜单栏）移除：原菜单项全部迁入界面，功能一个不少
  - 切换选项曲线动画：侧边栏导航与设置页选项卡改为自绘 Canvas 分段控件，
    选中滑块按缓动曲线逐帧滑动；页面切换为 Canvas 内整页推入/推出
  - 设置自动保存：单选项改动即写 .settings.json，不再需要保存按钮
  - 动画引擎：缓动曲线 + 颜色插值 + 去重补间调度，按钮/卡片/弹窗/Toast/
    进度条/加载指示/新手引导/折叠面板全部带过渡
  - 侧边栏只保留品牌 + 导航项，移除提示文案

v2.2.0 更新:
  - 侧边栏导航 + 设置页选项卡（替代原顶栏菜单入口与设置弹窗）
  - 全部提示/确认改为主窗口内覆盖层，不再新开系统窗口
  - 任务栏 AppUserModelID、窗口图标、窗口尺寸 1280x840

v2.1 更新:
  - 整合包选择区改为大拖入框，拖入任意整合包内文件/文件夹自动定位 tacz
  - 拖入预设包/更新包自动识别并加载，重名时询问是否替换
  - 「新建数据库」默认在程序目录下创建

v2.0 更新:
  - Win11 透明修复（强制不透明 + 禁用 DWM Mica/Acrylic），打包版同样适用
  - 新手引导系统：Step1/2/3/4 描述 + 当前步骤控件高亮描边
  - 引导根据实际状态自动切换
"""

import ctypes
try:                      # ctypes.wintypes 在非 Windows 上会直接抛 ValueError
    import ctypes.wintypes
except Exception:         # pragma: no cover - 仅影响 Windows 回收站功能
    ctypes.wintypes = None
import hashlib
import json
import os
import queue
import shutil
import sys
import tempfile
import threading
import time
import traceback
import zipfile
from datetime import datetime
from pathlib import Path
from tkinter import *
# 故意不导入 tkinter.messagebox：它是 Tk 原生模态对话框，必然新开系统窗口。
# 本文件所有提示/确认都走主窗口内的覆盖层（见 show_message），下方另有同名
# 兼容垫片 messagebox，保证漏改的调用点也不会退回系统新窗口。
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

# ==================== 常量定义 ====================
VERSION = "2.4.14"
AUTHOR = "NimShade"
PROJECT_NAME = "Pulses Swap"

IS_WINDOWS = sys.platform.startswith('win')

if getattr(sys, 'frozen', False):
    PROGRAM_DIR = Path(sys.executable).parent
else:
    PROGRAM_DIR = Path(__file__).parent

CONFIG_FILENAME = "PulsesSwap_config.json"
DATABASE_DIRNAME = "PulsesSwap_database"
APP_DIRNAME = "PulsesSwap"


def safe_print(*args, **kwargs) -> None:
    """windowed 打包（console=False）时 sys.stdout 为 None，直接 print 会抛
    AttributeError 并把异常处理路径本身弄崩，这里统一兜底。"""
    try:
        print(*args, **kwargs)
    except Exception:
        pass


def is_dir_writable(directory: Path) -> bool:
    """真实写测试：建目录 → 写临时文件 → 删掉。

    不用 os.access()：在 Windows 上它只看只读属性位，
    对 C:\\Program Files 这类 ACL 拒绝的目录会误报为可写。
    """
    probe = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / f".pulses_write_test_{os.getpid()}_{time.time_ns()}"
        with open(probe, 'w', encoding='utf-8') as f:
            f.write('ok')
        return True
    except Exception:
        return False
    finally:
        if probe is not None:
            try:
                probe.unlink()
            except Exception:
                pass


def get_user_data_dir() -> Path:
    """跨平台用户数据目录：Windows 用 %LOCALAPPDATA%\\PulsesSwap，
    其他平台用 $XDG_DATA_HOME/PulsesSwap 或 ~/.local/share/PulsesSwap。"""
    if IS_WINDOWS:
        base = os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA')
        if base:
            return Path(base) / APP_DIRNAME
        return Path.home() / 'AppData' / 'Local' / APP_DIRNAME
    xdg = os.environ.get('XDG_DATA_HOME')
    if xdg:
        return Path(xdg) / APP_DIRNAME
    return Path.home() / '.local' / 'share' / APP_DIRNAME


def resolve_data_base_dir() -> tuple[Path, bool]:
    """解析数据根目录。返回 (根目录, 是否处于便携模式)。

    优先级：
      1. 程序目录可写 → 直接用程序目录（绿色/便携模式，行为与旧版完全一致）
      2. 程序目录不可写，但数据库确实就在程序目录下
         → 仍然用程序目录（不改变已有用户的数据位置）
      3. 否则 → 用户数据目录（安装到 C:\\Program Files 时的正常路径）。
         即使回退，旧版写在程序目录的 PulsesSwap_config.json 仍会被
         load_db_path() 读到，老用户记下的数据库位置不会丢。
    """
    if is_dir_writable(PROGRAM_DIR):
        return PROGRAM_DIR, True
    if (PROGRAM_DIR / DATABASE_DIRNAME).exists():
        return PROGRAM_DIR, True
    return get_user_data_dir(), False


DATA_BASE_DIR, IS_PORTABLE_MODE = resolve_data_base_dir()

# v2.1 及以前固定把配置写在程序目录，读取时仍需兼容旧文件
LEGACY_BOOTSTRAP_FILE = PROGRAM_DIR / CONFIG_FILENAME

BOOTSTRAP_FILE = DATA_BASE_DIR / CONFIG_FILENAME
DEFAULT_DB_DIR = DATA_BASE_DIR / DATABASE_DIRNAME


def resource_path(filename: str) -> Path:
    """解析随程序分发的资源文件路径（源码运行 / PyInstaller frozen 都适用）。"""
    candidates = []
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        candidates.append(Path(meipass) / filename)
    here = Path(__file__).resolve().parent
    candidates.append(here / filename)                       # 与源码同级
    candidates.append(here.parent / 'packaging' / filename)  # 仓库内 packaging/
    for c in candidates:
        try:
            if c.exists():
                return c
        except Exception:
            continue
    return candidates[0]

LEGACY_DB_DIRNAME = "FGC_database"
LEGACY_CACHE_FILE = ".cache.json"
LEGACY_MIGRATED_MARKER = ".migrated_to_pulses_swap"

# ==================== Windows 原生回收站 ====================
FO_DELETE = 0x0003
FOF_ALLOWUNDO = 0x0040
FOF_NOCONFIRMATION = 0x0010
FOF_NOERRORUI = 0x0400
FOF_SILENT = 0x0004
FOF_NOCONFIRMMKDIR = 0x0200


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.wintypes.HWND),
        ("wFunc", ctypes.wintypes.UINT),
        ("pFrom", ctypes.wintypes.LPCWSTR),
        ("pTo", ctypes.wintypes.LPCWSTR),
        ("fFlags", ctypes.wintypes.USHORT),
        ("fAnyOperationsAborted", ctypes.wintypes.BOOL),
        ("hNameMappings", ctypes.wintypes.LPVOID),
        ("lpszProgressTitle", ctypes.wintypes.LPCWSTR),
    ]


def move_to_recycle_bin(path) -> bool:
    """使用 Windows 原生 SHFileOperationW 将文件/文件夹送入回收站"""
    if not IS_WINDOWS:
        return False
    try:
        p = Path(path)
        if not p.exists():
            return True
        path_str = str(p.resolve()) + '\0\0'
        op = _SHFILEOPSTRUCTW()
        op.hwnd = None
        op.wFunc = FO_DELETE
        op.pFrom = path_str
        op.pTo = None
        op.fFlags = (FOF_ALLOWUNDO | FOF_NOCONFIRMATION |
                     FOF_NOERRORUI | FOF_SILENT | FOF_NOCONFIRMMKDIR)
        op.fAnyOperationsAborted = False
        op.hNameMappings = None
        op.lpszProgressTitle = None
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        return (result == 0) and (not op.fAnyOperationsAborted)
    except Exception:
        return False


# ==================== Pulses 水墨淡色主题 ====================
C_WINDOW_BG      = "#F5F7F8"
C_PANEL_BG       = "#FFFFFF"
C_PANEL_ALT_BG   = "#EDF2F4"
C_INPUT_BG       = "#F7FAFB"

C_ACCENT         = "#5BA89A"
C_ACCENT_HOVER   = "#4A9285"
C_ACCENT_PRESSED = "#3D7A6E"
C_ACCENT_SOFT    = "#D6E8E4"

C_TEXT_MAIN      = "#2C3E3F"
C_TEXT_SECONDARY = "#6B7B7D"
C_TEXT_MUTED     = "#9AABAD"
C_TEXT_INVERSE   = "#FFFFFF"

C_BORDER         = "#D1DCDE"
C_DIVIDER        = "#E0E8EA"
C_FOCUS          = "#5BA89A"

C_SUCCESS        = "#5BA89A"
C_WARNING        = "#C9A961"
C_ERROR          = "#C97B7B"
C_INFO           = "#7B9DC9"

C_STATUS_NORMAL    = "#5BA89A"
C_STATUS_ADDED     = "#7B9DC9"
C_STATUS_REMOVED   = "#C97B7B"
C_STATUS_MODIFIED  = "#B58EC9"
C_STATUS_EXTRA     = "#C9A961"
C_STATUS_MISSING   = "#C97B7B"
C_STATUS_EMPTY     = "#9AABAD"

C_STATUS_NORMAL_BG    = "#E7F1EE"
C_STATUS_MISSING_BG   = "#F7E8E8"
C_STATUS_EXTRA_BG     = "#F7F2E5"
C_STATUS_MODIFIED_BG  = "#F2EAF7"
C_STATUS_ADDED_BG     = "#E8EFF7"

C_GUIDE_GLOW     = "#3D7A6E"

# 层级用色：宣传片靠 box-shadow 分层，CustomTkinter 的 CTkFrame 不支持投影，
# 这里用「卡片底色微差 + 更浅的发丝描边」近似（见 R_CARD 注释）。
C_CARD_BG        = "#FFFFFF"   # 卡片底色：与 C_WINDOW_BG(#F5F7F8) 形成微差层级
C_BORDER_SOFT    = "#E3EAEB"   # 卡片/控件描边：C_BORDER 向白底混合约 50%，
                               # 近似宣传片的 rgba 半透明极细低对比线

# ==================== 形状令牌（对齐宣传片 :root） ====================
# 宣传片：--r-window:26px / --r-card:16px / --r-control:12px
R_WINDOW   = 26   # 顶层窗口圆角；CustomTkinter 不能给 toplevel 画圆角，
                  # 实际由 DWM_CORNER_PREF 在 Windows 11 上近似（见该常量）
R_CARD     = 16   # 卡片 / 面板（含拖入框等 panel）
R_CONTROL  = 12   # 按钮 / 输入框 / 显示框 / 列表框 / 文本框
R_PROGRESS = 4    # 进度条：高 8px，取 4px 即为胶囊全圆角
BORDER_W       = 1   # 发丝描边宽度
BORDER_W_FOCUS = 3   # 新手引导高亮描边宽度

# Windows 11 DWM 窗口圆角偏好：1=直角(v2.1 现状) 2=圆角(约 8px) 3=小圆角(约 4px)。
# 26px 系统不可达，取最接近的 DWM 圆角；如需恢复 v2.1 的直角窗口改回 1。
DWM_CORNER_PREF = 2

# ==================== 字体令牌 ====================
# 跨平台回退链：先 Apple 字体，再 Windows 中文字体，最后通用无衬线。
# 启动时由 apply_font_fallbacks() 取第一个系统真实存在的族。
FONT_STACK_CN = (
    "SF Pro Display", "SF Pro Text", "PingFang SC", "Helvetica Neue",
    "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI",
    "Noto Sans CJK SC", "DejaVu Sans", "Arial",
)
FONT_STACK_MONO = (
    "SF Mono", "JetBrains Mono", "Cascadia Mono",
    "Consolas", "Menlo", "DejaVu Sans Mono", "Courier New",
)
# 兜底值（Windows 必备中文字体）；apply_font_fallbacks() 会就地更新这三个名字。
FONT_FAMILY_CN   = "Microsoft YaHei UI"
FONT_FAMILY      = FONT_FAMILY_CN
FONT_FAMILY_MONO = "Consolas"

# 字号阶梯（整体上移 1~2pt，拉开层级、避免拥挤）
FS_TINY    = 11   # 提示 / 说明小字（原 10，用户反馈太小 → +1）
FS_SMALL   = 12   # 次要信息、单行标签、单选项（原 11）
FS_BODY    = 13   # 正文与控件默认字号（原 12）
FS_SUBHEAD = 15   # 卡片小节标题（原 13 粗体）
FS_TITLE   = 17   # 对话框主标题（原 15 粗体）
FS_DISPLAY = 21   # 展示型标题（原 19）

# ==================== 尺寸 / 间距令牌 ====================
H_CONTROL   = 32   # 按钮 / 输入框 / 显示框高度（原 28）
H_DROP_AREA = 76   # 拖入框高度（原 70）
H_LOG_BOX   = 132  # 日志页文本框高度（原 120）
H_HOME_LOG  = 112  # 主界面右下角日志栏高度（分割线下面那块）
H_PROGRESS  = 8    # 进度条高度
H_BTN_BAR   = 68   # 对话框底部按钮条高度（原 64）
H_TAB_HEAD  = 52   # 设置页选项卡头部高度（自绘分段控件）
PAD_CARD_X  = 16   # 卡片内左右内边距（原 12）
PAD_CARD_Y  = 12   # 卡片内上下内边距（原 10）
PAD_DIALOG  = 18   # 对话框内容边距（原 15/20）
PAD_GAP     = 10   # 卡片之间 / 行与行之间（原 8）
PAD_TIGHT   = 6    # 紧邻控件之间（原 4~6）
PAD_XS      = 4    # 极小间距（原 4）
PAD_MICRO   = 2    # 单选项与说明文字之间的极小间距（原 2）
PAD_INNER   = 8    # 控件内部文字与边框的距离
PAD_INDENT  = 32   # 单选项说明文字的缩进（与指示器对齐，原 32）
PAD_WINDOW  = 8    # 主窗口内容与窗口边框的距离

LEFT_COL_W = 340   # 主界面「Step 1/2/3」列宽度（与宣传片布局一致）
SIDEBAR_W  = 200   # 侧边导航栏宽度（原顶栏/菜单入口改为侧边栏页面）
H_NAV      = 38    # 侧边栏导航项高度

WINDOW_W, WINDOW_H = 1280, 900             # 主窗口（原 1150x760 偏小）
WINDOW_MIN_W, WINDOW_MIN_H = 1140, 812     # 主窗口最小尺寸（纵向预算见 H_STEP_*_MIN）

# 主界面左列纵向预算（px）。逐项按 FS_*/H_*/PAD_* 令牌累加，数值为实测需求：
#   Step1 整合包 ≈ 258 = 标题 + 拖入框 126 + 状态两行 + 内边距
#   Step2 预设管理 ≈ 350 = 标题 + 预设列表(4 行) + 导入框 76 + 按钮行 + 内边距
#   Step3 预设详情 ≈ 190 = 标题 + 三行信息 + 版本号行 + 内边距
#   Step2 预设   ≈ 275 = 标题 35 + 列表 ≥110 + 导入框 76 + 间隔 10 + 按钮行 32 + 内边距 12
#   Step3 详情   ≈ 138 = 标题 35 + 三行信息 51 + 版本行(8+32) + 内边距 12
#   合计 628 + 两个 PAD_GAP(10) = 648
# 顶栏（原生菜单栏）已移除，最小窗口内容高度 = 800 - 上下 PAD_WINDOW 16 = 784 ≥ 648，
# 余量 136px 通过 grid 行权重全部给 Step2 的预设列表（它会先被压缩），
# 因此 Step1/Step3 在任何允许的窗口尺寸下都不会被裁切。
H_STEP1_MIN = 258
H_STEP2_MIN = 292
H_STEP3_MIN = 190

# 覆盖层卡片 (宽, 高)：改为主窗口内覆盖层后高度由内容自适应，这里只取宽度
DLG_LOCATOR  = (680, 520)   # 数据库定位（含 4 个长文本按钮）
DLG_CHOICE   = (540, 380)   # 迁移后处理 / 身份提示 / 冲突处理
DLG_SMALL    = (520, 340)   # 迁移预设


def resolve_font_family(stack, fallback):
    """从回退链中挑第一个系统可用的字体族；无 Tk 环境时返回 fallback。"""
    try:
        from tkinter import font as tkfont
        available = set(tkfont.families())
    except Exception:
        return fallback
    for name in stack:
        if name in available:
            return name
    return fallback


def apply_font_fallbacks():
    """创建 root 之后调用：把 FONT_FAMILY* 解析成当前平台真实存在的字体族。"""
    global FONT_FAMILY_CN, FONT_FAMILY, FONT_FAMILY_MONO
    FONT_FAMILY_CN = resolve_font_family(FONT_STACK_CN, FONT_FAMILY_CN)
    FONT_FAMILY = FONT_FAMILY_CN
    FONT_FAMILY_MONO = resolve_font_family(FONT_STACK_MONO, FONT_FAMILY_MONO)
    return FONT_FAMILY_CN, FONT_FAMILY_MONO


ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")
ctk.set_widget_scaling(1.0)


# ==================== 线程 → 主线程投递 ====================
# Tkinter 的 after() 从 worker 线程调用并不可靠：主线程不在 mainloop 里时
# 会直接抛 RuntimeError("main thread is not in main loop")，worker 线程当场死掉
# —— 表现就是「预设列表永远停在加载中」+ 日志里一堆报错。
# 这里统一走队列：worker 只管入队，主线程每 25ms 取一次。
_UI_QUEUE: "queue.Queue" = queue.Queue()
_UI_PUMP_RUNNING = False


def ui_call(root, func=None, *args) -> None:
    """线程安全地把调用切回主线程执行。"""
    if func is None:
        return
    if threading.current_thread() is threading.main_thread():
        try:
            root.after(0, func, *args)
            return
        except Exception:
            pass          # 退化成队列，绝不抛给调用方
    _UI_QUEUE.put((func, args))


def start_ui_pump(root, interval_ms: int = 25) -> None:
    """主线程轮询队列（只需启动一次）。"""
    global _UI_PUMP_RUNNING
    if _UI_PUMP_RUNNING:
        return
    _UI_PUMP_RUNNING = True

    def _pump():
        while True:
            try:
                func, args = _UI_QUEUE.get_nowait()
            except queue.Empty:
                break
            try:
                func(*args)
            except Exception:
                safe_print("UI 任务执行失败:", traceback.format_exc())
        try:
            root.after(interval_ms, _pump)
        except Exception:
            pass

    try:
        root.after(interval_ms, _pump)
    except Exception:
        pass


# ==================== DPI / 缩放 ====================
# Windows 上必须做两件事，缺一个都会出问题：
#   · 进程声明 DPI 感知 —— 否则系统会把窗口位图整体拉伸，字就是糊的；
#   · 自绘的 tk.Canvas 用原始像素，得乘上和 CTk 相同的缩放系数，
#     否则系统 125%/150% 下会和 CTk 控件错位（CTk 控件自己会缩放）。
UI_SCALE = 1.0


def enable_high_resolution_timer() -> None:
    """Windows 默认定时器精度约 15.6ms：after(17) 实际会变成 ~31ms，
    60fps 的补间直接掉到 30fps，观感就是「一卡一卡」。

    timeBeginPeriod(1) 把精度提到 1ms（用完在退出时 timeEndPeriod 还回去）。
    非 Windows 平台无事发生。
    """
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:
        pass


def release_high_resolution_timer() -> None:
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.winmm.timeEndPeriod(1)
    except Exception:
        pass


def enable_dpi_awareness() -> float:
    """声明 DPI 感知并返回系统缩放系数（1.0 / 1.25 / 1.5 …）。

    必须在任何窗口创建之前调用 —— CTk 自己也会声明，但它在第一个控件
    创建时才做，那时窗口已经按未感知状态建好了，仍会被拉伸。
    """
    if not IS_WINDOWS:
        return 1.0
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)      # PER_MONITOR_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            return 1.0
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        try:
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)   # LOGPIXELSX
        finally:
            ctypes.windll.user32.ReleaseDC(0, hdc)
        return max(1.0, min(3.0, float(dpi) / 96.0))
    except Exception:
        return 1.0


def sync_ui_scale(root_widget) -> float:
    """root 建好后同步一次：CTk 的控件缩放 × 自绘控件用的像素换算。

    窗口尺寸也必须一起放大（set_window_scaling）。只放大控件不放大窗口，
    内容就撑不下 —— 表现是列表被撑得很大、下面的一键替换/日志被挤出窗口，
    看起来像「强制展示所有条目、不允许被裁切」。
    """
    global UI_SCALE
    try:
        UI_SCALE = float(ctk.ScalingTracker.get_widget_scaling(root_widget))
    except Exception:
        UI_SCALE = 1.0
    try:
        ctk.set_window_scaling(UI_SCALE)
    except Exception:
        pass
    return UI_SCALE


def px(value):
    """设计稿像素 → 当前缩放下的像素（只给 tk.Canvas / grid minsize 用）。"""
    return int(round(float(value) * UI_SCALE))


# ==================== 辅助函数 ====================
def sanitize_filename(name: str) -> str:
    if not name:
        return "unnamed"
    safe = "".join(c if c.isalnum() or c in " _-." else "_" for c in name)
    return safe.strip() or "unnamed"


def get_pack_id(pack_path: Path) -> str:
    name = pack_path.name
    safe_name = sanitize_filename(name)
    path_hash = hashlib.md5(str(pack_path.resolve()).encode('utf-8')).hexdigest()[:6]
    return f"{safe_name}_{path_hash}"


def generate_export_filename(preset_name: str, version: str,
                              is_incremental: bool, increment: int = 0) -> str:
    safe_preset = sanitize_filename(preset_name)
    safe_version = sanitize_filename(version) if version else "v1.0.0"
    if is_incremental:
        return f"{safe_preset}-{safe_version}-更新-{increment}.fgcupdate"
    return f"{safe_preset}-{safe_version}-完整.fgcpack"


def format_size(size_bytes: int) -> str:
    try:
        size = float(size_bytes)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    except Exception:
        return f"{size_bytes} B"


def get_item_fingerprint(item_path: Path) -> dict:
    if not item_path.exists():
        return {}
    if item_path.is_file():
        try:
            stat = item_path.stat()
            return {'type': 'zip', 'size': stat.st_size, 'file_count': 1}
        except Exception:
            return {}
    total_size = 0
    file_count = 0
    try:
        for item in item_path.rglob('*'):
            if item.is_file():
                total_size += item.stat().st_size
                file_count += 1
    except Exception:
        pass
    return {'type': 'folder', 'size': total_size, 'file_count': file_count}


def fingerprints_match(a: dict, b: dict) -> bool:
    if not a or not b:
        return False
    if a.get('size') != b.get('size'):
        return False
    if a.get('file_count', 0) != b.get('file_count', 0):
        return False
    return True


def locate_tacz_by_path(path: Path) -> Path | None:
    """
    从给定路径定位 tacz 文件夹。
    1) 如果是文件，从父目录开始；
    2) 本层找 tacz；
    3) 向上逐层找（最多 8 层）。
    返回 tacz 文件夹路径，找不到返回 None。
    """
    if not path:
        return None
    try:
        p = path if path.is_dir() else path.parent
    except Exception:
        return None
    # 本层
    c = p / 'tacz'
    if c.exists() and c.is_dir():
        return c
    # 向上
    current = p
    for _ in range(8):
        c = current / 'tacz'
        if c.exists() and c.is_dir():
            return c
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


# ==================== 动画引擎 ====================
# 需求：所有交互都要有过渡动画。Tk 控件没有逐控件 alpha，能动的只有
# 「位置 / 尺寸 / 颜色」三样，所以这里统一提供缓动函数 + 颜色插值 +
# 基于 after 的补间调度，上层只描述「从哪到哪」。
#
# 每个补间用 (widget, key) 标识：重复触发会自动取消上一帧序列，
# 不会出现两条动画互相拉扯；控件销毁后 after 回调由 Tk 自动丢弃。
_TWEENS: dict = {}

# 动画总开关。
# 需求澄清：要去掉的是「图标动画」，不是页面/选项卡的滑动动画 ——
# 图标已经整体去掉，动画全部保留，所以这里是 True。
# 关掉时 tween() 会把终态直接画上、on_done 立即回调（所有调用点不用改），
# 需要静态版时把它改成 False 即可（两条循环动效会自动降级为静态，不会自递归）。
ANIMATIONS_ENABLED = True

# 补间帧率：位置类（滑块、幕布）很便宜，跑 60fps；
# 颜色类每帧都要让 CTk 重画控件（实测大卡片描边 3.05ms/帧、按钮 1.71ms/帧，
# Windows 上还要翻几倍），跑 40fps 就够顺，整体开销直接减半。
FPS_MOVE = 60
FPS_COLOR = 40


def clamp01(t):
    return 0.0 if t < 0 else (1.0 if t > 1 else float(t))


# ---------- 缓动曲线 ----------
def ease_linear(t):
    return t


def ease_out_cubic(t):
    """快速起步、缓慢收尾：位移类动画的默认曲线。"""
    return 1 - (1 - t) ** 3


def ease_out_quint(t):
    """比 cubic 更「急起缓停」，用于滑块/页面这种需要干脆利落的大位移。"""
    return 1 - (1 - t) ** 5


def ease_in_out_cubic(t):
    return 4 * t * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 3) / 2


def ease_out_back(t, overshoot=1.4):
    """带一点点回弹，用于浮层/提示的入场。"""
    t -= 1
    return t * t * ((overshoot + 1) * t + overshoot) + 1


# ---------- 数值 / 颜色插值 ----------
def lerp(a, b, t):
    return a + (b - a) * t


def hex_to_rgb(color):
    """把 '#RRGGBB' / '#RGB' 解析成 (r,g,b)；解析不了返回 None。"""
    if not isinstance(color, str):
        return None
    value = color.strip()
    if not value.startswith("#"):
        return None
    value = value[1:]
    try:
        if len(value) == 3:
            return tuple(int(c * 2, 16) for c in value)
        if len(value) >= 6:
            return (int(value[0:2], 16), int(value[2:4], 16),
                    int(value[4:6], 16))
    except ValueError:
        return None
    return None


def rgb_to_hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(
        int(max(0, min(255, round(rgb[0])))),
        int(max(0, min(255, round(rgb[1])))),
        int(max(0, min(255, round(rgb[2])))))


def lerp_color(c1, c2, t):
    """颜色插值；任一端不是合法 hex 时退化为端点取色，绝不抛异常。"""
    a = hex_to_rgb(c1)
    b = hex_to_rgb(c2)
    if a is None or b is None:
        return c1 if t < 0.5 else c2
    return rgb_to_hex((lerp(a[0], b[0], t), lerp(a[1], b[1], t),
                       lerp(a[2], b[2], t)))


# ---------- 补间调度 ----------
def cancel_tween(widget, key):
    job = _TWEENS.pop((id(widget), key), None)
    if job is not None:
        try:
            widget.after_cancel(job)
        except Exception:
            pass


def cancel_all_tweens(widget):
    for token in [k for k in _TWEENS if k[0] == id(widget)]:
        cancel_tween(widget, token[1])


_FPS_LOG = {"interval": None, "total_ms": 0.0, "frames": 0}


def _note_frame_time(interval_ms: float) -> None:
    """累计补间帧间隔，切换结束后由调用方读出来记日志。"""
    _FPS_LOG["interval"] = interval_ms
    _FPS_LOG["total_ms"] += interval_ms
    _FPS_LOG["frames"] += 1


def take_frame_stats() -> tuple:
    """取走累计的帧统计 → (平均帧间隔ms, 帧数)，并清零。"""
    frames = _FPS_LOG["frames"]
    total = _FPS_LOG["total_ms"]
    _FPS_LOG["frames"] = 0
    _FPS_LOG["total_ms"] = 0.0
    if frames <= 0 or total <= 0:
        return (0.0, 0)
    return (total / frames, frames)


def apply_animations_setting(enabled: bool) -> None:
    """把「动画」设置应用到全局开关（设置页切换时也走这里）。"""
    global ANIMATIONS_ENABLED
    ANIMATIONS_ENABLED = bool(enabled)


def tween(widget, key, duration_ms, on_frame, on_done=None,
          easing=ease_out_cubic, fps=60):
    """
    用 widget.after 驱动一条补间时间线。

    on_frame(缓动值, 线性进度) 每帧调用；进度按真实耗时计算，掉帧不会变慢。
    另有帧数上限兜底：即使事件循环被压缩（例如同步 after 的测试环境），
    动画也一定会在有限帧内收敛到终点，不会自锁。
    """
    cancel_tween(widget, key)
    if not ANIMATIONS_ENABLED:
        # 动画关闭：一帧到位，逻辑与开启时完全一致
        try:
            on_frame(1.0, 1.0)
        except Exception:
            pass
        if on_done is not None:
            try:
                on_done()
            except Exception:
                pass
        return
    interval = max(1, int(round(1000.0 / max(1, fps))))
    duration_ms = max(1, int(duration_ms))
    max_frames = int(duration_ms / interval) + 3
    token = (id(widget), key)
    start = time.perf_counter()
    state = {"frames": 0, "last": None}

    def step():
        if token not in _TWEENS:
            return
        state["frames"] += 1
        now = time.perf_counter()
        if state.get("last") is not None:
            _note_frame_time((now - state["last"]) * 1000.0)
        state["last"] = now
        elapsed = (now - start) * 1000.0
        raw = clamp01(elapsed / duration_ms)
        if state["frames"] >= max_frames:
            raw = 1.0
        try:
            on_frame(easing(raw), raw)
        except Exception:
            pass
        if raw >= 1.0:
            _TWEENS.pop(token, None)
            if on_done is not None:
                try:
                    on_done()
                except Exception:
                    pass
            return
        try:
            _TWEENS[token] = widget.after(interval, step)
        except Exception:
            _TWEENS.pop(token, None)

    # 先占位再排期：万一宿主把 after 做成同步回调，step 里的守卫也能认出自己
    _TWEENS[token] = -1
    try:
        job = widget.after(interval, step)
    except Exception:
        _TWEENS.pop(token, None)
        return
    if token in _TWEENS:
        _TWEENS[token] = job


def attach_hover_glow(widget, base_color=None, hover_color=None, duration_ms=130):
    """卡片/拖入框的 hover 描边过渡：进入混向强调色，离开混回原色。

    卡片里通常还嵌着按钮/标签，鼠标从卡片移到子控件上时 Tk 会给卡片发
    <Leave>，直接响应会来回闪。这里把「离开」延后 90ms，期间若有 <Enter>
    就撤销，等效于「指针真的移出卡片」才收光。
    """
    try:
        base_color = base_color or widget.cget("border_color")
    except Exception:
        base_color = C_BORDER_SOFT
    if hex_to_rgb(base_color) is None:
        base_color = C_BORDER_SOFT
    hover_color = hover_color or C_ACCENT_SOFT
    state = {"color": base_color, "leave_job": None}

    def _to(target, ms=duration_ms):
        start = state["color"]
        if start == target:
            return

        def frame(e, raw):
            state["color"] = lerp_color(start, target, e)
            try:
                widget.configure(border_color=state["color"])
            except Exception:
                pass

        frame(0.0, 0.0)
        tween(widget, "glow", ms, frame, easing=ease_in_out_cubic,
              fps=FPS_COLOR)

    def _cancel_leave():
        if state["leave_job"] is not None:
            try:
                widget.after_cancel(state["leave_job"])
            except Exception:
                pass
            state["leave_job"] = None

    def _on_enter(_event=None):
        _cancel_leave()
        _to(hover_color)

    def _on_leave(_event=None):
        _cancel_leave()

        def fire():
            state["leave_job"] = None
            _to(base_color)

        try:
            state["leave_job"] = widget.after(90, fire)
        except Exception:
            fire()

    try:
        widget.bind("<Enter>", _on_enter, add="+")
        widget.bind("<Leave>", _on_leave, add="+")
    except Exception:
        pass
    return widget


# ==================== 动画控件 ====================
class AnimatedButton(ctk.CTkButton):
    """带曲线过渡的按钮：hover / 按下都是逐帧混色，而不是瞬间跳色。

    CTk 自带的 hover 是「瞬时换色」，这里把它的 hover 目标设成底色把它架空，
    再由本类用补间驱动 fg_color。CTk 内部处理器与本类处理器在同一次事件
    分发里先后执行，本类每次都从当前插值色继续，因此不会看到跳变。
    """

    def __init__(self, master, base_color, hover_target, press_color=None,
                 **kwargs):
        kwargs["fg_color"] = base_color
        # hover_color 交给 CTk 用「目标色」：CTk 自己也会在进出/点击动画里
        # 瞬时刷一次颜色，如果这里填底色，就会把我逐帧混出来的中间色顶掉
        # （表现是 hover 一下又弹回原色）。填目标色两边一致，不会打架。
        kwargs["hover_color"] = hover_target
        super().__init__(master, **kwargs)
        self._base_color = base_color
        self._hover_target = hover_target
        self._press_color = press_color or hover_target
        self._current = base_color
        self._hovering = False
        try:
            self.bind("<Enter>", self._anim_enter, add="+")
            self.bind("<Leave>", self._anim_leave, add="+")
            self.bind("<ButtonPress-1>", self._anim_press, add="+")
            self.bind("<ButtonRelease-1>", self._anim_release, add="+")
        except Exception:
            pass

    def _enabled(self):
        try:
            return str(self.cget("state")) == "normal"
        except Exception:
            return True

    def _reassert(self):
        try:
            self.configure(fg_color=self._current)
        except Exception:
            pass

    def _to(self, target, duration=110):
        if target == self._current:
            return
        start = self._current

        def frame(e, raw):
            self._current = lerp_color(start, target, e)
            try:
                self.configure(fg_color=self._current)
            except Exception:
                pass

        frame(0.0, 0.0)
        tween(self, "bg", duration, frame, easing=ease_out_cubic,
              fps=FPS_COLOR)

    # 注意：处理函数一律用 _anim_* 命名，绝不能叫 _on_enter/_on_leave/
    # _on_release —— CTkButton 在 __init__ 里 bind("<ButtonRelease-1>",
    # self._on_release)，那是它执行 command 的地方；一旦被同名覆盖，
    # 按钮就变成「点下去什么都不执行」。
    def _anim_enter(self, _event=None):
        self._hovering = True
        self._reassert()
        if self._enabled():
            self._to(self._hover_target)

    def _anim_leave(self, _event=None):
        self._hovering = False
        self._reassert()
        self._to(self._base_color)

    def _anim_press(self, _event=None):
        self._reassert()
        if self._enabled():
            self._to(self._press_color, 70)

    def _anim_release(self, _event=None):
        self._reassert()
        if not self._enabled():
            return
        self._to(self._hover_target if self._hovering else self._base_color, 120)


class CanvasSegmented(Canvas):
    """自绘分段控件（侧边栏导航 / 设置页选项卡共用）。

    选中态是一块圆角药丸，切换只更新位置与配色，不做过渡动画
    （需求：去掉图标与动画，界面保持静态、瞬时切换）。
    Canvas 会把子项裁剪在自身范围内，重排不会溢到隔壁区域。

    items: [(key, text), ...]
    """

    def __init__(self, parent, items, command=None, orientation="vertical",
                 item_height=H_NAV, pad=4, gap=4, radius=R_CONTROL,
                 bg_color=C_CARD_BG, pill_color=C_ACCENT_SOFT,
                 hover_color=C_ACCENT_SOFT, text_color=C_TEXT_MAIN,
                 active_text_color=C_ACCENT, font_size=FS_BODY,
                 bold_active=False, text_anchor="w", text_pad=14,
                 duration_ms=240, hover_ms=110, width=1, height=1):
        # 自绘控件是原始像素：按 UI_SCALE 放大，否则系统 125%/150% 下会和
        # CTk 控件错位（CTk 自己会缩放，Canvas 不会）
        item_height = px(item_height)
        pad, gap, radius = px(pad), px(gap), px(radius)
        text_pad = px(text_pad)
        font_size = max(1, int(round(font_size * UI_SCALE)))
        super().__init__(parent, bg=bg_color, highlightthickness=0, bd=0,
                         width=px(width) if width > 1 else width,
                         height=px(height) if height > 1 else height)
        self._items = [(key, str(text)) for key, text in items]
        self._keys = [key for key, _ in self._items]
        self._command = command
        self._orientation = orientation
        self._item_height = item_height
        self._pad = pad
        self._gap = gap
        self._radius = radius
        self._bg = bg_color
        self._pill_color = pill_color
        self._hover_color = hover_color
        self._text_color = text_color
        self._active_text_color = active_text_color
        # 字体族要在构造时取（apply_font_fallbacks 会就地改写全局名）
        self._font = (FONT_FAMILY, font_size)
        self._font_active = (FONT_FAMILY, font_size,
                             "bold" if bold_active else "normal")
        self._text_anchor = text_anchor
        self._text_pad = text_pad
        self._duration_ms = duration_ms
        self._hover_ms = hover_ms

        self._active = None
        self._rects = []
        self._text_ids = []
        self._text_colors = {}
        self._pill_id = None
        self._pill_rect = None
        self._pill_alpha = 0.0
        self._hover_id = None
        self._hover_rect = None
        self._hover_alpha = 0.0
        self._hover_index = -1
        self._size = (0, 0)
        self._laid_out = False

        # 层级：悬停层 -> 滑块 -> 文字
        self._hover_id = self.create_polygon(
            *self._rect_points((-6, -6, -3, -3)), smooth=True, splinesteps=24,
            fill=bg_color, outline="")
        self._pill_id = self.create_polygon(
            *self._rect_points((-6, -6, -3, -3)), smooth=True, splinesteps=24,
            fill=bg_color, outline="")
        for index, (_, text) in enumerate(self._items):
            self._text_ids.append(
                self.create_text(0, 0, text=text, fill=text_color,
                                  anchor=text_anchor, font=self._font))
            self._text_colors[index] = text_color
        self.bind("<Configure>", self._on_configure)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    # ---------- 几何 ----------
    def _rect_points(self, rect):
        x1, y1, x2, y2 = rect
        radius = max(0.0, min(float(self._radius), (x2 - x1) / 2.0,
                              (y2 - y1) / 2.0))
        return [x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
                x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
                x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1]

    def _on_configure(self, event):
        size = (max(1, event.width), max(1, event.height))
        if size == self._size:
            return
        self._size = size
        self._layout(*size)

    def _layout(self, width, height):
        count = max(1, len(self._items))
        rects = []
        if self._orientation == "vertical":
            x1, x2 = self._pad, width - self._pad
            for index in range(count):
                y1 = self._pad + index * (self._item_height + self._gap)
                rects.append((x1, y1, x2, y1 + self._item_height))
        else:
            inner = width - 2 * self._pad - (count - 1) * self._gap
            item_w = inner / float(count)
            y1, y2 = self._pad, height - self._pad
            x = self._pad
            for _ in range(count):
                rects.append((x, y1, x + item_w, y2))
                x += item_w + self._gap
        self._rects = rects
        for index, text_id in enumerate(self._text_ids):
            x1, y1, x2, y2 = rects[index]
            center_y = (y1 + y2) / 2.0
            if self._text_anchor == "w":
                self.coords(text_id, x1 + self._text_pad, center_y)
            else:
                self.coords(text_id, (x1 + x2) / 2.0, center_y)
        if self._active in self._keys:
            target = rects[self._keys.index(self._active)]
            resizing = self._pill_rect is not None
            self._pill_rect = target
            self.coords(self._pill_id, *self._rect_points(target))
            if resizing:
                # 窗口尺寸变化会打乱滑块的动画轨迹：取消补间并直接落到目标项
                cancel_tween(self, "pill")
                self._pill_alpha = 1.0
                self.itemconfigure(self._pill_id, fill=self._pill_color)
            elif not self._laid_out:
                # 首次拿到真实尺寸：补一次带淡入的选中，滑块不会「啪」地出现
                self._laid_out = True
                self.select(self._active, animate=True)
            else:
                self._pill_alpha = 1.0
                self.itemconfigure(self._pill_id, fill=self._pill_color)
        if 0 <= self._hover_index < len(rects):
            self._hover_rect = rects[self._hover_index]
            self.coords(self._hover_id, *self._rect_points(self._hover_rect))

    def _index_at(self, x, y):
        for index, (x1, y1, x2, y2) in enumerate(self._rects):
            if x1 <= x <= x2 and y1 <= y <= y2:
                return index
        return -1

    # ---------- 交互 ----------
    def _on_motion(self, event):
        self._set_hover(self._index_at(event.x, event.y))

    def _on_leave(self, _event=None):
        self._set_hover(-1)

    def _on_click(self, event):
        index = self._index_at(event.x, event.y)
        if index < 0:
            return
        self.select(self._keys[index], notify=True)

    def _set_hover(self, index, animate=True):
        if index == self._hover_index:
            return
        self._hover_index = index
        active_index = (self._keys.index(self._active)
                        if self._active in self._keys else -1)
        target_alpha = 1.0 if (0 <= index < len(self._rects)
                               and index != active_index) else 0.0
        if 0 <= index < len(self._rects):
            self._hover_rect = self._rects[index]
            try:
                self.coords(self._hover_id,
                            *self._rect_points(self._hover_rect))
            except Exception:
                pass
        start_alpha = self._hover_alpha

        def paint(alpha):
            self._hover_alpha = alpha
            try:
                self.itemconfigure(
                    self._hover_id,
                    fill=lerp_color(self._bg, self._hover_color, alpha))
            except Exception:
                pass

        if not animate or self._hover_ms <= 0:
            paint(target_alpha)
            return

        def frame(e, raw):
            paint(lerp(start_alpha, target_alpha, e))

        tween(self, "hover", self._hover_ms, frame, easing=ease_out_cubic,
              fps=FPS_COLOR)

    # ---------- 选中 ----------
    def current(self):
        """当前选中项的 key（未选中返回 None）。"""
        return self._active

    def index_of(self, key):
        return self._keys.index(key) if key in self._keys else -1

    def select(self, key, animate=True, notify=False):
        if key not in self._keys:
            return
        index = self._keys.index(key)
        previous = self._active
        self._active = key
        self._animate_texts(previous, index, animate)
        self._move_pill(index, animate)
        if self._hover_index == index:
            self._set_hover(-1, animate=animate)
        if notify and callable(self._command):
            try:
                self._command(key)
            except Exception:
                pass

    def _move_pill(self, index, animate=True):
        if not self._rects:
            return
        target = self._rects[index]
        if not animate:
            self._pill_rect = target
            self._pill_alpha = 1.0
            self.coords(self._pill_id, *self._rect_points(target))
            self.itemconfigure(self._pill_id, fill=self._pill_color)
            return
        start = self._pill_rect or target
        start_alpha = self._pill_alpha

        def frame(e, raw):
            self._pill_rect = tuple(lerp(a, b, e)
                                    for a, b in zip(start, target))
            self._pill_alpha = lerp(start_alpha, 1.0, e)
            self.coords(self._pill_id, *self._rect_points(self._pill_rect))
            self.itemconfigure(
                self._pill_id,
                fill=lerp_color(self._bg, self._pill_color, self._pill_alpha))

        def done():
            self._pill_rect = target
            self._pill_alpha = 1.0
            self.coords(self._pill_id, *self._rect_points(target))
            self.itemconfigure(self._pill_id, fill=self._pill_color)

        frame(0.0, 0.0)      # 立即落到起点，滑块不等待第一帧
        tween(self, "pill", self._duration_ms, frame, done,
              easing=ease_out_cubic, fps=FPS_MOVE)

    def _animate_texts(self, previous_key, active_index, animate=True):
        for index, text_id in enumerate(self._text_ids):
            is_active = (index == active_index)
            target = self._active_text_color if is_active else self._text_color
            start = self._text_colors.get(index, self._text_color)
            try:
                self.itemconfigure(text_id,
                                   font=self._font_active if is_active
                                   else self._font)
            except Exception:
                pass
            if not animate or start == target:
                self._text_colors[index] = target
                try:
                    self.itemconfigure(text_id, fill=target)
                except Exception:
                    pass
                continue

            def frame(e, raw, i=index, s=start, t=target, item=text_id):
                color = lerp_color(s, t, e)
                self._text_colors[i] = color
                try:
                    self.itemconfigure(item, fill=color)
                except Exception:
                    pass

            frame(0.0, 0.0)
            tween(self, "text{}".format(index), 160, frame,
                  easing=ease_out_cubic, fps=FPS_COLOR)

class SlideStack:
    """把若干页面放进一个 Canvas，用缓动曲线做「推入 / 推出」切换。

    Canvas 会裁剪内嵌窗口，所以页面在滑动过程中不会溢到侧边栏上 ——
    这也是这里不直接用 place() 搬页面的原因（Tk 普通容器不裁剪子控件）。
    """

    def __init__(self, parent, bg_color=C_WINDOW_BG, duration_ms=260,
                 easing=ease_out_cubic):
        self.canvas = Canvas(parent, bg=bg_color, highlightthickness=0, bd=0)
        self.canvas.pack(fill=BOTH, expand=True)
        self.bg_color = bg_color
        self.duration_ms = duration_ms
        self.easing = easing
        self.frames = {}
        self.items = {}
        self.order = []
        self.current = None
        self._size = (1, 1)
        # 页面快照：切换动画期间只搬位图，不搬控件树
        # （搬控件树时 Tk 会把移出可视区的窗口项 unmap/remap，
        #   Windows 上 remap 那一下控件会闪成白的 —— 用户反馈的「插帧」）
        self._shots = {}
        self._slide_imgs = None
        self.canvas.bind("<Configure>", self._on_configure)

    def add(self, key, frame):
        try:
            frame.configure(fg_color=self.bg_color)
        except Exception:
            pass
        item = self.canvas.create_window(
            0, 0, window=frame, anchor="nw",
            width=self._size[0], height=self._size[1])
        self.canvas.itemconfigure(item, state="hidden")
        self.frames[key] = frame
        self.items[key] = item
        if key not in self.order:
            self.order.append(key)
        return item

    def _on_configure(self, event):
        self._size = (max(1, event.width), max(1, event.height))
        for item in self.items.values():
            try:
                self.canvas.itemconfigure(item, width=self._size[0],
                                          height=self._size[1])
            except Exception:
                pass
        if (id(self.canvas), "slide") in _TWEENS:
            # 切换动画进行中被重排：轨迹已失效，直接落到终点
            cancel_tween(self.canvas, "slide")
            self._settle()
        if self.current in self.items:
            self.canvas.coords(self.items[self.current], 0, 0)

    def _settle(self):
        """把所有页面归位：当前页贴左可见，其余隐藏。"""
        for key, item in self.items.items():
            try:
                self.canvas.coords(item, 0, 0)
                self.canvas.itemconfigure(
                    item, state="normal" if key == self.current else "hidden")
            except Exception:
                pass

    def show(self, key, animate=True, direction=1, axis="x"):
        """direction: +1 = 新页从右/下方滑进来；-1 反之。
        axis: 侧边栏是竖排 → 竖着滑；设置页选项卡是横排 → 横着滑。

        真·滑动（不是幕布、也不是淡入淡出）：新页从进入侧滑到正位，
        旧页原地不动、滑完再隐藏。只搬一棵控件树，帧开销是「两页对开」
        的一半，也不会在中间露出空白带。
        """
        if key not in self.items:
            return
        # 上一次切换还没跑完就被打断：先让它落位，否则状态和画面会不一致
        if (id(self.canvas), "slide") in _TWEENS:
            cancel_tween(self.canvas, "slide")
            self._settle()
        span = float(self._size[0] if axis == "x" else self._size[1])
        previous = self.current
        if key == previous:
            self._activate(key)      # 兜一次，保证画面和 current 一致
            return
        self.current = key
        if previous is None or not animate or not ANIMATIONS_ENABLED:
            self._activate(key)
            return

        new_item = self.items[key]
        old_item = self.items.get(previous)
        start = -span if direction >= 0 else span      # 新页起点
        # 有快照就只搬位图（控件树一动不动，不会出现 remap 闪白）
        old_shot = self._shots.get(previous)
        new_shot = self._shots.get(key)
        if old_shot is not None and new_shot is not None:
            self._slide_images(key, start, old_shot, new_shot, axis, span)
            return
        try:
            # 旧页留在原地当背景（它整页不透明，天然铺满视口，不会露底色），
            # 只搬新页 —— 每帧只搬一棵控件树，开销是对开推入的一半。
            if old_item is not None:
                if axis == "x":
                    self.canvas.coords(old_item, 0, 0)
                else:
                    self.canvas.coords(old_item, 0, 0)
                self.canvas.itemconfigure(old_item, state="normal")
            if axis == "x":
                self.canvas.coords(new_item, start, 0)
            else:
                self.canvas.coords(new_item, 0, start)
            self.canvas.itemconfigure(new_item, state="normal")
        except Exception:
            self._activate(key)
            return

        def frame(e, raw):
            pos = lerp(start, 0.0, e)
            try:
                if axis == "x":
                    self.canvas.coords(new_item, pos, 0)
                else:
                    self.canvas.coords(new_item, 0, pos)
            except Exception:
                pass

        def done():
            # 收尾：新页贴正位、旧页隐藏（_activate 里统一处理）
            self._activate(key)

        frame(0.0, 0.0)
        tween(self.canvas, "slide", self.duration_ms, frame, done,
              easing=self.easing, fps=FPS_MOVE)

    def prewarm(self):
        """把每一页都 map 一次再藏回去。

        Canvas 窗口项第一次被 map 时，Tk 要跑一遍整棵控件树的布局
        （实测设置页 78 个控件约 41ms，主页 137 个更久，Windows 还要翻倍），
        这一下正好卡在切换动画的第一帧 —— 表现就是「点了没反应，
        过一会儿才切页」。提前付掉这笔钱，之后切换就只剩搬位置。
        """
        try:
            for item in self.items.values():
                self.canvas.itemconfigure(item, state="normal")
            self.canvas.update_idletasks()
            for name, item in self.items.items():
                if name != self.current:
                    self.canvas.itemconfigure(item, state="hidden")
            self.canvas.update_idletasks()
        except Exception:
            pass

    def _capture(self, key):
        """给正在显示的页面拍一张位图，供切换动画当素材。失败返回 None。"""
        try:
            from PIL import ImageGrab, ImageTk
        except Exception:
            return None
        try:
            w, h = int(self._size[0]), int(self._size[1])
            if w < 16 or h < 16:
                return None
            cv = self.canvas
            x, y = cv.winfo_rootx(), cv.winfo_rooty()
            img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    def _schedule_capture(self, key):
        """页面稳定后补拍快照（延后一点，等布局与绘制落定）。"""
        def _do():
            if key != self.current:
                return
            shot = self._capture(key)
            if shot is not None:
                self._shots[key] = shot
        try:
            self.canvas.after(180, _do)
        except Exception:
            pass

    def _slide_images(self, key, start, old_shot, new_shot, axis, span):
        """只搬两张位图的切换动画：控件树全程不动，任何平台都不会闪白。"""
        cv = self.canvas
        park = self._park_position()
        for item in self.items.values():
            try:
                cv.coords(item, park, 0)
                cv.itemconfigure(item, state="normal")
            except Exception:
                pass
        try:
            if axis == "x":
                old_img = cv.create_image(0, 0, anchor="nw", image=old_shot)
                new_img = cv.create_image(start, 0, anchor="nw", image=new_shot)
            else:
                old_img = cv.create_image(0, 0, anchor="nw", image=old_shot)
                new_img = cv.create_image(0, start, anchor="nw", image=new_shot)
        except Exception:
            self._activate(key)
            return
        self._slide_imgs = (old_img, new_img)

        def frame(e, raw):
            pos = lerp(start, 0.0, e)
            try:
                if axis == "x":
                    cv.coords(new_img, pos, 0)
                else:
                    cv.coords(new_img, 0, pos)
            except Exception:
                pass

        def done():
            for it in (old_img, new_img):
                try:
                    cv.delete(it)
                except Exception:
                    pass
            self._slide_imgs = None
            self._activate(key)

        frame(0.0, 0.0)
        tween(cv, "slide", self.duration_ms, frame, done,
              easing=self.easing, fps=FPS_MOVE)

    def _park_position(self):
        """停靠点：视口右侧外一屏。"""
        span = float(self._size[0] if self._size[0] > 1 else 1)
        return span

    def _activate(self, key):
        """当前页摆正位，其余**停到视口外**（不是隐藏）。

        为什么不能隐藏：Canvas 窗口项在 state="hidden" 期间不会被 Tk 调整
        尺寸，再显示时还带着旧尺寸（实测设置页/日志页停在 384x483 的 CTk
        默认尺寸），滑进来时四周会露出下面那页的内容 —— 就是用户反馈的
        「撕裂」。一直保持 map、只挪到视口外，尺寸就始终跟画布一致。
        """
        if key not in self.items:
            return
        self.current = key
        park = self._park_position()
        for name, item in self.items.items():
            try:
                if name == key:
                    self.canvas.coords(item, 0, 0)
                else:
                    self.canvas.coords(item, park, 0)
                self.canvas.itemconfigure(item, state="normal")
            except Exception:
                pass
        # 页面落定后补拍快照，供下一次切换当素材
        self._schedule_capture(key)


class Toast:
    """右上角浮出提示：曲线滑入 + 自动淡出，全程不阻塞操作。"""

    def __init__(self, host, text, kind="success", duration_ms=1700):
        self.host = host
        self.color = {"success": C_SUCCESS, "info": C_ACCENT,
                      "warning": C_WARNING, "error": C_ERROR}.get(kind, C_ACCENT)
        self.frame = ctk.CTkFrame(host.overlay_host, fg_color=C_PANEL_BG,
                                   corner_radius=R_CONTROL,
                                   border_width=BORDER_W,
                                   border_color=self.color)
        self.label = ctk.CTkLabel(self.frame, text=text, text_color=self.color,
                                   font=(FONT_FAMILY, FS_SMALL),
                                   fg_color="transparent")
        self.label.pack(padx=PAD_CARD_X, pady=PAD_TIGHT)
        # _slide > 0 表示浮层右边缘越出容器右边缘（= 在屏幕外），
        # 入场从 +28 滑到 0，出场再滑回去 —— 之前符号写反了，
        # 变成「从里往外滑」，看着像往右弹一下。
        self._slide = 28.0
        self._hold_ms = duration_ms
        self._place()
        self._play_in()

    def _place(self):
        try:
            self.frame.place(relx=1.0, rely=0.0, anchor="ne",
                              x=-PAD_WINDOW + self._slide, y=PAD_WINDOW)
        except Exception:
            pass

    def _play_in(self):
        def frame(e, raw):
            self._slide = lerp(28.0, 0.0, e)
            self._place()

        def done():
            try:
                self.host.root.after(self._hold_ms, self._play_out)
            except Exception:
                pass

        frame(0.0, 0.0)
        tween(self.frame, "toast_in", 200, frame, done, easing=ease_out_back)

    def _play_out(self):
        def frame(e, raw):
            self._slide = lerp(0.0, 28.0, e)
            self._place()
            try:
                self.frame.configure(
                    fg_color=lerp_color(C_PANEL_BG, C_WINDOW_BG, e),
                    border_color=lerp_color(self.color, C_WINDOW_BG, e))
                self.label.configure(
                    text_color=lerp_color(self.color, C_WINDOW_BG, e))
            except Exception:
                pass

        tween(self.frame, "toast_out", 190, frame, self.close,
              easing=ease_in_out_cubic)

    def close(self):
        cancel_all_tweens(self.frame)
        # 清掉宿主持有的引用，否则 app._toast 会一直指向已销毁的浮层
        try:
            if getattr(self.host, "_toast", None) is self:
                self.host._toast = None
        except Exception:
            pass
        try:
            self.frame.destroy()
        except Exception:
            pass


# ==================== 控件工厂 ====================
def make_button(parent, text, command=None, width=None, state="normal", accent=False):
    """统一按钮工厂：返回的按钮自带 hover / 按下的曲线过渡。"""
    kwargs = dict(
        text=text, command=command,
        text_color=C_TEXT_INVERSE if accent else C_TEXT_MAIN,
        border_color=C_ACCENT if accent else C_BORDER_SOFT,
        border_width=BORDER_W, corner_radius=R_CONTROL,
        font=(FONT_FAMILY, FS_BODY), height=H_CONTROL, state=state)
    if width is not None:
        kwargs['width'] = width
    if accent:
        # 按下要更沉一档：之前 press_color 直接用了 hover 色，按下去看不出变化
        return AnimatedButton(parent, C_ACCENT, C_ACCENT_HOVER,
                               press_color=C_ACCENT_PRESSED, **kwargs)
    return AnimatedButton(parent, C_PANEL_ALT_BG, C_ACCENT_SOFT,
                           press_color=lerp_color(C_ACCENT_SOFT, C_ACCENT, 0.45),
                           **kwargs)


def make_entry(parent, textvariable=None, placeholder="", width=None):
    kwargs = dict(
        fg_color=C_INPUT_BG, border_color=C_BORDER_SOFT, border_width=BORDER_W,
        corner_radius=R_CONTROL, text_color=C_TEXT_MAIN,
        placeholder_text=placeholder, placeholder_text_color=C_TEXT_MUTED,
        font=(FONT_FAMILY, FS_BODY), height=H_CONTROL)
    if textvariable is not None:
        kwargs['textvariable'] = textvariable
    if width is not None:
        kwargs['width'] = width
    return ctk.CTkEntry(parent, **kwargs)


def make_display_box(parent, text="", width=None, height=H_CONTROL):
    frame = ctk.CTkFrame(parent, fg_color=C_INPUT_BG, border_color=C_BORDER_SOFT,
                          border_width=BORDER_W, corner_radius=R_CONTROL,
                          height=height)
    frame.pack_propagate(False)
    label = ctk.CTkLabel(frame, text=text, text_color=C_TEXT_SECONDARY,
                          font=(FONT_FAMILY, FS_SMALL), anchor="w",
                          fg_color="transparent")
    label.pack(fill=BOTH, expand=True, padx=PAD_INNER)
    return frame, label


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
                  font=(FONT_FAMILY, font_size, weight),
                  anchor="w")
    kwargs['fg_color'] = bg if bg is not None else "transparent"
    # justify 只在显式传入时下发，避免影响其余单行标签的外观。
    # （原来多行提示写的是 justify=LEFT，但本工厂没有该参数 -> 一进设置页就 TypeError）
    if justify is not None:
        kwargs['justify'] = justify
    return ctk.CTkLabel(parent, **kwargs)


# ==================== 窗口内覆盖层对话框 ====================
# 需求：所有提示/确认都出现在主程序窗口内部，不开新的系统窗口。
# tkinter.messagebox 是 Tk 原生模态对话框（必然新开窗口），所以这里自绘：
#   · 遮罩 + 居中卡片用 place() 铺在主窗口内容区（含侧边栏）之上；
#   · 全部用 relx/rely/relwidth/relheight 相对定位，窗口 resize 时由 Tk 自动跟随，
#     因此不需要任何 <Configure> 绑定，也就不会在拖拽窗口时触发重排；
#   · 模态阻塞用 root.wait_variable() 的嵌套事件循环，不创建任何窗口，无需 grab_set；
#   · 模态性：遮罩吃掉鼠标事件、focus_set 把键盘焦点收进卡片、Tab 只在卡片内循环、
#     ESC 关闭（等价于「取消/否」）、点遮罩本身不关闭；
#   · Tk 控件不支持逐控件 alpha，遮罩用纯色 C_PANEL_ALT_BG 近似半透明。

_OVERLAY_HOST = None      # 由 PulsesSwapApp.setup_ui() 注册的宿主（见 set_overlay_host）
_OVERLAY_WIDTH = {"info": 460, "warning": 480, "error": 560, "question": 480}
_OVERLAY_STACK = []       # 当前打开的覆盖层（后开的在最上层），用于多层弹窗时的 ESC 判定
_DEFAULT_BUTTONS = {
    "info":     [("确定", True, True)],
    "warning":  [("确定", True, True)],
    "error":    [("确定", True, True)],
    "question": [("是", True, True), ("否", False, False)],
}


def set_overlay_host(host):
    """注册覆盖层宿主（PulsesSwapApp 实例）；必须晚于主窗口骨架创建。"""
    global _OVERLAY_HOST
    _OVERLAY_HOST = host


def get_overlay_host():
    return _OVERLAY_HOST


def _run_modal(build_and_wait):
    """
    把「建卡片 + 嵌套等待」整体切到主线程执行。
    导入/导出等 worker 线程里也会弹确认框，而 Tk 调用不是线程安全的，
    所以这里统一用 root.after 回主线程，再用 Event 把结果带回业务线程。
    """
    if threading.current_thread() is threading.main_thread():
        return build_and_wait()
    host = _OVERLAY_HOST
    if host is None:
        # 宿主未注册（主窗口骨架还没建好）时没有可用的 after 通道，只能就地构建
        return build_and_wait()
    box, done = {}, threading.Event()

    def _call():
        try:
            box['value'] = build_and_wait()
        except Exception as exc:            # pragma: no cover - 纯防御
            box['error'] = exc
        finally:
            done.set()

    try:
        ui_call(host.root, _call)
    except Exception:
        return None
    done.wait()
    if 'error' in box:
        raise box['error']
    return box.get('value')


class _OverlayCardBase:
    """
    覆盖层卡片的内容构建 + 关闭/等待语义。
    容器（窗口内遮罩 / 启动兜底的 Toplevel）由子类提供，内容代码完全复用。
    """

    def __init__(self, width=480, escape_value=None):
        self.width = width
        self.escape_value = escape_value
        self.result = escape_value
        self.focusables = []
        self._closed = False
        self.root = None
        self.body = None

    # ---------- 生命周期（容器部分由子类实现） ----------
    def _teardown(self):
        raise NotImplementedError

    def _release(self):
        """子类用于唤醒阻塞中的 wait()。"""
        return None

    def wait(self):
        raise NotImplementedError

    def close(self, value=None):
        if self._closed:
            return
        self._closed = True
        self.result = value
        try:
            self._teardown()
        except Exception:
            pass
        try:
            self._release()
        except Exception:
            pass

    # ---------- 键盘模态 ----------
    def _is_top(self):
        """是否是当前最上层的卡片（多层覆盖时只有最上层响应 ESC）。"""
        return True

    def _on_escape(self, event=None):
        if not self._is_top():
            return "break"
        self.close(self.escape_value)
        return "break"

    def _on_return(self, value):
        self.close(value)
        return "break"

    def _on_tab(self, event=None):
        return self._cycle_focus(1)

    def _on_tab_back(self, event=None):
        return self._cycle_focus(-1)

    def _cycle_focus(self, step):
        """Tab 只在卡片内循环，避免焦点跑到遮罩下面的主界面控件上。"""
        ring = [w for w in self.focusables if w is not None]
        if not ring:
            return "break"
        try:
            index = ring.index(self.root.focus_get())
        except Exception:
            index = -1 if step > 0 else 0
        try:
            ring[(index + step) % len(ring)].focus_set()
        except Exception:
            pass
        return "break"

    def register_focusable(self, widget):
        self.focusables.append(widget)
        return widget

    def _key_widgets(self):
        return []

    # ---------- 内容构建 ----------
    def add_title(self, text, fg=None):
        label = make_label(self.body, text=text,
                            fg=C_ACCENT if fg is None else fg,
                            font_size=FS_SUBHEAD, bold=True)
        label.pack(anchor=W, pady=(0, PAD_TIGHT))
        return label

    def add_text(self, text, fg=None, font_size=FS_BODY, wrap_extra=6):
        label = make_label(self.body, text=text,
                            fg=C_TEXT_MAIN if fg is None else fg,
                            font_size=font_size)
        label.configure(
            wraplength=max(200, self.width - 2 * PAD_DIALOG - wrap_extra),
            justify=LEFT, anchor=W)
        label.pack(anchor=W, fill=X, pady=(0, PAD_INNER))
        return label

    def add_buttons(self, buttons, default=None):
        """buttons: [(文字, 返回值, 是否强调色)]；default 为回车触发的返回值。"""
        default_value = buttons[0][1] if default is None else default
        bar = ctk.CTkFrame(self.body, fg_color="transparent")
        bar.pack(fill=X, side=BOTTOM, pady=(PAD_DIALOG, 0))
        for text, value, accent in reversed(buttons):
            btn = make_button(bar, text,
                               command=lambda v=value: self.close(v),
                               accent=accent)
            btn.pack(side=RIGHT, padx=(PAD_TIGHT, 0))
            self.register_focusable(btn)
            try:
                btn.bind("<Return>", lambda e, v=value: self._on_return(v))
            except Exception:
                pass
        for widget in self._key_widgets():
            try:
                widget.bind("<Return>",
                             lambda e, v=default_value: self._on_return(v))
            except Exception:
                pass
        return bar


class OverlayCard(_OverlayCardBase):
    """窗口内覆盖层：遮罩 + 居中卡片，全部相对定位，窗口 resize 时自动跟随。"""

    def __init__(self, host, width=480, escape_value=None):
        super().__init__(width=width, escape_value=escape_value)
        self.host = host
        self.root = host.root
        self._esc_funcid = None
        self._var = IntVar(master=self.root)

        self.mask = ctk.CTkFrame(host.overlay_host, fg_color=C_PANEL_ALT_BG,
                                  corner_radius=0)
        self.mask.place(relx=0.0, rely=0.0, relwidth=1.0, relheight=1.0)
        self.mask.lift()
        # height=1 让卡片高度完全由内容决定（CTkFrame 默认 200x200 会撑出空白）
        self.card = ctk.CTkFrame(self.mask, fg_color=C_PANEL_BG,
                                  corner_radius=R_CARD, border_width=BORDER_W,
                                  border_color=C_BORDER_SOFT,
                                  width=width, height=1)
        self.card.place(relx=0.5, rely=0.5, anchor="center")
        self.body = ctk.CTkFrame(self.card, fg_color="transparent")
        self.body.pack(fill=BOTH, expand=True, padx=PAD_DIALOG, pady=PAD_DIALOG)

        try:
            # ESC 走 root 级绑定（子控件拿到焦点后仍然有效），关闭时按 funcid 解绑
            self._esc_funcid = self.root.bind("<Escape>", self._on_escape, add="+")
            for widget in self._key_widgets():
                widget.bind("<Escape>", self._on_escape)
                widget.bind("<Tab>", self._on_tab)
                widget.bind("<Shift-Tab>", self._on_tab_back)
            self.mask.focus_set()
        except Exception:
            pass
        self._play_entrance()
        _OVERLAY_STACK.append(self)

    def _play_entrance(self):
        """卡片入场：从下方 4.5% 处曲线滑到居中，同时描边从强调色淡回发丝色。"""
        def frame(e, raw):
            try:
                self.card.place_configure(rely=lerp(0.545, 0.5, e))
                self.card.configure(
                    border_color=lerp_color(C_ACCENT_SOFT, C_BORDER_SOFT, e))
            except Exception:
                pass

        frame(0.0, 0.0)
        tween(self.card, "entrance", 190, frame, easing=ease_out_cubic)

    def _key_widgets(self):
        return [self.mask, self.card, self.body]

    def _is_top(self):
        return bool(_OVERLAY_STACK) and _OVERLAY_STACK[-1] is self

    def _teardown(self):
        try:
            if _OVERLAY_STACK and _OVERLAY_STACK[-1] is self:
                _OVERLAY_STACK.pop()
        except Exception:
            pass
        try:
            if self._esc_funcid is not None:
                self.root.unbind("<Escape>", self._esc_funcid)
        except Exception:
            pass
        try:
            self.mask.destroy()
        except Exception:
            pass

    def _release(self):
        self._var.set(1)          # 唤醒 wait_variable 的嵌套事件循环

    def wait(self):
        self.root.wait_variable(self._var)
        if not self._closed:
            # 防御：wait 已返回但卡片没走 close()（例如变量被外部置位），
            # 这里补一次收尾，保证遮罩/栈不会残留
            self.close(self.result)
        return self.result


class ToplevelCard(_OverlayCardBase):
    """
    兜底容器：宿主尚未注册（主窗口骨架还没建好）时才会用到，退化成一个 Toplevel。
    内容代码与窗口内覆盖层完全共用，保证极端情况下提示不会静默丢失。
    """

    def __init__(self, parent, width=520, height=560, escape_value=None,
                 title=PROJECT_NAME):
        super().__init__(width=width, escape_value=escape_value)
        self.root = parent
        self.window = ctk.CTkToplevel(parent)
        self.window.title(title)
        self.window.geometry(f"{width}x{height}")
        self.window.configure(fg_color=C_WINDOW_BG)
        # 子窗口图标与主窗口保持一致（apply_window_icon 定义在文件末尾，
        # 运行时才解析，这里调用没有先后顺序问题）
        try:
            apply_window_icon(self.window)
        except Exception:
            pass
        self.body = ctk.CTkFrame(self.window, fg_color="transparent")
        self.body.pack(fill=BOTH, expand=True, padx=PAD_DIALOG, pady=PAD_DIALOG)
        try:
            self.window.transient(parent)
        except Exception:
            pass
        try:
            self.window.grab_set()
            self.window.protocol("WM_DELETE_WINDOW",
                                  lambda: self.close(escape_value))
            self.window.bind("<Escape>", self._on_escape)
        except Exception:
            pass

    def _key_widgets(self):
        return [self.window, self.body]

    def _teardown(self):
        try:
            self.window.destroy()
        except Exception:
            pass

    def wait(self):
        self.window.wait_window()
        return self.result


def make_card(host, parent, width=520, escape_value=None, title=PROJECT_NAME):
    """有宿主就用窗口内覆盖层；没有宿主（启动极早期）才退化成 Toplevel。"""
    if host is not None:
        return OverlayCard(host, width=width, escape_value=escape_value)
    return ToplevelCard(parent, width=width, escape_value=escape_value,
                         title=title)


def show_message(parent, title, text, kind="info", buttons=None, escape_value=None):
    """
    自绘的窗口内对话框（替代 messagebox.*）。
    parent 只用于兼容原调用形式；宿主统一走 set_overlay_host 注册的实例。
    返回被点击按钮的值：普通提示为 True，ask 类为 True/False，ESC 为 escape_value。
    """
    if escape_value is None:
        escape_value = False if kind == "question" else True
    specs = buttons if buttons is not None else _DEFAULT_BUTTONS.get(
        kind, _DEFAULT_BUTTONS["info"])

    def _build_and_wait():
        card = make_card(_OVERLAY_HOST, parent,
                          width=_OVERLAY_WIDTH.get(kind, 480),
                          escape_value=escape_value, title=title)
        card.add_title(title)
        card.add_text(text)
        card.add_buttons(specs)
        return card.wait()

    return _run_modal(_build_and_wait)


def show_info(title, message="", parent=None, **kwargs):
    return show_message(parent, title, message, "info")


def show_warning(title, message="", parent=None, **kwargs):
    return show_message(parent, title, message, "warning")


def show_error(title, message="", parent=None, **kwargs):
    return show_message(parent, title, message, "error")


def ask_yes_no(title, message="", parent=None, **kwargs):
    return bool(show_message(parent, title, message, "question"))


def ask_ok_cancel(title, message="", parent=None, **kwargs):
    return bool(show_message(
        parent, title, message, "question",
        buttons=[("确定", True, True), ("取消", False, False)],
        escape_value=False))


class _MessageBoxCompat:
    """
    兼容垫片：本文件已把所有 messagebox.* 调用点换成 show_*/ask_*（见上方），
    这个对象保证万一还有漏改或后续新增的 messagebox.xxx(...) 调用，
    也仍然走窗口内覆盖层，而不是退回系统新窗口。
    """

    @staticmethod
    def showinfo(title=None, message="", **kwargs):
        return show_info(title, message)

    @staticmethod
    def showwarning(title=None, message="", **kwargs):
        return show_warning(title, message)

    @staticmethod
    def showerror(title=None, message="", **kwargs):
        return show_error(title, message)

    @staticmethod
    def askyesno(title=None, message="", **kwargs):
        return ask_yes_no(title, message)

    @staticmethod
    def askokcancel(title=None, message="", **kwargs):
        return ask_ok_cancel(title, message)

    @staticmethod
    def askquestion(title=None, message="", **kwargs):
        return "yes" if ask_yes_no(title, message) else "no"


messagebox = _MessageBoxCompat()


# ==================== 数据库定位 ====================
class DatabaseLocator:
    @staticmethod
    def load_db_path() -> Path | None:
        # 先读当前数据目录下的配置，再兼容旧版写在程序目录的配置
        candidates = [BOOTSTRAP_FILE]
        if LEGACY_BOOTSTRAP_FILE != BOOTSTRAP_FILE:
            candidates.append(LEGACY_BOOTSTRAP_FILE)
        for cfg in candidates:
            try:
                if not cfg.exists():
                    continue
                with open(cfg, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                path = data.get('database_path')
                if path:
                    return Path(path)
            except Exception:
                continue
        return None

    @staticmethod
    def save_db_path(path: Path) -> bool:
        targets = [BOOTSTRAP_FILE]
        if LEGACY_BOOTSTRAP_FILE != BOOTSTRAP_FILE:
            targets.append(LEGACY_BOOTSTRAP_FILE)
        last_error = None
        for cfg in targets:
            try:
                cfg.parent.mkdir(parents=True, exist_ok=True)
                with open(cfg, 'w', encoding='utf-8') as f:
                    json.dump({'database_path': str(path)}, f,
                              indent=2, ensure_ascii=False)
                return True
            except Exception as e:
                last_error = e
        safe_print(f"保存数据库位置失败: {type(last_error).__name__}: {last_error}")
        return False

    @staticmethod
    def is_valid_database(path: Path) -> bool:
        if not path.exists() or not path.is_dir():
            return False
        if (path / '.settings.json').exists() or (path / '.global.json').exists():
            return True
        try:
            for sub in path.iterdir():
                if sub.is_dir() and (sub / 'index.json').exists():
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def is_empty_folder(path: Path) -> bool:
        if not path.exists() or not path.is_dir():
            return False
        try:
            return not any(path.iterdir())
        except Exception:
            return False

    @staticmethod
    def init_database_detailed(path: Path) -> tuple[bool, str]:
        """创建数据库。失败时把真实异常类型与消息一并返回，交给调用方展示。"""
        try:
            path.mkdir(parents=True, exist_ok=True)
            sf = path / '.settings.json'
            if not sf.exists():
                with open(sf, 'w', encoding='utf-8') as f:
                    json.dump({'storage_mode': 'isolated', 'role': 'player'},
                              f, indent=2, ensure_ascii=False)
            gf = path / '.global.json'
            if not gf.exists():
                with open(gf, 'w', encoding='utf-8') as f:
                    json.dump({'recent_packs': []}, f, indent=2, ensure_ascii=False)
            return True, ""
        except Exception as e:
            detail = f"{type(e).__name__}: {e}"
            safe_print(f"初始化数据库失败: {detail} (位置: {path})")
            return False, detail

    @staticmethod
    def init_database(path: Path) -> bool:
        ok, _ = DatabaseLocator.init_database_detailed(path)
        return ok


# ==================== 旧版 FGC v2 数据库适配 ====================
class LegacyDatabaseMigrator:
    @staticmethod
    def is_legacy_database(path: Path) -> bool:
        if not path or not path.exists() or not path.is_dir():
            return False
        if (path / LEGACY_MIGRATED_MARKER).exists():
            return False
        if path.name == LEGACY_DB_DIRNAME:
            return True
        cache = path / LEGACY_CACHE_FILE
        if cache.exists():
            try:
                with open(cache, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                presets = data.get('presets', {})
                for info in presets.values():
                    if 'version' not in info:
                        return True
                    for v in info.get('gunpacks', {}).values():
                        if isinstance(v, list):
                            return True
            except Exception:
                pass
        try:
            for sub in path.iterdir():
                if sub.is_dir() and not sub.name.startswith('.'):
                    idx = sub / 'index.json'
                    if idx.exists() and not (sub / 'version.txt').exists():
                        return True
        except Exception:
            pass
        return False

    @staticmethod
    def find_legacy_databases(root: Path) -> list[Path]:
        found = []
        candidates = [
            root / LEGACY_DB_DIRNAME,
            root / 'tacz' / LEGACY_DB_DIRNAME,
        ]
        if root.parent:
            candidates.append(root.parent / LEGACY_DB_DIRNAME)
        for c in candidates:
            if c and c.exists() and LegacyDatabaseMigrator.is_legacy_database(c):
                found.append(c)
        return found

    @staticmethod
    def convert_preset_index(legacy_data: dict, preset_path: Path) -> dict:
        raw = legacy_data.get('gunpacks', {})
        standard = {}
        for name, value in raw.items():
            item_path = preset_path / name
            fp = get_item_fingerprint(item_path)
            if fp:
                standard[name] = fp
            elif isinstance(value, (list, tuple)):
                standard[name] = {
                    'type': 'zip', 'size': 0, 'file_count': 1,
                    'legacy_hash': str(value[0]) if value else ''}
            elif isinstance(value, dict):
                standard[name] = value
            else:
                standard[name] = {'type': 'zip', 'size': 0, 'file_count': 1}

        version = (legacy_data.get('version')
                   or legacy_data.get('description')
                   or 'v1.0.0')
        return {
            'name': legacy_data.get('name', preset_path.name),
            'version': version,
            'description': legacy_data.get('description', ''),
            'gunpacks': standard,
            'applied': legacy_data.get('applied', False),
            'incremental_count': legacy_data.get('incremental_count', 0),
            'legacy_migrated': True,
        }

    @staticmethod
    def migrate_legacy_to_new(legacy_db: Path, new_db: Path,
                              log_manager=None,
                              conflict_mode: str = 'rename',
                              progress_callback=None,
                              after_migrate: str = 'mark') -> dict:
        stats = {'migrated': 0, 'skipped': 0, 'renamed': 0,
                 'errors': [], 'disposed': 'none'}
        new_db.mkdir(parents=True, exist_ok=True)

        try:
            preset_dirs = [p for p in legacy_db.iterdir()
                           if p.is_dir() and not p.name.startswith('.')]
        except Exception as e:
            if log_manager:
                log_manager.log(f"扫描旧版数据库失败: {e}", 'ERROR')
            stats['errors'].append(f"扫描失败: {e}")
            return stats

        total = len(preset_dirs)
        if log_manager:
            log_manager.log(
                f"开始适配旧版数据库，共 {total} 个预设", 'PROCESS')

        for idx, preset_dir in enumerate(preset_dirs):
            target_name = preset_dir.name
            target_path = new_db / target_name

            if target_path.exists():
                if conflict_mode == 'skip':
                    stats['skipped'] += 1
                    if log_manager:
                        log_manager.log(f"跳过已存在预设: {target_name}", 'WARNING')
                    if progress_callback:
                        progress_callback(idx + 1, total, f"跳过 {target_name}")
                    continue
                elif conflict_mode == 'rename':
                    i = 1
                    while (new_db / f"{target_name}_legacy{i}").exists():
                        i += 1
                    target_name = f"{target_name}_legacy{i}"
                    target_path = new_db / target_name
                    stats['renamed'] += 1
                elif conflict_mode == 'overwrite':
                    shutil.rmtree(target_path, ignore_errors=True)

            try:
                shutil.copytree(preset_dir, target_path)
                idx_file = target_path / 'index.json'
                new_data = None
                if idx_file.exists():
                    with open(idx_file, 'r', encoding='utf-8') as f:
                        legacy_data = json.load(f)
                    new_data = LegacyDatabaseMigrator.convert_preset_index(
                        legacy_data, target_path)
                    with open(idx_file, 'w', encoding='utf-8') as f:
                        json.dump(new_data, f, indent=2, ensure_ascii=False)
                with open(target_path / 'version.txt', 'w', encoding='utf-8') as f:
                    f.write((new_data or {}).get('version', 'v1.0.0'))
                stats['migrated'] += 1
                if log_manager:
                    log_manager.log(
                        f"已迁移预设: {preset_dir.name} -> {target_name}", 'SUCCESS')
            except Exception as e:
                stats['errors'].append(f"{preset_dir.name}: {e}")
                if log_manager:
                    log_manager.log(f"迁移 {preset_dir.name} 失败: {e}", 'ERROR')

            if progress_callback:
                progress_callback(idx + 1, total, f"迁移 {preset_dir.name}")

        if after_migrate == 'mark':
            try:
                marker = legacy_db / LEGACY_MIGRATED_MARKER
                with open(marker, 'w', encoding='utf-8') as f:
                    json.dump({
                        'migrated_to': str(new_db),
                        'migrated_at': datetime.now().isoformat(),
                        'migrated_count': stats['migrated'],
                        'renamed_count': stats['renamed'],
                        'skipped_count': stats['skipped'],
                    }, f, indent=2, ensure_ascii=False)
                stats['disposed'] = 'marked'
                if log_manager:
                    log_manager.log(
                        f"已在旧库写入迁移标记: {marker}", 'SUCCESS')
            except Exception as e:
                stats['errors'].append(f"写迁移标记失败: {e}")
                if log_manager:
                    log_manager.log(f"写迁移标记失败: {e}", 'ERROR')

        elif after_migrate == 'delete':
            try:
                ok = move_to_recycle_bin(legacy_db)
                if ok:
                    stats['disposed'] = 'recycled'
                    if log_manager:
                        log_manager.log(
                            f"旧版数据库已移入回收站: {legacy_db}", 'SUCCESS')
                else:
                    shutil.rmtree(legacy_db, ignore_errors=True)
                    stats['disposed'] = 'deleted'
                    if log_manager:
                        log_manager.log(
                            f"旧版数据库已删除（无法移入回收站）: {legacy_db}",
                            'SUCCESS')
            except Exception as e:
                stats['errors'].append(f"删除旧库失败: {e}")
                if log_manager:
                    log_manager.log(f"删除旧库失败: {e}", 'ERROR')

        return stats


# ==================== 数据库定位对话框 ====================
class DatabaseLocatorDialog:
    def __init__(self, parent):
        self.parent = parent
        self.result: Path | None = None
        self.legacy_to_migrate: Path | None = None

    def show(self) -> Path | None:
        # 需求：这是「选文件夹」的界面，做成独立小窗口（640x520），
        # 而不是铺满主窗口的覆盖层 —— 覆盖层在主窗口最大化时看着像占满全屏。
        dlg_w = DLG_LOCATOR[0]
        card = ToplevelCard(self.parent, width=dlg_w, height=DLG_LOCATOR[1],
                             escape_value=None, title="选择数据库位置")
        frame = card.body

        make_label(frame, text="欢迎使用 Pulses Swap",
                    fg=C_ACCENT, font_size=FS_TITLE, bold=True).pack(
                        anchor=W, pady=(0, PAD_TIGHT))
        make_label(frame, text="Step 1 · 选择数据库位置",
                    fg=C_GUIDE_GLOW, font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, pady=(0, PAD_INNER))

        desc = make_label(frame,
            text="首次启动需要指定数据库位置。\n"
                 "数据库用于保存预设、校验数据和程序设置。\n\n"
                 "• 新用户 → 点「新建数据库」或「使用默认位置」\n"
                 "• 已有 Pulses Swap 数据库 → 点「定位已有数据库」\n"
                 "• 有旧版 FGC_database → 点「适配旧版数据库」",
            fg=C_TEXT_SECONDARY, font_size=FS_BODY)
        desc.configure(wraplength=dlg_w - 2 * PAD_DIALOG - 6, justify=LEFT, anchor=W)
        desc.pack(anchor=W, fill=X, pady=(0, PAD_DIALOG))

        loc_frame = ctk.CTkFrame(frame, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                   border_width=BORDER_W, border_color=C_BORDER_SOFT)
        loc_frame.pack(fill=X, pady=(0, PAD_DIALOG))

        make_label(loc_frame,
                    text=("默认数据库位置（与程序同目录）:" if IS_PORTABLE_MODE
                          else "默认数据库位置（用户数据目录）:"),
                    fg=C_TEXT_SECONDARY, font_size=FS_SMALL).pack(
                        anchor=W, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        make_label(loc_frame, text=str(DEFAULT_DB_DIR),
                    fg=C_TEXT_MAIN, font_size=FS_SMALL).pack(
                        anchor=W, padx=PAD_CARD_X, pady=(0, PAD_CARD_Y))

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill=X, pady=(0, PAD_TIGHT))

        btn_refs = {}

        def _highlight(target_key):
            for k, b in btn_refs.items():
                try:
                    if k == target_key:
                        b.configure(border_color=C_GUIDE_GLOW,
                                    border_width=BORDER_W_FOCUS)
                    else:
                        b.configure(border_color=C_BORDER_SOFT,
                                    border_width=BORDER_W)
                except Exception:
                    pass

        def _init_or_report(path, title):
            """创建数据库；失败时把真实异常类型/消息带进弹窗，而不是只说一句失败。"""
            ok, err = DatabaseLocator.init_database_detailed(path)
            if not ok:
                show_error(
                    "错误", f"{title}：{err}\n位置: {path}", parent=self.parent)
            return ok

        def _choose(path, legacy=None):
            """选定数据库并关闭覆盖层。"""
            self.result = path
            if legacy is not None:
                self.legacy_to_migrate = legacy
            card.close(True)

        def on_existing():
            folder = filedialog.askdirectory(
                title="选择已有的数据库文件夹",
                initialdir=str(PROGRAM_DIR),
                parent=self.parent)
            if not folder:
                return
            path = Path(folder)
            if LegacyDatabaseMigrator.is_legacy_database(path):
                if ask_yes_no("检测到旧版数据库",
                    "该文件夹是旧版 FGC_database。\n\n"
                    "是否先适配为新版数据库？", parent=self.parent):
                    if _init_or_report(DEFAULT_DB_DIR, "创建数据库失败"):
                        _choose(DEFAULT_DB_DIR, legacy=path)
                return
            if DatabaseLocator.is_valid_database(path):
                _choose(path)
            else:
                show_error("错误",
                    "所选文件夹不是有效的数据库。\n\n"
                    "有效的数据库应包含 .settings.json 或预设子文件夹。",
                    parent=self.parent)

        def on_legacy():
            folder = filedialog.askdirectory(
                title="选择旧版 FGC_database 文件夹",
                initialdir=str(PROGRAM_DIR),
                parent=self.parent)
            if not folder:
                return
            path = Path(folder)
            if not LegacyDatabaseMigrator.is_legacy_database(path):
                if (path / LEGACY_MIGRATED_MARKER).exists():
                    show_info("已迁移",
                        "该旧版数据库已被标记为「已迁移」。\n\n"
                        "如需重新适配，请手动删除旧库根目录下的\n"
                        f"{LEGACY_MIGRATED_MARKER} 文件后再试。",
                        parent=self.parent)
                else:
                    show_error("错误",
                        "所选文件夹不是旧版 FGC_database。\n\n"
                        "旧版数据库应包含预设子文件夹和 index.json。",
                        parent=self.parent)
                return
            if _init_or_report(DEFAULT_DB_DIR, "创建数据库失败"):
                _choose(DEFAULT_DB_DIR, legacy=path)

        def on_new():
            # 默认在数据目录下新建（便携模式即程序目录）
            default_hint = ("程序目录" if IS_PORTABLE_MODE else "用户数据目录")
            if ask_yes_no("新建数据库",
                f"是否在{default_hint}下新建数据库？\n\n"
                f"位置: {DEFAULT_DB_DIR}\n\n"
                f"选「否」可手动选择其他文件夹。",
                parent=self.parent):
                path = DEFAULT_DB_DIR
            else:
                folder = filedialog.askdirectory(
                    title="选择用于新建数据库的文件夹",
                    initialdir=str(PROGRAM_DIR),
                    parent=self.parent)
                if not folder:
                    return
                path = Path(folder)
            if path.exists() and not DatabaseLocator.is_empty_folder(path):
                if DatabaseLocator.is_valid_database(path):
                    _choose(path)
                    return
                show_error("错误",
                    "所选文件夹非空且不是有效数据库。\n\n"
                    "请选择一个空文件夹用于新建数据库。",
                    parent=self.parent)
                return
            if _init_or_report(path, "创建数据库失败"):
                _choose(path)

        def on_default():
            if _init_or_report(DEFAULT_DB_DIR, "创建默认数据库失败"):
                _choose(DEFAULT_DB_DIR)

        b_exist = make_button(btn_frame, "定位已有数据库", command=on_existing)
        b_exist.pack(side=LEFT, padx=(0, PAD_TIGHT))
        b_legacy = make_button(btn_frame, "适配旧版数据库", command=on_legacy)
        b_legacy.pack(side=LEFT, padx=PAD_TIGHT)
        b_new = make_button(btn_frame, "新建数据库", command=on_new, accent=True)
        b_new.pack(side=LEFT, padx=PAD_TIGHT)
        b_default = make_button(btn_frame, "使用默认位置", command=on_default)
        b_default.pack(side=LEFT, padx=PAD_TIGHT)
        for _btn in (b_exist, b_legacy, b_new, b_default):
            card.register_focusable(_btn)

        btn_refs = {
            'exist': b_exist, 'legacy': b_legacy,
            'new': b_new, 'default': b_default,
        }
        _highlight('new')

        card.wait()
        return self.result


# ==================== 设置管理 ====================
class AppSettings:
    def __init__(self):
        self.storage_mode = "isolated"
        self.animations = True
        self.role = "player"
        self._settings_file: Path | None = None

    def bind_database(self, db_path: Path):
        self._settings_file = db_path / ".settings.json"
        self.load()
        apply_animations_setting(self.animations)

    def load(self):
        if self._settings_file and self._settings_file.exists():
            try:
                with open(self._settings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.storage_mode = data.get('storage_mode', 'isolated')
                self.role = data.get('role', 'player')
                self.animations = bool(data.get('animations', True))
            except Exception:
                pass

    def save(self) -> bool:
        if not self._settings_file:
            return False
        try:
            self._settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._settings_file, 'w', encoding='utf-8') as f:
                json.dump({'storage_mode': self.storage_mode,
                           'role': self.role,
                           'animations': self.animations},
                          f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"保存设置失败: {e}")
            return False

    def get_db_path(self, pack_path: Path) -> Path:
        if not self._settings_file:
            return DEFAULT_DB_DIR / "unknown"
        base = self._settings_file.parent
        if self.storage_mode == "merged":
            return base
        return pack_path / "PulsesSwap_database"


# ==================== 日志系统 ====================
class LogManager:
    """日志缓冲 + 显示。

    显示分两档：
      · 单行模式（默认）：只显示「最近一条非细节日志」，避免回显类噪声刷屏；
      · 完整日志（日志页「显示完整日志」）：显示全部，含细节/进度条目。
    细节条目仍然会被记录，只是单行模式下不占用显示位。
    """

    # 这些层级默认算「细节日志」，只有完整日志模式才显示
    VERBOSE_LEVELS = ("DEBUG", "PROCESS")

    def __init__(self, text_widget, root):
        self.text_widget = text_widget
        self.root = root
        self.full_log = []          # [(log_line, level, verbose)]
        self.show_full = False
        self.widgets = []           # 同一份日志可以同时投到多个文本框
        self._configure_tags(text_widget)
        self.widgets.append(text_widget)

    @staticmethod
    def _configure_tags(widget):
        try:
            inner = widget._textbox
            inner.tag_configure('INFO', foreground=C_TEXT_MAIN)
            inner.tag_configure('WARNING', foreground=C_WARNING)
            inner.tag_configure('ERROR', foreground=C_ERROR)
            inner.tag_configure('SUCCESS', foreground=C_SUCCESS)
            inner.tag_configure('DEBUG', foreground=C_INFO)
            inner.tag_configure('PROCESS', foreground='#8E7BB8')
            inner.tag_configure('GUIDE', foreground=C_GUIDE_GLOW)
            inner.tag_configure('timestamp', foreground=C_TEXT_MUTED)
        except Exception:
            pass

    def attach(self, widget):
        """把同一份日志同时投到另一个文本框（主界面右下角的日志栏）。"""
        if widget is None or widget in self.widgets:
            return widget
        self._configure_tags(widget)
        self.widgets.append(widget)
        self._render(widget)
        return widget

    def log(self, message: str, level: str = 'INFO', verbose: bool = None):
        """verbose=None 时按层级判断；显式 True/False 可覆盖。"""
        if verbose is None:
            verbose = level in self.VERBOSE_LEVELS
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_line = f"[{timestamp}] [{level}] {message}\n"
        self.full_log.append((log_line, level, bool(verbose)))
        if threading.current_thread() is threading.main_thread():
            self._update_display()
        else:
            ui_call(self.root, self._update_display)

    def set_show_full(self, show_full: bool):
        self.show_full = show_full
        if threading.current_thread() is threading.main_thread():
            self._update_display()
        else:
            ui_call(self.root, self._update_display)

    def _visible_entries(self):
        """当前该显示哪些行：完整模式全部，否则只留最近一条非细节日志。"""
        if self.show_full:
            return [(line, level) for line, level, _verbose in self.full_log]
        for log_line, level, verbose in reversed(self.full_log):
            if not verbose:
                return [(log_line, level)]
        return []

    def _update_display(self):
        for widget in list(self.widgets):
            self._render(widget)

    def _render(self, widget):
        try:
            widget.delete("1.0", END)
            for log_line, level in self._visible_entries():
                self._insert_log(widget, log_line, level)
            widget.see(END)
        except Exception:
            pass

    def _insert_log(self, widget, log_line: str, level: str):
        try:
            inner = widget._textbox
            end = log_line.find(']') + 1
            inner.insert(END, log_line[:end], 'timestamp')
            inner.insert(END, log_line[end:], level)
        except Exception:
            try:
                widget.insert(END, log_line)
            except Exception:
                pass

    def clear(self):
        self.full_log.clear()
        for widget in list(self.widgets):
            try:
                widget.delete("1.0", END)
            except Exception:
                pass


# ==================== 新手引导系统 ====================
class GuideManager:
    def __init__(self, root):
        self.root = root
        self._steps: dict = {}
        self._current: str | None = None
        self._originals: dict = {}

    def register(self, step_name: str, widgets: list = None,
                 desc: str = "", colors: tuple = None):
        """只登记步骤与说明文案。

        需求：去掉控件上的绿色描边高亮（Step 1 卡片那圈绿边），
        所以 widgets 不再参与显示 —— 引导只通过日志文案提示当前该做哪步。
        """
        self._steps[step_name] = {
            'widgets': [],
            'desc': desc,
            'colors': colors or (C_GUIDE_GLOW, BORDER_W_FOCUS),
        }

    def clear_registered(self):
        self._steps.clear()

    def show(self, step_name: str):
        self._restore_all()
        if step_name not in self._steps:
            self._current = None
            return
        self._current = step_name
        info = self._steps[step_name]
        border_color, border_width = info['colors']
        for w in info['widgets']:
            self._highlight(w, border_color, border_width)

    def hide(self):
        self._restore_all()
        self._current = None

    def _highlight(self, widget, color, width):
        try:
            wid = id(widget)
            if wid not in self._originals:
                try:
                    orig_bc = widget.cget('border_color')
                except Exception:
                    orig_bc = C_BORDER
                try:
                    orig_bw = widget.cget('border_width')
                except Exception:
                    orig_bw = BORDER_W
                self._originals[wid] = {
                    'widget': widget,
                    'border_color': orig_bc,
                    'border_width': orig_bw,
                }
            widget.configure(border_width=width)
            self._pulse(widget, color)
        except Exception:
            pass

    def _pulse(self, widget, color):
        """描边呼吸：在强调色与提亮色之间来回缓动（三角波），直到 hide()。"""
        light = lerp_color(color, "#FFFFFF", 0.6)

        def frame(e, raw):
            triangle = raw if raw <= 0.5 else (1.0 - raw)
            try:
                widget.configure(
                    border_color=lerp_color(color, light, triangle))
            except Exception:
                pass

        frame(0.0, 0.0)
        if ANIMATIONS_ENABLED:
            tween(widget, "guide", 1100, frame,
                  on_done=lambda: self._pulse(widget, color),
                  easing=ease_linear)

    def _restore_all(self):
        for wid, saved in list(self._originals.items()):
            try:
                w = saved['widget']
                cancel_tween(w, "guide")
                w.configure(border_color=saved['border_color'],
                            border_width=saved['border_width'])
            except Exception:
                pass
        self._originals.clear()


# ==================== 最近打开 ====================
class RecentPacksManager:
    def __init__(self, path: Path):
        self.path = path
        self.recent = []
        self.load()

    def load(self):
        if self.path.exists():
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.recent = data.get('recent_packs', [])
            except Exception:
                self.recent = []

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            if self.path.exists():
                try:
                    with open(self.path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except Exception:
                    data = {}
            data['recent_packs'] = self.recent
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def add(self, pack_path: str, pack_name: str):
        self.recent = [r for r in self.recent if r.get('path') != pack_path]
        self.recent.insert(0, {
            'path': pack_path, 'name': pack_name,
            'last_opened': datetime.now().isoformat()})
        self.recent = self.recent[:10]
        self.save()

    def get_all(self) -> list[dict]:
        return self.recent


# ==================== TACZ 文件监控 ====================
class _TaczEventHandler(FileSystemEventHandler):
    IGNORE_NAMES = {'tacz-pre.toml', '.export-state.json', 'blacklist.txt'}
    IGNORE_DIRS = {'tacz_default_gun'}

    def __init__(self, trigger):
        super().__init__()
        self.trigger = trigger

    def _interesting(self, path_str: str) -> bool:
        if not path_str:
            return False
        name = os.path.basename(path_str)
        if name in self.IGNORE_NAMES:
            return False
        if name.startswith('.') or name.endswith('.tmp') or name.endswith('~'):
            return False
        try:
            parts = Path(path_str).parts
            for d in self.IGNORE_DIRS:
                if d in parts:
                    return False
        except Exception:
            pass
        return True

    def on_any_event(self, event):
        try:
            if event.event_type == 'opened':
                return
            if not self._interesting(event.src_path):
                return
            dest = getattr(event, 'dest_path', None)
            if dest and not self._interesting(dest):
                return
            self.trigger()
        except Exception:
            pass


class TaczWatcher:
    DEBOUNCE_SEC = 0.8

    def __init__(self, tacz_path: Path, on_change_callback, log_manager=None):
        self.tacz_path = tacz_path
        self.on_change_callback = on_change_callback
        self.log = log_manager
        self.observer = None
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active

    def start(self) -> bool:
        if not HAS_WATCHDOG or self._active:
            return False
        if not self.tacz_path or not self.tacz_path.exists():
            return False
        try:
            handler = _TaczEventHandler(self._schedule)
            self.observer = Observer()
            self.observer.daemon = True
            self.observer.schedule(handler, str(self.tacz_path), recursive=True)
            self.observer.start()
            self._active = True
            if self.log:
                self.log.log(f"已启动 TACZ 监控: {self.tacz_path}", 'INFO',
                                  verbose=True)
            return True
        except Exception as e:
            if self.log:
                self.log.log(f"启动 TACZ 监控失败: {e}", 'WARNING')
            self.observer = None
            self._active = False
            return False

    def stop(self):
        with self._lock:
            if self._timer is not None:
                try:
                    self._timer.cancel()
                except Exception:
                    pass
                self._timer = None
        if self.observer is not None:
            try:
                self.observer.stop()
                self.observer.join(timeout=2)
            except Exception:
                pass
            self.observer = None
        if self._active and self.log:
            self.log.log("已停止 TACZ 监控", 'INFO', verbose=True)
        self._active = False

    def _schedule(self):
        with self._lock:
            if self._timer is not None:
                try:
                    self._timer.cancel()
                except Exception:
                    pass
            self._timer = threading.Timer(self.DEBOUNCE_SEC, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self):
        with self._lock:
            self._timer = None
        try:
            self.on_change_callback()
        except Exception as e:
            if self.log:
                self.log.log(f"文件变更回调出错: {e}", 'WARNING')


# ==================== 预设数据管理 ====================
PRESET_MARK_APPLIED = "✓ "


def preset_name_of(row_text: str) -> str:
    """列表行文本 → 预设名（「已应用」前缀不算名字）。"""
    if row_text.startswith(PRESET_MARK_APPLIED):
        return row_text[len(PRESET_MARK_APPLIED):]
    return row_text


class PresetManager:
    PROTECTED_FILES = ['tacz-pre.toml', '.export-state.json', 'blacklist.txt']
    PROTECTED_DIRS = ['tacz_default_gun']
    CACHE_FILE = '.cache.json'
    BATCH_SIZE = 5
    BATCH_DELAY = 0.005

    def __init__(self, db_path: Path, log_manager, tacz_path=None, pack_name=""):
        self.database_path = db_path
        self.tacz_path = tacz_path
        self.pack_name = pack_name
        self.log = log_manager
        self.current_preset: str | None = None
        self.presets: dict[str, dict] = {}
        self.cache_path = db_path / self.CACHE_FILE if db_path else None

    def load_from_cache(self) -> bool:
        if not self.cache_path or not self.cache_path.exists():
            return False
        try:
            with open(self.cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            db_mtime = self.database_path.stat().st_mtime if self.database_path.exists() else 0
            if cache_data.get('db_mtime', 0) != db_mtime:
                return False
            self.presets = cache_data.get('presets', {})
            self.current_preset = cache_data.get('current_preset')
            self.log.log(f"从缓存加载预设成功，共 {len(self.presets)} 个预设",
                          'SUCCESS', verbose=True)
            return True
        except Exception as e:
            self.log.log(f"加载缓存失败: {e}", 'WARNING')
            return False

    def save_cache(self):
        if not self.cache_path:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'db_mtime': self.database_path.stat().st_mtime if self.database_path.exists() else 0,
                    'presets': self.presets,
                    'current_preset': self.current_preset
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log.log(f"保存缓存失败: {e}", 'WARNING')

    def load_all_presets(self, use_cache: bool = True):
        if use_cache and self.load_from_cache():
            return
        self.presets = {}
        if not self.database_path.exists():
            return
        for preset_dir in self.database_path.iterdir():
            if preset_dir.is_dir() and not preset_dir.name.startswith('.'):
                self._load_preset(preset_dir)
        self.log.log(f"预设加载完成，共 {len(self.presets)} 个预设", 'INFO',
                          verbose=True)
        self.save_cache()

    def _load_preset(self, preset_path: Path):
        try:
            index_file = preset_path / 'index.json'
            if not index_file.exists():
                self.presets[preset_path.name] = {
                    'path': str(preset_path), 'name': preset_path.name,
                    'version': 'v1.0.0', 'gunpacks': {}, 'applied': False,
                    'incremental_count': 0}
                return
            with open(index_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            raw = data.get('gunpacks', {})
            standard = {}
            for name, value in raw.items():
                if isinstance(value, dict):
                    standard[name] = value
                elif isinstance(value, (list, tuple)):
                    standard[name] = {'type': 'zip', 'size': 0,
                                      'file_count': 1,
                                      'legacy_hash': str(value[0]) if value else ''}
                else:
                    standard[name] = {'type': 'zip', 'size': 0, 'file_count': 1}
            if standard != raw:
                data['gunpacks'] = standard
                with open(index_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                self.log.log(f"预设 '{preset_path.name}' 已自动适配为新格式", 'INFO',
                          verbose=True)

            version = (data.get('version')
                       or data.get('description')
                       or 'v1.0.0')
            self.presets[preset_path.name] = {
                'path': str(preset_path),
                'name': data.get('name', preset_path.name),
                'version': version,
                'gunpacks': standard,
                'applied': data.get('applied', False),
                'incremental_count': data.get('incremental_count', 0)}
            if self.presets[preset_path.name]['applied']:
                self.current_preset = preset_path.name
        except Exception as e:
            self.log.log(f"加载预设 {preset_path.name} 失败: {e}", 'ERROR')

    def create_preset(self, name: str, version: str = 'v1.0.0') -> bool:
        if not name or name in self.presets:
            return False
        preset_path = self.database_path / name
        try:
            preset_path.mkdir(parents=True, exist_ok=True)
            index_data = {'name': name, 'version': version, 'gunpacks': {},
                          'applied': False, 'incremental_count': 0}
            with open(preset_path / 'index.json', 'w', encoding='utf-8') as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)
            with open(preset_path / 'version.txt', 'w', encoding='utf-8') as f:
                f.write(version)
            self.presets[name] = {
                'path': str(preset_path), 'name': name, 'version': version,
                'gunpacks': {}, 'applied': False, 'incremental_count': 0}
            self.save_cache()
            self.log.log(f"预设 '{name}' 创建成功", 'SUCCESS')
            return True
        except Exception as e:
            self.log.log(f"创建预设失败: {e}", 'ERROR')
            return False

    def update_preset_version(self, preset_name: str, version: str) -> bool:
        if preset_name not in self.presets:
            return False
        try:
            preset_info = self.presets[preset_name]
            preset_info['version'] = version
            preset_path = Path(preset_info['path'])
            index_file = preset_path / 'index.json'
            if index_file.exists():
                with open(index_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                data['version'] = version
                with open(index_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            with open(preset_path / 'version.txt', 'w', encoding='utf-8') as f:
                f.write(version)
            self.save_cache()
            return True
        except Exception as e:
            self.log.log(f"更新版本号失败: {e}", 'ERROR')
            return False

    def rename_preset(self, old_name: str, new_name: str) -> bool:
        if old_name not in self.presets or new_name in self.presets:
            return False
        if not new_name or not new_name.strip():
            return False
        for char in r'\/:*?"<>|':
            if char in new_name:
                self.log.log(f"预设名称不能包含非法字符: {char}", 'ERROR')
                return False
        try:
            preset_info = self.presets[old_name]
            old_path = Path(preset_info['path'])
            new_path = self.database_path / new_name
            was_applied = preset_info.get('applied', False)
            if was_applied:
                preset_info['applied'] = False
                self.current_preset = None
            old_path.rename(new_path)
            index_file = new_path / 'index.json'
            if index_file.exists():
                with open(index_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                data['name'] = new_name
                with open(index_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            preset_info['path'] = str(new_path)
            preset_info['name'] = new_name
            self.presets[new_name] = preset_info
            del self.presets[old_name]
            if was_applied:
                preset_info['applied'] = True
                self.current_preset = new_name
                self._update_preset_status(new_path, True)
            self.save_cache()
            return True
        except Exception as e:
            self.log.log(f"重命名预设失败: {e}", 'ERROR')
            return False

    def delete_preset(self, name: str) -> bool:
        if name not in self.presets:
            return False
        if self.presets[name].get('applied', False):
            self.log.log(f"预设 '{name}' 已应用，请先取消应用再删除", 'WARNING')
            return False
        try:
            preset_info = self.presets[name]
            preset_path = Path(preset_info['path'])
            if preset_path.exists():
                shutil.rmtree(preset_path)
            del self.presets[name]
            if self.current_preset == name:
                self.current_preset = None
            self.save_cache()
            return True
        except Exception as e:
            self.log.log(f"删除预设失败: {e}", 'ERROR')
            return False

    def _get_gunpacks_from_folder(self, folder_path: Path) -> dict:
        result = {}
        if not folder_path.exists():
            return result
        protected_all = self.PROTECTED_FILES + self.PROTECTED_DIRS
        for item in folder_path.iterdir():
            if item.name in ['description.txt', 'index.json', 'version.txt']:
                continue
            if item.name in protected_all:
                continue
            fp = get_item_fingerprint(item)
            if fp:
                result[item.name] = fp
        return result

    def detect_changes(self, preset_name: str) -> dict:
        preset_info = self.presets.get(preset_name)
        if not preset_info or not self.tacz_path:
            return {'added': [], 'removed': [], 'modified': []}
        current = self._get_gunpacks_from_folder(self.tacz_path)
        indexed = preset_info.get('gunpacks', {})
        added, removed, modified = [], [], []
        for name, curr_fp in current.items():
            if name not in indexed:
                added.append(name)
            elif not fingerprints_match(curr_fp, indexed[name]):
                modified.append(name)
        for name in indexed:
            if name not in current:
                removed.append(name)
        return {'added': added, 'removed': removed, 'modified': modified}

    def has_changes(self, preset_name: str) -> bool:
        c = self.detect_changes(preset_name)
        return bool(c['added'] or c['removed'] or c['modified'])

    def _move_items(self, src_dir: Path, dst_dir: Path, exclude=None,
                    progress_callback=None) -> int:
        if not src_dir.exists():
            return 0
        exclude = exclude or []
        items = [i for i in src_dir.iterdir() if i.name not in exclude]
        total = len(items)
        moved = 0
        for i, item in enumerate(items):
            try:
                dest = dst_dir / item.name
                if dest.exists():
                    if dest.is_dir():
                        shutil.rmtree(dest)
                    else:
                        dest.unlink()
                shutil.move(str(item), str(dest))
                moved += 1
                if progress_callback:
                    progress_callback(i + 1, total, f"移动 {item.name}")
                if (i + 1) % self.BATCH_SIZE == 0:
                    time.sleep(self.BATCH_DELAY)
            except Exception as e:
                self.log.log(f"移动 {item.name} 失败: {e}", 'WARNING')
        return moved

    def _clear_dir(self, dir_path: Path, exclude=None):
        if not dir_path.exists():
            return
        exclude = exclude or []
        for item in dir_path.iterdir():
            if item.name in exclude:
                continue
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except Exception as e:
                self.log.log(f"删除 {item.name} 失败: {e}", 'ERROR')

    def _safe_remove(self, path: Path) -> bool:
        if move_to_recycle_bin(path):
            return True
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            return True
        except Exception as e:
            self.log.log(f"删除 {path.name} 失败: {e}", 'ERROR')
            return False

    def apply_preset(self, preset_name: str, progress_callback=None) -> bool:
        if preset_name not in self.presets:
            return False
        if not self.tacz_path or not self.tacz_path.exists():
            return False
        current_applied = None
        for name, info in self.presets.items():
            if info.get('applied', False):
                current_applied = name
                break
        if current_applied == preset_name:
            return True
        target_preset = self.presets[preset_name]
        target_path = Path(target_preset['path'])
        protected_all = self.PROTECTED_FILES + self.PROTECTED_DIRS
        try:
            self.log.log(f"开始切换预设: {current_applied or 'None'} -> {preset_name}", 'PROCESS')
            if current_applied and current_applied in self.presets:
                cur_info = self.presets[current_applied]
                cur_path = Path(cur_info['path'])
                moved = self._move_items(self.tacz_path, cur_path, protected_all, progress_callback)
                cur_info['applied'] = False
                self._update_preset_status(cur_path, False)
                self.log.log(f"已回收 {moved} 个枪包到 '{current_applied}'", 'INFO',
                          verbose=True)
            self._clear_dir(self.tacz_path, protected_all)
            moved = self._move_items(target_path, self.tacz_path,
                                     ['description.txt', 'index.json', 'version.txt'],
                                     progress_callback)
            target_preset['applied'] = True
            self._update_preset_status(target_path, True)
            self.current_preset = preset_name
            self.save_cache()
            self.log.log(f"成功应用预设 '{preset_name}' (移动了 {moved} 个枪包)", 'SUCCESS')
            return True
        except Exception as e:
            self.log.log(f"应用预设失败: {e}", 'ERROR')
            return False

    def _update_preset_status(self, preset_path: Path, applied: bool):
        try:
            index_file = preset_path / 'index.json'
            if not index_file.exists():
                return
            with open(index_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data['applied'] = applied
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            for name, info in self.presets.items():
                if Path(info['path']) == preset_path:
                    info['applied'] = applied
                    break
            self.save_cache()
        except Exception as e:
            self.log.log(f"更新预设状态失败: {e}", 'ERROR')

    def update_preset_index(self, preset_name: str, from_tacz: bool = False) -> bool:
        if preset_name not in self.presets:
            return False
        preset_info = self.presets[preset_name]
        preset_path = Path(preset_info['path'])
        try:
            if from_tacz and self.tacz_path:
                gunpacks = self._get_gunpacks_from_folder(self.tacz_path)
                self.log.log(f"从Tacz读取到 {len(gunpacks)} 个枪包", 'INFO',
                          verbose=True)
            else:
                gunpacks = self._get_gunpacks_from_folder(preset_path)
                self.log.log(f"从预设 '{preset_name}' 读取到 {len(gunpacks)} 个枪包",
                          'INFO', verbose=True)
            index_data = {
                'name': preset_info['name'],
                'version': preset_info.get('version', 'v1.0.0'),
                'gunpacks': gunpacks,
                'applied': preset_info.get('applied', False),
                'incremental_count': preset_info.get('incremental_count', 0)}
            with open(preset_path / 'index.json', 'w', encoding='utf-8') as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)
            preset_info['gunpacks'] = gunpacks
            self.save_cache()
            self.log.log(f"预设 '{preset_name}' 校验数据已更新", 'SUCCESS')
            return True
        except Exception as e:
            self.log.log(f"更新预设索引失败: {e}", 'ERROR')
            return False

    def export_preset(self, preset_name: str, export_path: Path, progress_callback=None) -> bool:
        if preset_name not in self.presets:
            return False
        if preset_name == "default":
            self.log.log("不允许导出名为 'default' 的预设", 'ERROR')
            return False

        preset_info = self.presets[preset_name]
        preset_path = Path(preset_info['path'])
        was_applied = preset_info.get('applied', False)

        if was_applied and self.tacz_path and self.tacz_path.exists():
            source_path = self.tacz_path
            self.log.log(f"预设 '{preset_name}' 已应用，从 TACZ 读取枪包内容",
                          'INFO', verbose=True)
        else:
            source_path = preset_path
            self.log.log(f"从预设文件夹读取导出内容: {preset_name}", 'INFO',
                          verbose=True)

        try:
            if was_applied and self.tacz_path and self.tacz_path.exists():
                current_gunpacks = self._get_gunpacks_from_folder(self.tacz_path)
            else:
                current_gunpacks = self._get_gunpacks_from_folder(preset_path)

            index_data = {
                'name': preset_info['name'],
                'version': preset_info.get('version', 'v1.0.0'),
                'gunpacks': current_gunpacks,
                'applied': was_applied,
                'incremental_count': preset_info.get('incremental_count', 0)
            }
            with open(preset_path / 'index.json', 'w', encoding='utf-8') as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)

            protected_all = self.PROTECTED_FILES + self.PROTECTED_DIRS
            items = []
            added_names = set()

            if source_path == preset_path:
                for item in source_path.rglob('*'):
                    if item == source_path:
                        continue
                    rel = item.relative_to(source_path)
                    if rel.parts and rel.parts[0] in protected_all:
                        continue
                    items.append(item)
                    added_names.add(str(rel))
            else:
                for item in source_path.rglob('*'):
                    if item == source_path:
                        continue
                    rel = item.relative_to(source_path)
                    if rel.parts and rel.parts[0] in protected_all:
                        continue
                    items.append(item)
                    added_names.add(str(rel))

                for meta_name in ['index.json', 'description.txt', 'version.txt']:
                    meta_path = preset_path / meta_name
                    if meta_path.exists() and meta_name not in added_names:
                        items.append(meta_path)
                        added_names.add(meta_name)

            total = len(items)
            if total == 0:
                with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_STORED):
                    pass
                self.log.log(f"预设 '{preset_name}' 导出成功（空包）", 'SUCCESS')
                if progress_callback:
                    progress_callback(0, 0, "完成")
                return True

            self.log.log(f"正在打包 {total} 个项目...", 'PROCESS')
            with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_STORED) as zipf:
                for idx, item in enumerate(items):
                    try:
                        if source_path == preset_path:
                            arcname = item.relative_to(preset_path)
                        else:
                            try:
                                arcname = item.relative_to(source_path)
                            except ValueError:
                                arcname = item.relative_to(preset_path)

                        if item.is_file():
                            zipf.write(item, arcname)
                        else:
                            zipf.write(item, str(arcname) + '/')
                    except Exception as e:
                        self.log.log(f"打包 {item.name} 失败: {e}", 'WARNING')
                    if progress_callback and idx % 2 == 0:
                        progress_callback(idx + 1, total, f"打包 {item.name}")
                    if idx % 20 == 0:
                        time.sleep(0.001)

            self.log.log(f"预设 '{preset_name}' 导出成功: {export_path.name}", 'SUCCESS')
            if progress_callback:
                progress_callback(total, total, "完成")
            return True

        except Exception as e:
            self.log.log(f"导出预设失败: {e}", 'ERROR')
            return False

    def export_incremental(self, preset_name: str, export_path: Path, progress_callback=None) -> bool:
        if preset_name not in self.presets or not self.tacz_path:
            return False
        if preset_name == "default":
            self.log.log("不允许导出名为 'default' 的预设", 'ERROR')
            return False

        preset_info = self.presets[preset_name]
        if not preset_info.get('applied', False):
            self.log.log("只能对已应用的预设导出增量更新", 'ERROR')
            return False

        changes = self.detect_changes(preset_name)
        total_changes = len(changes['added']) + len(changes['removed']) + len(changes['modified'])
        if total_changes == 0:
            self.log.log("未检测到任何变更", 'INFO')
            return False
        self.log.log(
            f"检测到变更: 新增 {len(changes['added'])} / "
            f"移除 {len(changes['removed'])} / "
            f"修改 {len(changes['modified'])}",
            'INFO')

        base_gunpacks = preset_info.get('gunpacks', {})
        new_gunpacks = self._get_gunpacks_from_folder(self.tacz_path)

        files_to_pack = []
        for name in changes['added'] + changes['modified']:
            item = self.tacz_path / name
            if item.exists():
                files_to_pack.append(item)

        increment = preset_info.get('incremental_count', 0) + 1

        metadata = {
            'format': 'pulses_swap_incremental',
            'format_version': 2,
            'preset_name': preset_name,
            'pack_name': self.pack_name,
            'version': preset_info.get('version', 'v1.0.0'),
            'increment': increment,
            'changes': changes,
            'base_gunpacks_index': base_gunpacks,
            'new_gunpacks_index': new_gunpacks,
            'timestamp': datetime.now().isoformat()
        }

        try:
            total = len(files_to_pack) + 1
            processed = 0
            with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_STORED) as zipf:
                zipf.writestr('_increment.json',
                              json.dumps(metadata, indent=2, ensure_ascii=False))
                processed += 1
                if progress_callback:
                    progress_callback(processed, total, "写入元数据")
                for item in files_to_pack:
                    try:
                        if item.is_file():
                            zipf.write(item, item.name)
                        else:
                            for sub in item.rglob('*'):
                                if sub.is_file():
                                    zipf.write(sub, str(sub.relative_to(self.tacz_path)))
                    except Exception as e:
                        self.log.log(f"打包 {item.name} 失败: {e}", 'WARNING')
                    processed += 1
                    if progress_callback:
                        progress_callback(processed, total, f"打包 {item.name}")
                    time.sleep(0.001)

            self.log.log("导出完成，正在同步校验数据...", 'PROCESS')
            preset_info['gunpacks'] = new_gunpacks
            preset_info['incremental_count'] = increment
            preset_path = Path(preset_info['path'])
            index_data = {
                'name': preset_info['name'],
                'version': preset_info.get('version', 'v1.0.0'),
                'gunpacks': new_gunpacks,
                'applied': True,
                'incremental_count': increment
            }
            with open(preset_path / 'index.json', 'w', encoding='utf-8') as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)
            self.save_cache()

            self.log.log(f"增量更新包导出成功: {export_path.name} (迭代 {increment})", 'SUCCESS')
            self.log.log(f"校验数据已同步为最新 ({len(new_gunpacks)} 个枪包)",
                          'SUCCESS', verbose=True)
            if progress_callback:
                progress_callback(total, total, "完成")
            return True
        except Exception as e:
            self.log.log(f"导出增量包失败: {e}", 'ERROR')
            return False

    def import_preset(self, import_path: Path, progress_callback=None) -> bool:
        try:
            temp_dir = Path(tempfile.mkdtemp())
            with zipfile.ZipFile(import_path, 'r') as zipf:
                members = zipf.infolist()
                total = len(members)
                for idx, member in enumerate(members):
                    if member.is_dir():
                        continue
                    try:
                        zipf.extract(member, temp_dir)
                        if progress_callback and idx % 2 == 0:
                            progress_callback(idx + 1, total, f"解压 {member.filename}")
                    except Exception as e:
                        self.log.log(f"解压失败 {member.filename}: {e}", 'WARNING')
                    if idx % 20 == 0:
                        time.sleep(0.001)
            index_file = temp_dir / 'index.json'
            if not index_file.exists():
                self.log.log("导入失败: 缺少index.json", 'ERROR')
                shutil.rmtree(temp_dir)
                return False
            with open(index_file, 'r', encoding='utf-8') as f:
                index_data = json.load(f)
            preset_name = index_data.get('name', import_path.stem)
            raw = index_data.get('gunpacks', {})
            standard = {}
            for name, value in raw.items():
                if isinstance(value, dict):
                    standard[name] = value
                elif isinstance(value, list):
                    standard[name] = {'type': 'zip', 'size': 0, 'file_count': 1,
                                      'hash': str(value[0]) if value else ''}
                else:
                    standard[name] = {'type': 'zip', 'size': 0, 'file_count': 1}
            index_data['gunpacks'] = standard
            index_data['version'] = index_data.get('version',
                                                    index_data.get('description', 'v1.0.0'))
            index_data['incremental_count'] = index_data.get('incremental_count', 0)
            if preset_name in self.presets:
                if not ask_yes_no("确认覆盖", f"预设 '{preset_name}' 已存在，是否覆盖？"):
                    shutil.rmtree(temp_dir)
                    return False
                old_path = Path(self.presets[preset_name]['path'])
                if old_path.exists():
                    shutil.rmtree(old_path)
                del self.presets[preset_name]
            preset_path = self.database_path / preset_name
            if preset_path.exists():
                shutil.rmtree(preset_path)
            shutil.move(str(temp_dir), str(preset_path))
            with open(preset_path / 'index.json', 'w', encoding='utf-8') as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)
            self._load_preset(preset_path)
            gunpacks = self._get_gunpacks_from_folder(preset_path)
            self.presets[preset_name]['gunpacks'] = gunpacks
            index_data['gunpacks'] = gunpacks
            with open(preset_path / 'index.json', 'w', encoding='utf-8') as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)
            self.save_cache()
            if progress_callback:
                progress_callback(100, 100, "完成")
            self.log.log(f"预设 '{preset_name}' 导入成功", 'SUCCESS')
            return True
        except Exception as e:
            self.log.log(f"导入预设失败: {e}", 'ERROR')
            return False

    def import_incremental(self, import_path: Path, progress_callback=None) -> bool:
        try:
            temp_dir = Path(tempfile.mkdtemp())
            with zipfile.ZipFile(import_path, 'r') as zipf:
                for member in zipf.infolist():
                    if member.is_dir():
                        continue
                    try:
                        zipf.extract(member, temp_dir)
                    except Exception as e:
                        self.log.log(f"解压失败 {member.filename}: {e}", 'WARNING')
            meta_file = temp_dir / '_increment.json'
            if not meta_file.exists():
                self.log.log("不是有效的增量更新包（缺少元数据）", 'ERROR')
                shutil.rmtree(temp_dir)
                return False
            with open(meta_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            if metadata.get('format') != 'pulses_swap_incremental':
                self.log.log("不是有效的增量更新包（格式不匹配）", 'ERROR')
                shutil.rmtree(temp_dir)
                return False

            preset_name = metadata.get('preset_name')
            version = metadata.get('version', '')
            increment = metadata.get('increment', 0)
            changes = metadata.get('changes', {})
            new_gunpacks = metadata.get('new_gunpacks_index', {})
            base_gunpacks = metadata.get('base_gunpacks_index')

            if preset_name not in self.presets:
                self.log.log(f"目标预设 '{preset_name}' 不存在", 'ERROR')
                shutil.rmtree(temp_dir)
                return False
            preset_info = self.presets[preset_name]
            if preset_info.get('version', '') != version:
                self.log.log(f"版本不匹配: 本地 '{preset_info.get('version','')}' vs 更新 '{version}'", 'ERROR')
                shutil.rmtree(temp_dir)
                show_error("版本不匹配",
                    f"增量更新包版本与本地不一致：\n\n"
                    f"本地版本: {preset_info.get('version','')}\n"
                    f"更新版本: {version}\n\n"
                    f"请确认您使用的是对应的增量包。")
                return False
            if not preset_info.get('applied', False):
                self.log.log(f"预设 '{preset_name}' 未应用，无法导入增量更新", 'ERROR')
                shutil.rmtree(temp_dir)
                show_error("无法应用",
                    f"预设 '{preset_name}' 当前未应用。\n\n"
                    f"请先切换到该预设后再导入增量更新。")
                return False

            if base_gunpacks:
                self.log.log("正在校验本地枪包与增量包要求的原始状态...", 'PROCESS')
                local_gunpacks = self._get_gunpacks_from_folder(self.tacz_path)
                missing = []
                modified = []
                for name, base_fp in base_gunpacks.items():
                    if name not in local_gunpacks:
                        missing.append(name)
                    elif not fingerprints_match(local_gunpacks[name], base_fp):
                        modified.append(name)

                if missing or modified:
                    self.log.log("增量更新校验失败：本地枪包与增量包要求的原始状态不匹配", 'ERROR')
                    if missing:
                        self.log.log(f"  缺失 {len(missing)} 个枪包（需向管理员请求）:", 'ERROR')
                        for n in missing[:10]:
                            self.log.log(f"    × {n}", 'ERROR')
                        if len(missing) > 10:
                            self.log.log(f"    ... 还有 {len(missing)-10} 个", 'ERROR')
                    if modified:
                        self.log.log(f"  内容已被修改 {len(modified)} 个枪包:", 'ERROR')
                        for n in modified[:10]:
                            self.log.log(f"    ~ {n}", 'ERROR')
                        if len(modified) > 10:
                            self.log.log(f"    ... 还有 {len(modified)-10} 个", 'ERROR')

                    lines = ["增量更新无法应用：本地枪包状态与增量包要求的原始状态不匹配。\n"]
                    if missing:
                        lines.append(f"缺失的枪包（{len(missing)} 个，需向管理员请求）：")
                        for n in missing[:10]:
                            lines.append(f"  × {n}")
                        if len(missing) > 10:
                            lines.append(f"  ... 还有 {len(missing)-10} 个")
                        lines.append("")
                    if modified:
                        lines.append(f"内容已被修改的枪包（{len(modified)} 个）：")
                        for n in modified[:10]:
                            lines.append(f"  ~ {n}")
                        if len(modified) > 10:
                            lines.append(f"  ... 还有 {len(modified)-10} 个")
                        lines.append("")
                    lines.append("请先恢复这些枪包到原始状态后再重试。")

                    shutil.rmtree(temp_dir)
                    show_error("增量更新校验失败", "\n".join(lines))
                    return False
                else:
                    self.log.log("本地枪包与原始状态匹配", 'SUCCESS', verbose=True)
            else:
                self.log.log("提示：此增量包未包含原始校验数据，跳过兼容性校验", 'WARNING')

            added = changes.get('added', [])
            removed = changes.get('removed', [])
            modified = changes.get('modified', [])
            self.log.log(f"增量更新: 新增 {len(added)} / 移除 {len(removed)} / "
                          f"修改 {len(modified)}", 'INFO', verbose=True)

            for name in removed:
                target = self.tacz_path / name
                if target.exists():
                    if self._safe_remove(target):
                        self.log.log(f"已移除 {name}（可在回收站找回）", 'DEBUG')

            for name in added + modified:
                src = temp_dir / name
                if not src.exists():
                    continue
                dst = self.tacz_path / name
                if dst.exists():
                    if dst.is_dir():
                        shutil.rmtree(dst)
                    else:
                        dst.unlink()
                shutil.move(str(src), str(dst))

            if new_gunpacks:
                preset_info['gunpacks'] = new_gunpacks
            else:
                preset_info['gunpacks'] = self._get_gunpacks_from_folder(self.tacz_path)
            preset_info['incremental_count'] = increment
            preset_path = Path(preset_info['path'])
            index_data = {
                'name': preset_info['name'],
                'version': preset_info.get('version', 'v1.0.0'),
                'gunpacks': preset_info['gunpacks'], 'applied': True,
                'incremental_count': increment}
            with open(preset_path / 'index.json', 'w', encoding='utf-8') as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)
            self.save_cache()
            shutil.rmtree(temp_dir, ignore_errors=True)
            self.log.log(f"增量更新导入成功 (迭代 {increment})", 'SUCCESS')
            return True
        except Exception as e:
            self.log.log(f"导入增量包失败: {e}", 'ERROR')
            return False

    def get_current_gunpacks_for_preset(self, preset_name: str, use_cache: bool = True) -> dict:
        if preset_name not in self.presets:
            return {}
        preset_info = self.presets[preset_name]
        if preset_info.get('applied', False):
            if self.tacz_path and self.tacz_path.exists():
                return self._get_gunpacks_from_folder(self.tacz_path)
            return {}
        if use_cache and preset_info.get('gunpacks'):
            return preset_info['gunpacks']
        return self._get_gunpacks_from_folder(Path(preset_info['path']))


# ==================== 设置对话框 ====================
class SettingsPage:
    """
    设置页面（侧边栏「设置」页）：
    · 选项卡改成自绘的 CanvasSegmented，选中滑块带曲线滑动动画；
    · 选项卡内容用 SlideStack 做同款推入/推出切换；
    · 所有选项改完立即自动保存（写数据库目录下的 .settings.json），
      底部按钮条只保留「恢复默认」和自动保存状态回显。
    """

    def __init__(self, parent_frame, app, on_save_callback=None,
                 on_db_action=None):
        self.parent_frame = parent_frame
        self.app = app
        self.root = app.root
        self.settings: AppSettings = app.settings
        self.on_save_callback = on_save_callback
        self.on_db_action = on_db_action
        self._loading = False

        self.frame = ctk.CTkFrame(parent_frame, fg_color=C_WINDOW_BG)

        # ===== 选项卡头部：自绘分段控件（滑块带动画） =====
        head = ctk.CTkFrame(self.frame, fg_color=C_CARD_BG,
                             corner_radius=R_CARD, border_width=BORDER_W,
                             border_color=C_BORDER_SOFT, height=H_TAB_HEAD)
        head.pack(fill=X)
        head.pack_propagate(False)
        self.tab_bar = CanvasSegmented(
            head, [("general", "常规"), ("database", "数据库"), ("about", "关于")],
            command=self._on_tab_selected, orientation="horizontal",
            item_height=H_CONTROL, pad=8, gap=6, radius=R_CONTROL,
            bg_color=C_CARD_BG, pill_color=C_ACCENT, hover_color=C_ACCENT_SOFT,
            text_color=C_TEXT_SECONDARY, active_text_color=C_TEXT_INVERSE,
            font_size=FS_SMALL, bold_active=True, text_anchor="center",
            duration_ms=240)
        self.tab_bar.pack(fill=BOTH, expand=True, padx=PAD_XS, pady=PAD_XS)

        # ===== 选项卡内容：Canvas 承载，切换时整块推入/推出 =====
        self.stack = SlideStack(self.frame, bg_color=C_WINDOW_BG, duration_ms=260)
        self.stack.canvas.pack_configure(pady=(PAD_GAP, 0))

        self.storage_var = StringVar(value=self.settings.storage_mode)
        self.role_var = StringVar(value=self.settings.role)

        self.tabs = {}
        for key in ("general", "database", "about"):
            tab = ctk.CTkFrame(self.stack.canvas, fg_color=C_WINDOW_BG)
            self.tabs[key] = tab
            self.stack.add(key, tab)

        self._build_general(self.tabs["general"])
        self._build_database(self.tabs["database"])
        self._build_about(self.tabs["about"])

        # ===== 底部按钮条：自动保存状态 + 恢复默认 =====
        self.btn_bar = ctk.CTkFrame(self.frame, fg_color=C_CARD_BG,
                                     corner_radius=R_CARD, height=H_BTN_BAR,
                                     border_width=BORDER_W,
                                     border_color=C_BORDER_SOFT)
        self.btn_bar.pack(fill=X, pady=(PAD_GAP, 0))
        self.btn_bar.pack_propagate(False)
        make_button(self.btn_bar, "恢复默认", command=self._reset_defaults,
                     width=100).pack(side=RIGHT, padx=(PAD_TIGHT, PAD_DIALOG),
                                     pady=(H_BTN_BAR - H_CONTROL) // 2)
        self.saved_label = make_label(self.btn_bar, text=self._saved_hint(),
                                       fg=C_TEXT_MUTED, font_size=FS_TINY)
        self.saved_label.pack(side=LEFT, padx=PAD_DIALOG)

        self.reload()
        # 预热：每个选项卡都先布局一次，避免第一次切换时卡一帧
        try:
            for key in ("general", "database", "about"):
                self.stack.items[key]
                self.stack.canvas.itemconfigure(self.stack.items[key],
                                                 state="normal")
            self.stack.canvas.update_idletasks()
            for key in ("general", "database", "about"):
                self.stack.canvas.itemconfigure(self.stack.items[key],
                                                 state="hidden")
        except Exception:
            pass
        self.show_tab("general", animate=False)

    def _saved_hint(self):
        # 需求：设置项简洁 —— 常态只留四个字，改动时短暂回显「已自动保存」
        return "自动保存"

    # ==================== 选项卡切换 ====================
    def _on_tab_selected(self, key):
        self.show_tab(key)

    def show_tab(self, key, animate=True):
        if key not in self.tabs:
            return
        # 注意：不能用 tab_bar.current() 当「上一个」——点击进来时
        # CanvasSegmented 已经先把选中态切到新项了，那样永远算不出方向，
        # 表现就是「不管点哪边都往同一个方向滑」。这里自己记上一个选项卡。
        previous = getattr(self, "_active_tab", None) or self.stack.current
        direction = 1
        if previous is not None and previous != key:
            old_index = self.tab_bar.index_of(previous)
            new_index = self.tab_bar.index_of(key)
            # 点左面的选项卡内容往左走（新页从右侧进来），点右面的往右走
            if old_index >= 0 and new_index >= 0:
                direction = 1 if new_index > old_index else -1
        self._active_tab = key
        self.tab_bar.select(key, animate=animate, notify=False)
        self.stack.show(key, animate=animate, direction=direction, axis="x")

    # ==================== 选项卡：常规 ====================
    def _build_general(self, tab):
        # 需求：设置项要简洁 —— 不留解释性小字，选项本身就是完整说明；
        # 选中态用带动画的分段控件（滑块逐帧滑动），切换即可见。
        make_label(tab, text="存储模式", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, pady=(PAD_TIGHT, PAD_TIGHT))
        mode_card = ctk.CTkFrame(tab, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                  border_width=BORDER_W, border_color=C_BORDER_SOFT)
        mode_card.pack(fill=X, pady=(0, PAD_DIALOG))
        attach_hover_glow(mode_card)
        self.mode_seg = CanvasSegmented(
            mode_card, [("isolated", "隔离存储"), ("merged", "合并存储")],
            command=self._on_mode_selected, orientation="vertical",
            item_height=H_NAV, pad=6, gap=PAD_XS, radius=R_CONTROL,
            bg_color=C_CARD_BG, pill_color=C_ACCENT_SOFT,
            hover_color=C_ACCENT_SOFT, text_color=C_TEXT_MAIN,
            active_text_color=C_ACCENT, font_size=FS_BODY, bold_active=True,
            text_anchor="w", text_pad=16, duration_ms=240,
            height=px(2 * (H_NAV + PAD_XS) + 12))
        self.mode_seg.pack(fill=X, padx=PAD_TIGHT, pady=PAD_TIGHT)

        make_label(tab, text="动画", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, pady=(0, PAD_TIGHT))
        anim_card = ctk.CTkFrame(tab, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                  border_width=BORDER_W, border_color=C_BORDER_SOFT)
        anim_card.pack(fill=X, pady=(0, PAD_DIALOG))
        attach_hover_glow(anim_card)
        self.anim_seg = CanvasSegmented(
            anim_card, [("on", "流畅"), ("off", "关闭")],
            command=self._on_anim_selected, orientation="vertical",
            item_height=H_NAV, pad=6, gap=PAD_XS, radius=R_CONTROL,
            bg_color=C_CARD_BG, pill_color=C_ACCENT_SOFT,
            hover_color=C_ACCENT_SOFT, text_color=C_TEXT_MAIN,
            active_text_color=C_ACCENT, font_size=FS_BODY, bold_active=True,
            text_anchor="w", text_pad=16, duration_ms=240,
            height=px(2 * (H_NAV + PAD_XS) + 12))
        self.anim_seg.pack(fill=X, padx=PAD_TIGHT, pady=PAD_TIGHT)

        make_label(tab, text="用户身份", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, pady=(0, PAD_TIGHT))
        role_card = ctk.CTkFrame(tab, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                  border_width=BORDER_W, border_color=C_BORDER_SOFT)
        role_card.pack(fill=X, pady=(0, PAD_DIALOG))
        attach_hover_glow(role_card)
        self.role_seg = CanvasSegmented(
            role_card, [("player", "玩家"), ("developer", "开发者")],
            command=self._on_role_selected, orientation="vertical",
            item_height=H_NAV, pad=6, gap=PAD_XS, radius=R_CONTROL,
            bg_color=C_CARD_BG, pill_color=C_ACCENT_SOFT,
            hover_color=C_ACCENT_SOFT, text_color=C_TEXT_MAIN,
            active_text_color=C_ACCENT, font_size=FS_BODY, bold_active=True,
            text_anchor="w", text_pad=16, duration_ms=380,
            height=px(2 * (H_NAV + PAD_XS) + 12))
        self.role_seg.pack(fill=X, padx=PAD_TIGHT, pady=PAD_TIGHT)

    def _on_anim_selected(self, key):
        """动画开关：关掉后所有补间一帧到位（逻辑不变，只是不逐帧画）。"""
        enabled = (key != "off")
        apply_animations_setting(enabled)
        try:
            self.app.settings.animations = enabled
            self.app.settings.save()
        except Exception:
            pass
        self.app.toast("动画已关闭" if not enabled else "动画已开启",
                       kind="info")

    def _on_mode_selected(self, key):
        self.storage_var.set(key)
        self._on_auto_save()

    def _on_role_selected(self, key):
        self.role_var.set(key)
        self._on_auto_save()

    # ==================== 选项卡：数据库 ====================
    def _build_database(self, tab):
        make_label(tab, text="数据库位置", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, pady=(PAD_TIGHT, PAD_TIGHT))
        db_card = ctk.CTkFrame(tab, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                border_width=BORDER_W, border_color=C_BORDER_SOFT)
        db_card.pack(fill=X, pady=(0, PAD_DIALOG))
        self.db_path_label = make_label(db_card, text="", fg=C_TEXT_MAIN,
                                        font_size=FS_SMALL)
        self.db_path_label.configure(wraplength=620, justify=LEFT, anchor=W)
        self.db_path_label.pack(anchor=W, padx=PAD_CARD_X, pady=PAD_CARD_Y)

        make_label(tab, text="数据库管理", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, pady=(0, PAD_TIGHT))
        db_mgr_card = ctk.CTkFrame(tab, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                    border_width=BORDER_W, border_color=C_BORDER_SOFT)
        db_mgr_card.pack(fill=X, pady=(0, PAD_DIALOG))

        btn_row1 = ctk.CTkFrame(db_mgr_card, fg_color="transparent")
        btn_row1.pack(fill=X, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        make_button(btn_row1, "切换数据库", command=self.on_switch_db).pack(
            side=LEFT, padx=(0, PAD_TIGHT))
        make_button(btn_row1, "合并数据库", command=self.on_merge_db).pack(
            side=LEFT, padx=PAD_TIGHT)
        make_button(btn_row1, "适配旧版数据库", command=self.on_migrate_legacy).pack(
            side=LEFT, padx=PAD_TIGHT)

        btn_row2 = ctk.CTkFrame(db_mgr_card, fg_color="transparent")
        btn_row2.pack(fill=X, padx=PAD_CARD_X, pady=(0, PAD_TIGHT))
        make_button(btn_row2, "打开数据库文件夹", command=self.on_open_db).pack(
            side=LEFT, padx=(0, PAD_TIGHT))
        make_button(btn_row2, "强制更新校验数据",
                     command=self.app.force_update_validation).pack(
            side=LEFT, padx=PAD_TIGHT)
        make_label(db_mgr_card, text="", font_size=FS_TINY).pack(
                anchor=W, padx=PAD_CARD_X, pady=(0, PAD_TIGHT))

    # ==================== 选项卡：关于 ====================
    def _build_about(self, tab):
        make_label(tab, text=f"{PROJECT_NAME} v{VERSION}", fg=C_ACCENT,
                    font_size=FS_TITLE, bold=True).pack(
                        anchor=W, pady=(PAD_TIGHT, PAD_MICRO))
        make_label(tab, text=f"作者: {AUTHOR} · Minecraft Tacz 模组枪包快速切换工具",
                    fg=C_TEXT_SECONDARY, font_size=FS_SMALL).pack(
                        anchor=W, pady=(0, PAD_DIALOG))

        info_card = ctk.CTkFrame(tab, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                  border_width=BORDER_W, border_color=C_BORDER_SOFT)
        info_card.pack(fill=X, pady=(0, PAD_DIALOG))
        attach_hover_glow(info_card)
        self.about_db_label = make_label(info_card, text="", fg=C_TEXT_MAIN,
                                         font_size=FS_SMALL)
        self.about_db_label.configure(wraplength=620, justify=LEFT, anchor=W)
        self.about_db_label.pack(anchor=W, padx=PAD_CARD_X,
                                  pady=(PAD_CARD_Y, PAD_TIGHT))
        self.about_mode_label = make_label(info_card, text="", fg=C_TEXT_SECONDARY,
                                           font_size=FS_SMALL)
        self.about_mode_label.pack(anchor=W, padx=PAD_CARD_X, pady=(0, PAD_CARD_Y))

        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.pack(fill=X)
        make_button(btn_row, "使用教程",
                     command=self.app.show_tutorial).pack(
                        side=LEFT, padx=(0, PAD_TIGHT))
        make_button(btn_row, "功能列表",
                     command=self.app.show_about_detail).pack(
                        side=LEFT, padx=PAD_TIGHT)
        make_button(btn_row, "退出程序",
                     command=self.app.request_exit).pack(
                        side=LEFT, padx=PAD_TIGHT)

    # ==================== 状态同步 ====================
    def reload(self):
        """把当前设置重新读进控件（进入页面时调用）。不触发自动保存。"""
        self._loading = True
        try:
            self.storage_var.set(self.settings.storage_mode)
            self.role_var.set(self.settings.role)
            for seg, key in ((getattr(self, "mode_seg", None),
                              self.settings.storage_mode),
                             (getattr(self, "role_seg", None),
                              self.settings.role),
                             (getattr(self, "anim_seg", None),
                              "on" if ANIMATIONS_ENABLED else "off")):
                if seg is not None and seg.current() != key:
                    seg.select(key, animate=False)
        except Exception:
            pass
        self._update_db_labels()
        self._loading = False

    def _update_db_labels(self):
        db_str = (str(self.settings._settings_file.parent)
                  if self.settings._settings_file else "未绑定")
        mode = "合并存储" if self.settings.storage_mode == "merged" else "隔离存储"
        role = "玩家" if self.settings.role == "player" else "开发者"
        for widget, text in ((self.db_path_label, db_str),
                             (self.about_db_label, f"数据库位置: {db_str}"),
                             (self.about_mode_label,
                              f"当前模式: {mode} · 用户身份: {role}")):
            try:
                widget.configure(text=text)
            except Exception:
                pass

    def show_about_tab(self):
        self.show_tab("about")

    # ==================== 行为（语义与原 SettingsDialog 一致） ====================
    def on_switch_db(self):
        show_info("切换数据库",
            "切换数据库后需要重新打开整合包。\n\n"
            "原数据库不会被删除，可随时切回。", parent=self.root)
        if self.on_db_action:
            self.on_db_action('switch')

    def on_merge_db(self):
        if self.on_db_action:
            self.on_db_action('merge')

    def on_migrate_legacy(self):
        if self.on_db_action:
            self.on_db_action('migrate_legacy')

    def on_open_db(self):
        db = self.settings._settings_file.parent if self.settings._settings_file else None
        if db and db.exists():
            try:
                os.startfile(str(db))
            except Exception:
                pass

    # ==================== 自动保存 ====================
    def _can_persist(self):
        """没有数据库就没有落盘位置：只提示，不弹模态打断。"""
        if self.settings._settings_file is None:
            if hasattr(self.app, "toast"):
                self.app.toast("数据库未初始化，设置无法保存", "warning")
            return False
        return True

    def _on_auto_save(self):
        """单选项一改就落盘：不再需要「保存设置」按钮。"""
        if self._loading:
            return
        changed = (self.storage_var.get() != self.settings.storage_mode
                   or self.role_var.get() != self.settings.role)
        if not changed:
            return          # 重复点同一个单选项不算改动，不刷提示
        if not self._can_persist():
            self.reload()   # 回退控件，保持界面与真实设置一致
            return
        self.save(notify=True)

    def save(self, notify=True):
        """把控件当前值写进 settings 并落盘；返回是否成功。"""
        old_mode = self.settings.storage_mode
        self.settings.storage_mode = self.storage_var.get()
        self.settings.role = self.role_var.get()
        if not self.settings.save():
            show_error("错误",
                "保存设置失败。\n\n"
                "数据库可能尚未初始化，或数据库目录不可写。",
                parent=self.root)
            return False
        self._update_db_labels()
        if notify:
            self._flash_saved()
        if old_mode != self.settings.storage_mode:
            if self.settings.storage_mode == "merged":
                show_warning("提示",
                    "已切换到合并存储。\n\n"
                    "所有整合包将共用同一套预设。\n"
                    "不同整合包的同名枪包可能互相覆盖。\n\n"
                    "重新打开整合包后生效。",
                    parent=self.root)
            else:
                show_info("提示",
                    "已切换到隔离存储。\n\n"
                    "每个整合包使用独立数据库。\n"
                    "重新打开整合包后生效。",
                    parent=self.root)
        if self.on_save_callback:
            self.on_save_callback()
        return True

    def _reset_defaults(self):
        if not self._can_persist():
            return
        self._loading = True
        try:
            self.storage_var.set("isolated")
            self.role_var.set("player")
        finally:
            self._loading = False
        if self.save(notify=True) and hasattr(self.app, "toast"):
            self.app.toast("已恢复默认设置", "info")

    def _flash_saved(self):
        """自动保存回显：先亮一下，再曲线淡回提示色。"""
        try:
            self.saved_label.configure(text="✓ 已自动保存",
                                        text_color=C_SUCCESS)
        except Exception:
            return

        def fade():
            def frame(e, raw):
                try:
                    self.saved_label.configure(
                        text_color=lerp_color(C_SUCCESS, C_TEXT_MUTED, e))
                except Exception:
                    pass

            tween(self.saved_label, "saved", 320, frame,
                  on_done=self._reset_saved_text, easing=ease_in_out_cubic,
                  fps=FPS_COLOR)

        try:
            self.root.after(760, fade)
        except Exception:
            fade()

    def _reset_saved_text(self):
        try:
            self.saved_label.configure(text=self._saved_hint(),
                                        text_color=C_TEXT_MUTED)
        except Exception:
            pass


# ==================== 主窗口 ====================
class PulsesSwapApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{PROJECT_NAME} v{VERSION}")
        # 高分屏下窗口会被 window_scaling 放大，启动尺寸要按屏幕收口，
        # 否则 125%/150% 时窗口可能比屏幕还高。
        try:
            scr_w = int(self.root.winfo_screenwidth() or WINDOW_W)
            scr_h = int(self.root.winfo_screenheight() or WINDOW_H)
        except Exception:
            scr_w, scr_h = WINDOW_W, WINDOW_H
        scale = UI_SCALE if UI_SCALE > 0 else 1.0
        win_w = int(min(WINDOW_W, max(WINDOW_MIN_W, scr_w / scale - 40)))
        win_h = int(min(WINDOW_H, max(WINDOW_MIN_H, scr_h / scale - 90)))
        self.root.geometry(f"{win_w}x{win_h}")
        self.root.minsize(WINDOW_MIN_W, WINDOW_MIN_H)

        # ==================== Win11 透明修复 ====================
        try:
            self.root.attributes('-alpha', 1.0)
        except Exception:
            pass
        try:
            self.root.wm_attributes('-alpha', 1.0)
        except Exception:
            pass
        try:
            self.root.attributes('-transparentcolor', '')
        except Exception:
            pass
        try:
            self.root.configure(fg_color=C_WINDOW_BG)
        except Exception:
            try:
                self.root.configure(bg=C_WINDOW_BG)
            except Exception:
                pass

        self._disable_win11_transparency()
        # ========================================================

        self.current_pack_path: Path | None = None
        self.tacz_path: Path | None = None
        self.preset_manager: PresetManager | None = None
        self.log_manager: LogManager | None = None
        self.settings = AppSettings()
        self.recent_manager: RecentPacksManager | None = None
        self.tacz_watcher: TaczWatcher | None = None

        self.is_applying = False
        self.current_selected_preset: str | None = None
        self.show_full_log = False
        self.loading_presets = False
        self.recent_visible = False
        self.dont_remind_this_session = False
        self.db_ready = False
        self.last_after_migrate_mode = "mark"

        self.guide: GuideManager | None = None

        # worker 线程 → 主线程的投递队列，越早启动越好
        start_ui_pump(self.root)
        self.setup_ui()
        self.setup_menu()

        self.root.after(80, self._disable_win11_transparency)
        self.root.after(150, self._init_database_flow)

    def _disable_win11_transparency(self):
        if not IS_WINDOWS:
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if not hwnd:
                hwnd = self.root.winfo_id()
            _apply_opaque_window(hwnd)
        except Exception:
            pass

    # ==================== 数据库初始化 ====================
    def _init_database_flow(self):
        db_path = DatabaseLocator.load_db_path()
        if db_path and DatabaseLocator.is_valid_database(db_path):
            self._use_database(db_path)
            return

        if db_path and LegacyDatabaseMigrator.is_legacy_database(db_path):
            if ask_yes_no("检测到旧版数据库",
                f"检测到旧版 FGC_database:\n{db_path}\n\n"
                f"是否适配为新版数据库？\n"
                f"（可选择迁移后标记或删除原库）"):
                DatabaseLocator.init_database(DEFAULT_DB_DIR)
                self._use_database(DEFAULT_DB_DIR)
                self.root.after(200, lambda p=db_path: self.migrate_legacy_database(p))
            return

        if db_path:
            self.log_manager.log(f"数据库位置失效: {db_path}", 'WARNING')
        self.log_manager.log("未检测到数据库，请选择定位或新建", 'GUIDE')
        dialog = DatabaseLocatorDialog(self.root)
        result = dialog.show()
        if result:
            DatabaseLocator.save_db_path(result)
            self._use_database(result)
            if getattr(dialog, 'legacy_to_migrate', None):
                self.root.after(200, lambda p=dialog.legacy_to_migrate:
                                 self.migrate_legacy_database(p))
        else:
            self.log_manager.log("未选择数据库，部分功能不可用", 'WARNING')

    def _use_database(self, db_path: Path):
        self.settings.bind_database(db_path)
        self.recent_manager = RecentPacksManager(db_path / ".global.json")
        self.db_ready = True
        self.update_recent_list()
        self.log_manager.log(f"{PROJECT_NAME} v{VERSION} 启动成功，作者: {AUTHOR}", 'SUCCESS')
        self.log_manager.log(f"数据库位置: {db_path}", 'INFO', verbose=True)
        self.log_manager.log(
            "运行模式: " + ("绿色版（数据写在程序目录）" if IS_PORTABLE_MODE
                        else "安装版（数据写在用户目录）"),
            'INFO', verbose=True)
        self.log_manager.log(
            f"存储模式: {'合并' if self.settings.storage_mode == 'merged' else '隔离'}",
            'INFO', verbose=True)
        self.log_manager.log(
            f"用户身份: {'玩家' if self.settings.role == 'player' else '开发者'}",
            'INFO', verbose=True)
        if HAS_WATCHDOG:
            self.log_manager.log("watchdog 已就绪，可实时监控 TACZ 文件变化",
                                 'INFO', verbose=True)
        else:
            self.log_manager.log("watchdog 未安装，文件变更需手动刷新 (pip install watchdog)", 'WARNING')
        if IS_WINDOWS:
            self.log_manager.log("已启用 Windows 原生回收站删除", 'INFO',
                                 verbose=True)
        self.log_manager.log("Step 1 · 拖入整合包根目录（或整合包内任意文件）", 'GUIDE')
        self._update_guide()

    # ==================== UI 构建 ====================
    def setup_ui(self):
        # ===== 骨架：左侧导航栏 + 右侧页面区（替代原来的「左栏 + 右栏」两列） =====
        main_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        main_frame.pack(fill=BOTH, expand=True, padx=PAD_WINDOW, pady=PAD_WINDOW)

        # 覆盖层宿主：所有窗口内弹窗都 place 在这个 frame 上（连侧边栏一起盖住，保证模态）
        self.overlay_host = main_frame
        self.active_page = None
        set_overlay_host(self)

        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=0, minsize=px(SIDEBAR_W))
        main_frame.grid_columnconfigure(1, weight=1)

        # ===== 侧边导航栏：只有品牌 + 导航项，不放任何提示文案 =====
        sidebar = ctk.CTkFrame(main_frame, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                border_width=BORDER_W, border_color=C_BORDER_SOFT,
                                width=SIDEBAR_W)
        # 注意 sticky 必须带 e：只写 "nsw" 时 Tk 只把控件贴西边、不横向拉伸，
        # 侧边栏会被压到内容的自然宽度（124px），看起来又窄又挤。
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, PAD_GAP))
        sidebar.grid_propagate(False)
        self.sidebar = sidebar

        make_label(sidebar, text=PROJECT_NAME, fg=C_ACCENT, font_size=FS_SUBHEAD,
                    bold=True).pack(anchor=W, padx=PAD_CARD_X,
                                    pady=(PAD_CARD_Y, 0))
        make_label(sidebar, text=f"v{VERSION} · {AUTHOR}", fg=C_TEXT_MUTED,
                    font_size=FS_TINY).pack(anchor=W, padx=PAD_CARD_X,
                                            pady=(PAD_MICRO, PAD_GAP))

        # 导航项：纯文字（需求：去掉图标与动画），选中态是一块静态圆角药丸
        nav_items = (("home", "主界面"),
                     ("settings", "设置"),
                     ("log", "日志"))
        nav_height = px(len(nav_items) * (H_NAV + PAD_XS) + 2 * PAD_XS)
        self.nav = CanvasSegmented(
            sidebar, nav_items, command=self.show_page,
            orientation="vertical", item_height=H_NAV, pad=4, gap=PAD_XS,
            radius=R_CONTROL, bg_color=C_CARD_BG, pill_color=C_ACCENT_SOFT,
            hover_color=C_ACCENT_SOFT, text_color=C_TEXT_MAIN,
            active_text_color=C_ACCENT, font_size=FS_BODY, bold_active=True,
            text_anchor="w", text_pad=14, duration_ms=240, height=nav_height)
        self.nav.pack(fill=X, padx=PAD_XS)

        # ===== 侧边栏底部状态卡 =====
        # 侧边栏有 800+px 高，只有品牌 + 三个导航项会显得空；
        # 底部钉一张状态卡（整合包 / 状态 / 当前预设），既补留白又是真信息。
        status_card = ctk.CTkFrame(sidebar, fg_color=C_PANEL_ALT_BG,
                                    corner_radius=R_CONTROL,
                                    border_width=BORDER_W,
                                    border_color=C_BORDER_SOFT)
        status_card.pack(side=BOTTOM, fill=X, padx=PAD_XS,
                          pady=(PAD_GAP, PAD_CARD_Y))
        attach_hover_glow(status_card)
        make_label(status_card, text="当前整合包", fg=C_TEXT_MUTED,
                    font_size=FS_TINY).pack(anchor=W, padx=PAD_CARD_X,
                                             pady=(PAD_CARD_Y, PAD_MICRO))
        self.sb_pack_label = make_label(status_card, text="未选择",
                                         fg=C_TEXT_MAIN, font_size=FS_SMALL,
                                         bold=True)
        self.sb_pack_label.pack(anchor=W, padx=PAD_CARD_X)
        self.sb_status_label = make_label(status_card, text="状态: 未加载",
                                           fg=C_ERROR, font_size=FS_TINY)
        self.sb_status_label.pack(anchor=W, padx=PAD_CARD_X, pady=(PAD_TIGHT, 0))
        self.sb_preset_label = make_label(status_card, text="当前预设: 无",
                                           fg=C_ACCENT, font_size=FS_TINY)
        self.sb_preset_label.pack(anchor=W, padx=PAD_CARD_X,
                                   pady=(PAD_MICRO, PAD_CARD_Y))

        # ===== 右侧内容列：页面区 + 全局状态条（进度条） =====
        content_col = ctk.CTkFrame(main_frame, fg_color="transparent")
        content_col.grid(row=0, column=1, sticky="nsew")
        content_col.grid_columnconfigure(0, weight=1)
        content_col.grid_rowconfigure(0, weight=1)
        content_col.grid_rowconfigure(1, weight=0)

        self.page_host = ctk.CTkFrame(content_col, fg_color="transparent")
        self.page_host.grid(row=0, column=0, sticky="nsew")
        # 页面放在 Canvas 里：Canvas 会裁剪子窗口，推入/推出的过程不会溢到侧边栏
        self.stack = SlideStack(self.page_host, bg_color=C_WINDOW_BG,
                                 duration_ms=260)
        self.page_canvas = self.stack.canvas

        # 进度条移到全局状态条：原来在右栏里，show_progress/hide_progress 的
        # pack/pack_forget 语义不变，只是父容器换成了这里
        self.status_bar = ctk.CTkFrame(content_col, fg_color="transparent",
                                        height=1)
        self.status_bar.grid(row=1, column=0, sticky="ew")
        self.progress_bar = ctk.CTkProgressBar(self.status_bar, height=H_PROGRESS,
                                                 corner_radius=R_PROGRESS,
                                                 fg_color=C_PANEL_ALT_BG,
                                                 progress_color=C_ACCENT)
        self.progress_bar.pack(fill=X, pady=(0, PAD_XS))
        self.progress_bar.pack_forget()
        self.progress_label = make_label(self.status_bar, text="",
                                          fg=C_TEXT_SECONDARY, font_size=FS_TINY)
        self.progress_label.pack(fill=X, pady=(0, PAD_XS))
        self.progress_label.pack_forget()

        # ===== 页面 =====
        self.settings_page = None
        self.pages = {}
        self.pages["home"] = self._build_home_page()
        self.pages["log"] = self._build_log_page()
        # 主界面右下角的日志栏与「日志」页共用同一份日志流
        if getattr(self, "home_log_text", None) is not None:
            self.log_manager.attach(self.home_log_text)
        self.settings_page = SettingsPage(
            self.stack.canvas, self,
            on_save_callback=self._on_settings_saved,
            on_db_action=self._on_db_action)
        self.pages["settings"] = self.settings_page.frame
        for key in ("home", "settings", "log"):
            self.stack.add(key, self.pages[key])
        # 三页先各自布局一次（这笔开销只付一次，别落在切换动画的第一帧上）
        self.stack.current = "home"
        self.stack.prewarm()

        # ===== 新手引导注册 =====
        self.guide = GuideManager(self.root)
        self.guide.register(
            "step1_select_pack", [self.pack_drop_area],
            desc="Step 1 · 拖入整合包根目录，或点击「选择」定位")
        self.guide.register(
            "step2_create_preset", [self.create_preset_btn],
            desc="Step 2 · 点击「+ 创建」新建预设，放入枪包")
        self.guide.register(
            "step3_apply", [self.apply_btn],
            desc="Step 4 · 点击「一键替换」启用预设")

        self.show_page("home", animate=False)
        self._play_entrance()

    # ==================== 入场动画 ====================
    def _play_entrance(self):
        """启动入场：当前页从右侧轻轻滑入，侧边栏滑块同步淡入。"""
        # 入场只做滑块淡入：搬页面窗口项（整棵控件树）每帧要重排子窗口，
        # 是这里最贵的一类操作，放在启动第一帧最容易看出卡顿。
        self._update_nav_state(self.active_page, animate=True)

    # ==================== 页面切换 ====================
    PAGE_ORDER = ("home", "settings", "log")

    def show_page(self, name, animate=True):
        """切换右侧页面：整页在 Canvas 里推入/推出，侧边栏滑块同步滑动。

        方向按需求走「点哪边内容就往哪边走」：
          点下面/右面的选项 → 内容往下/右走（新页从下/右方进来）
          点上面/左面的选项 → 内容往上/左走（新页从上/左方进来）
        侧边栏是竖排，所以页面竖着滑（axis="y"）。
        """
        if name not in self.pages or name == self.active_page:
            return
        cancel_tween(self.stack.canvas, "entrance")
        previous = self.active_page
        direction = 1
        if previous is not None:
            try:
                # 点下面/右面的选项 → 内容往下/右走 → 新页从上方/左方进来
                # （SlideStack 里 direction=+1 表示新页起点在 -span）
                direction = (1 if self.PAGE_ORDER.index(name)
                             > self.PAGE_ORDER.index(previous) else -1)
            except ValueError:
                direction = 1
        self.active_page = name
        self._update_nav_state(name, animate=animate)
        self.stack.show(name, animate=animate, direction=direction, axis="y")
        if animate:
            # 切页动画结束后记一次实测帧率（完整日志可见）：
            # 卡不卡用数字说话，不靠感觉。
            def _log_fps():
                interval, frames = take_frame_stats()
                if frames > 3:
                    self.log_manager.log(
                        f"动画实测: {frames} 帧 · 平均帧间隔 {interval:.1f}ms "
                        f"(≈{1000 / max(interval, 0.01):.0f}fps)",
                        'INFO', verbose=True)
            ui_call(self.root, lambda: self.root.after(340, _log_fps))
        if name == "settings" and self.settings_page is not None:
            self.settings_page.reload()

    def _update_nav_state(self, name=None, animate=True):
        target = name or self.active_page
        nav = getattr(self, "nav", None)
        if nav is None or not target:
            return
        if nav.current() == target:
            return
        nav.select(target, animate=animate)

    def toast(self, text, kind="success", duration_ms=1700):
        """右上角浮出提示（曲线滑入 + 自动淡出），同一时刻只留一条。"""
        previous = getattr(self, "_toast", None)
        if previous is not None:
            try:
                previous.close()
            except Exception:
                pass
        try:
            self._toast = Toast(self, text, kind=kind, duration_ms=duration_ms)
        except Exception:
            self._toast = None

    def open_log_page(self):
        self.show_page("log")
        self.toggle_log_mode()

    # ==================== 主界面（Step 1/2/3 + 枪包列表） ====================
    def _build_home_page(self):
        page = ctk.CTkFrame(self.stack.canvas, fg_color=C_WINDOW_BG)
        page.grid_rowconfigure(0, weight=1)
        page.grid_columnconfigure(0, weight=0, minsize=px(LEFT_COL_W))
        page.grid_columnconfigure(1, weight=1)

        left_panel = ctk.CTkFrame(page, fg_color="transparent")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, PAD_GAP))
        # 纵向预算：Step1/Step3 固定高度，剩余空间全部给 Step2 的预设列表，
        # 这样窗口变小/DPI 放大时先压缩列表，Step3 卡片不会被裁（见 H_STEP*_MIN）
        left_panel.grid_columnconfigure(0, weight=1)
        left_panel.grid_rowconfigure(0, weight=0, minsize=px(H_STEP1_MIN))
        left_panel.grid_rowconfigure(1, weight=1, minsize=px(H_STEP2_MIN))
        left_panel.grid_rowconfigure(2, weight=0, minsize=px(H_STEP3_MIN))

        right_panel = ctk.CTkFrame(page, fg_color="transparent")
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.grid_columnconfigure(0, weight=1)
        right_panel.grid_rowconfigure(0, weight=1)
        right_panel.grid_rowconfigure(1, weight=0)

        # ===== 整合包分组（大拖入框） =====
        pack_group = ctk.CTkFrame(left_panel, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                    border_width=BORDER_W, border_color=C_BORDER_SOFT)
        pack_group.grid(row=0, column=0, sticky="nsew", pady=(0, PAD_GAP))
        attach_hover_glow(pack_group)
        make_label(pack_group, text="Step 1 · 整合包", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        pack_content = ctk.CTkFrame(pack_group, fg_color="transparent")
        pack_content.pack(fill=X, padx=PAD_CARD_X, pady=(0, PAD_CARD_Y))

        # 大拖入框
        self.pack_drop_area = ctk.CTkFrame(pack_content, fg_color=C_PANEL_ALT_BG,
                                             corner_radius=R_CARD, border_width=BORDER_W,
                                             border_color=C_BORDER_SOFT)
        self.pack_drop_area.pack(fill=X, pady=(0, PAD_TIGHT))

        self.pack_drop_label = ctk.CTkLabel(
            self.pack_drop_area,
            text="Step 1 · 拖入整合包根目录\n"
                 "或整合包内任意文件（自动定位 tacz）",
            text_color=C_TEXT_SECONDARY, font=(FONT_FAMILY, FS_BODY),
            justify=LEFT, anchor="w", fg_color="transparent")
        self.pack_drop_label.pack(fill=X, padx=PAD_GAP, pady=(PAD_GAP, PAD_XS))

        # 路径显示
        self.pack_path_frame, self.pack_path_label = make_display_box(
            self.pack_drop_area, text="未选择", height=H_CONTROL)
        self.pack_path_frame.pack(fill=X, padx=PAD_GAP, pady=(0, PAD_TIGHT))

        # 按钮行
        self.pack_btn_row = ctk.CTkFrame(self.pack_drop_area,
                                          fg_color="transparent")
        pack_btn_row = self.pack_btn_row
        pack_btn_row.pack(fill=X, padx=PAD_INNER, pady=(0, PAD_GAP))

        self.select_pack_btn = make_button(pack_btn_row, "选择",
                                             command=self.select_pack,
                                             width=60, accent=True)
        self.select_pack_btn.pack(side=LEFT, padx=(0, PAD_XS))
        self.open_pack_btn = make_button(pack_btn_row, "目录",
                                           command=self.open_pack_folder,
                                           width=52, state="disabled")
        self.open_pack_btn.pack(side=LEFT, padx=(0, PAD_XS))
        self.close_pack_btn = make_button(pack_btn_row, "关闭",
                                            command=self.close_pack,
                                            width=56)
        self.close_pack_btn.pack(side=LEFT, padx=(0, PAD_XS))
        self.recent_toggle_btn = make_button(pack_btn_row, "▼ 最近",
                                               command=self.toggle_recent,
                                               width=70)
        self.recent_toggle_btn.pack(side=LEFT)

        # 绑定 DND 到拖入框和提示文字
        if HAS_DND:
            for w in (self.pack_drop_area, self.pack_drop_label):
                try:
                    w.drop_target_register(DND_FILES)
                    w.dnd_bind('<<Drop>>', self.on_pack_drop)
                except Exception:
                    pass

        # 最近打开：做成「不参与布局」的下拉浮层。
        # 挂在按钮行下面、用 place 定位 —— place 不影响 pack/grid 的排版，
        # 所以展开/收起时整页不会重新布局。
        # （之前是 pack + 高度补间：每帧改高度都要重排整页，Windows 上就是
        #   又慢又闪白，用户指着这个按钮反馈的。）
        self.recent_wrap = ctk.CTkFrame(self.pack_btn_row,
                                         fg_color="transparent", height=1)
        self.recent_wrap.pack_propagate(False)
        self.recent_frame = ctk.CTkFrame(self.recent_wrap, fg_color=C_PANEL_ALT_BG,
                                          corner_radius=R_CONTROL, border_width=BORDER_W,
                                          border_color=C_BORDER_SOFT)
        self.recent_listbox = Listbox(self.recent_frame, height=4,
                                       bg=C_PANEL_ALT_BG, fg=C_TEXT_MAIN,
                                       selectbackground=C_ACCENT_SOFT,
                                       selectforeground=C_ACCENT,
                                       relief='flat', highlightthickness=0,
                                       font=(FONT_FAMILY,
                                             max(1, int(FS_SMALL * UI_SCALE))))
        self.recent_scroll = make_list_scroll(self.recent_frame,
                                               self.recent_listbox, width=8)
        self.recent_listbox.pack(side=LEFT, fill=BOTH, expand=True,
                                  padx=(PAD_TIGHT, 0), pady=PAD_TIGHT)
        self.recent_scroll.pack(side=RIGHT, fill=Y, padx=(2, PAD_TIGHT),
                                 pady=PAD_TIGHT)
        self.recent_listbox.bind('<Double-Button-1>', self.on_recent_double_click)

        # 状态标签
        self.pack_status_label = make_label(pack_content, text="状态: 未加载",
                                             fg=C_ERROR, font_size=FS_SMALL)
        self.pack_status_label.pack(anchor=W, pady=(PAD_XS, 0))
        self.pack_name_label = make_label(pack_content, text="当前预设: 无",
                                           fg=C_ACCENT, font_size=FS_SMALL)
        self.pack_name_label.pack(anchor=W, pady=(PAD_MICRO, 0))

        # ===== 预设管理 =====
        preset_group = ctk.CTkFrame(left_panel, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                     border_width=BORDER_W, border_color=C_BORDER_SOFT)
        preset_group.grid(row=1, column=0, sticky="nsew", pady=(0, PAD_GAP))
        attach_hover_glow(preset_group)
        make_label(preset_group, text="Step 2 · 预设管理", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        preset_content = ctk.CTkFrame(preset_group, fg_color="transparent")
        preset_content.pack(fill=BOTH, expand=True, padx=PAD_CARD_X,
                            pady=(0, PAD_CARD_Y))

        preset_list_wrap = ctk.CTkFrame(preset_content, fg_color=C_CARD_BG,
                                         corner_radius=R_CONTROL, border_width=BORDER_W,
                                         border_color=C_BORDER_SOFT)
        preset_list_wrap.pack(fill=BOTH, expand=True, pady=(0, PAD_GAP))
        attach_hover_glow(preset_list_wrap)
        self.preset_listbox = Listbox(preset_list_wrap, height=4,
                                       bg=C_CARD_BG, fg=C_TEXT_MAIN,
                                       selectbackground=C_ACCENT_SOFT,
                                       selectforeground=C_ACCENT,
                                       relief='flat', highlightthickness=0,
                                       font=(FONT_FAMILY,
                                             max(1, int(FS_BODY * UI_SCALE))))
        self.preset_scroll = make_list_scroll(preset_list_wrap,
                                               self.preset_listbox)
        self.preset_listbox.pack(side=LEFT, fill=BOTH, expand=True,
                                  padx=(PAD_XS, 0), pady=PAD_XS)
        self.preset_scroll.pack(side=RIGHT, fill=Y, padx=(2, PAD_XS),
                                 pady=PAD_XS)
        self.preset_listbox.bind('<<ListboxSelect>>', self.on_preset_selected)
        self.preset_listbox.bind('<Button-3>', self.show_preset_context_menu)

        # 拖入框：预设/更新包
        self.drop_area = ctk.CTkFrame(preset_content, fg_color=C_PANEL_ALT_BG,
                                       corner_radius=R_CARD, border_width=BORDER_W,
                                       border_color=C_BORDER_SOFT, height=H_DROP_AREA)
        self.drop_area.pack(fill=X, pady=(0, PAD_GAP))
        self.drop_area.pack_propagate(False)
        attach_hover_glow(self.drop_area)
        self.drop_label = ctk.CTkLabel(
            self.drop_area,
            text="Step 2 · 导入预设包 / 更新包\n"
                 "拖入 .fgcpack / .fgcupdate，或点击此处选择",
            text_color=C_TEXT_SECONDARY, font=(FONT_FAMILY, FS_TINY),
            justify=LEFT, anchor="w", fg_color="transparent")
        self.drop_label.pack(fill=BOTH, expand=True, padx=PAD_INNER, pady=PAD_INNER)
        self.drop_label.bind('<Button-1>', lambda e: self.select_import_file())
        self.drop_area.bind('<Button-1>', lambda e: self.select_import_file())
        if HAS_DND:
            try:
                self.drop_area.drop_target_register(DND_FILES)
                self.drop_area.dnd_bind('<<Drop>>', self.on_drop_file)
                self.drop_label.drop_target_register(DND_FILES)
                self.drop_label.dnd_bind('<<Drop>>', self.on_drop_file)
            except Exception:
                pass

        preset_btn_frame = ctk.CTkFrame(preset_content, fg_color="transparent")
        preset_btn_frame.pack(fill=X)
        self.create_preset_btn = make_button(preset_btn_frame, "＋ 创建",
                                              command=self.create_preset,
                                              state="disabled", width=68)
        self.create_preset_btn.pack(side=LEFT, padx=(0, PAD_XS))
        self.export_preset_btn = make_button(preset_btn_frame, "导出",
                                              command=self.export_preset,
                                              state="disabled", width=56)
        self.export_preset_btn.pack(side=LEFT, padx=PAD_XS)
        self.export_incremental_btn = make_button(preset_btn_frame, "更新",
                                                   command=self.export_incremental,
                                                   state="disabled", width=56)
        self.export_incremental_btn.pack(side=LEFT, padx=PAD_XS)
        self.refresh_preset_btn = make_button(preset_btn_frame, "刷新",
                                               command=self.refresh_presets,
                                               state="disabled", width=52)
        self.refresh_preset_btn.pack(side=LEFT, padx=PAD_XS)
        self.open_db_btn = make_button(preset_btn_frame, "数据库",
                                        command=self.open_preset_manager,
                                        state="disabled", width=64)
        self.open_db_btn.pack(side=LEFT, padx=PAD_XS)
        self.loading_label = make_label(preset_btn_frame, text="", fg=C_ACCENT,
                                        font_size=FS_TINY)
        self.loading_label.pack(side=LEFT, padx=PAD_TIGHT)

        # ===== 预设详情 =====
        info_group = ctk.CTkFrame(left_panel, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                   border_width=BORDER_W, border_color=C_BORDER_SOFT)
        info_group.grid(row=2, column=0, sticky="ew")
        attach_hover_glow(info_group)
        make_label(info_group, text="Step 3 · 预设详情", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        info_content = ctk.CTkFrame(info_group, fg_color="transparent")
        info_content.pack(fill=X, padx=PAD_CARD_X, pady=(0, PAD_CARD_Y))

        self.preset_name_label = make_label(info_content, text="预设: 未选择",
                                             fg=C_ACCENT, font_size=FS_SUBHEAD,
                                             bold=True)
        self.preset_name_label.pack(anchor=W)
        self.preset_version_label = make_label(info_content, text="版本号: 无",
                                                fg=C_TEXT_SECONDARY, font_size=FS_SMALL)
        self.preset_version_label.pack(anchor=W, pady=(PAD_MICRO, 0))
        self.preset_status_label = make_label(info_content, text="状态: 未应用",
                                               fg=C_TEXT_SECONDARY, font_size=FS_SMALL)
        self.preset_status_label.pack(anchor=W, pady=(PAD_MICRO, 0))

        version_edit_frame = ctk.CTkFrame(info_content, fg_color="transparent")
        version_edit_frame.pack(fill=X, pady=(PAD_INNER, 0))
        make_label(version_edit_frame, text="Step 3 · 版本号:", fg=C_TEXT_MAIN,
                    font_size=FS_SMALL).pack(side=LEFT)
        self.version_entry = make_entry(version_edit_frame, width=120)
        self.version_entry.pack(side=LEFT, fill=X, expand=True,
                                padx=(PAD_TIGHT, PAD_TIGHT))
        self.version_entry.bind('<Return>', lambda e: self.save_version())
        self.save_version_btn = make_button(version_edit_frame, "保存",
                                             command=self.save_version,
                                             state="disabled", width=60)
        self.save_version_btn.pack(side=RIGHT)

        # ===== 枪包列表 =====
        gunpack_group = ctk.CTkFrame(right_panel, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                      border_width=BORDER_W, border_color=C_BORDER_SOFT)
        gunpack_group.grid(row=0, column=0, sticky="nsew", pady=(0, PAD_GAP))
        attach_hover_glow(gunpack_group)
        make_label(gunpack_group, text="枪包列表", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        gunpack_content = ctk.CTkFrame(gunpack_group, fg_color="transparent")
        gunpack_content.pack(fill=BOTH, expand=True, padx=PAD_CARD_X,
                             pady=(0, PAD_CARD_Y))

        toolbar_frame = ctk.CTkFrame(gunpack_content, fg_color="transparent")
        toolbar_frame.pack(fill=X, pady=(0, PAD_TIGHT))
        self.gunpack_count_label = make_label(toolbar_frame, text="共 0 个枪包",
                                               fg=C_TEXT_MAIN, font_size=FS_SMALL)
        self.gunpack_count_label.pack(side=LEFT)

        self.refresh_gunpack_btn = make_button(toolbar_frame, "刷新",
                                                command=self.refresh_gunpacks,
                                                state="disabled", width=56)
        self.refresh_gunpack_btn.pack(side=RIGHT)

        self.open_tacz_btn = make_button(toolbar_frame, "打开TACZ",
                                          command=self.open_tacz_folder,
                                          state="disabled", width=84)
        self.open_tacz_btn.pack(side=RIGHT, padx=(0, PAD_XS))

        self.refresh_all_btn = make_button(toolbar_frame, "全部刷新",
                                            command=self.refresh_all, width=76)
        self.refresh_all_btn.pack(side=RIGHT, padx=(0, PAD_XS))

        gunpack_list_wrap = ctk.CTkFrame(gunpack_content, fg_color=C_CARD_BG,
                                          corner_radius=R_CONTROL, border_width=BORDER_W,
                                          border_color=C_BORDER_SOFT)
        gunpack_list_wrap.pack(fill=BOTH, expand=True)
        attach_hover_glow(gunpack_list_wrap)
        self.gunpack_listbox = Listbox(gunpack_list_wrap, height=6,
                                        bg=C_CARD_BG, fg=C_TEXT_MAIN,
                                        selectbackground=C_ACCENT_SOFT,
                                        selectforeground=C_ACCENT,
                                        relief='flat', highlightthickness=0,
                                        font=(FONT_FAMILY,
                                              max(1, int(FS_BODY * UI_SCALE))))
        self.gunpack_scroll = make_list_scroll(gunpack_list_wrap,
                                                self.gunpack_listbox)
        self.gunpack_listbox.pack(side=LEFT, fill=BOTH, expand=True,
                                   padx=(PAD_XS, 0), pady=PAD_XS)
        self.gunpack_scroll.pack(side=RIGHT, fill=Y, padx=(2, PAD_XS),
                                  pady=PAD_XS)

        self.apply_btn = make_button(right_panel, "Step 4 · 一键替换",
                                      command=self.apply_preset,
                                      state="disabled", accent=True)
        self.apply_btn.grid(row=1, column=0, sticky="ew")

        # ===== 分割线 + 日志栏 =====
        # 需求：分割线上面是「一键替换 + 工具条按钮 + 枪包列表」，下面放日志
        divider = ctk.CTkFrame(right_panel, fg_color=C_BORDER_SOFT, height=1)
        divider.grid(row=2, column=0, sticky="ew", pady=(PAD_GAP, PAD_GAP))

        home_log_group = ctk.CTkFrame(right_panel, fg_color=C_CARD_BG,
                                       corner_radius=R_CARD, border_width=BORDER_W,
                                       border_color=C_BORDER_SOFT)
        home_log_group.grid(row=3, column=0, sticky="ew")
        attach_hover_glow(home_log_group)
        log_head = ctk.CTkFrame(home_log_group, fg_color="transparent")
        log_head.pack(fill=X, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        make_label(log_head, text="日志", fg=C_TEXT_MUTED,
                    font_size=FS_TINY).pack(side=LEFT)
        make_button(log_head, "清空", command=self.clear_log,
                     width=48).pack(side=RIGHT)
        self.home_log_text = ctk.CTkTextbox(
            home_log_group, height=H_HOME_LOG, fg_color=C_INPUT_BG,
            border_color=C_BORDER_SOFT, border_width=BORDER_W,
            corner_radius=R_CONTROL, text_color=C_TEXT_MAIN,
            font=(FONT_FAMILY_MONO, FS_SMALL), wrap="word")
        self.home_log_text.pack(fill=X, padx=PAD_CARD_X, pady=(0, PAD_CARD_Y))

        return page

    # ==================== 日志页 ====================
    def _build_log_page(self):
        page = ctk.CTkFrame(self.stack.canvas, fg_color=C_WINDOW_BG)
        log_group = ctk.CTkFrame(page, fg_color=C_CARD_BG, corner_radius=R_CARD,
                                  border_width=BORDER_W, border_color=C_BORDER_SOFT)
        log_group.pack(fill=BOTH, expand=True)
        attach_hover_glow(log_group)
        make_label(log_group, text="运行日志", fg=C_ACCENT,
                    font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, padx=PAD_CARD_X, pady=(PAD_CARD_Y, PAD_TIGHT))
        log_content = ctk.CTkFrame(log_group, fg_color="transparent")
        log_content.pack(fill=BOTH, expand=True, padx=PAD_CARD_X,
                         pady=(0, PAD_CARD_Y))
        log_toolbar = ctk.CTkFrame(log_content, fg_color="transparent")
        log_toolbar.pack(fill=X, pady=(0, PAD_TIGHT))
        self.log_toggle_btn = make_button(log_toolbar, "显示完整日志",
                                           command=self.toggle_log_mode)
        self.log_toggle_btn.pack(side=LEFT)
        self.log_clear_btn = make_button(log_toolbar, "清空", command=self.clear_log)
        self.log_clear_btn.pack(side=LEFT, padx=(PAD_TIGHT, 0))
        self.log_text = ctk.CTkTextbox(log_content, height=H_LOG_BOX,
                                        fg_color=C_INPUT_BG,
                                        border_color=C_BORDER_SOFT, border_width=BORDER_W,
                                        corner_radius=R_CONTROL, text_color=C_TEXT_MAIN,
                                        font=(FONT_FAMILY_MONO, FS_BODY), wrap="word")
        self.log_text.pack(fill=BOTH, expand=True)

        self.log_manager = LogManager(self.log_text, self.root)
        return page

    # ==================== 顶栏菜单（已移除） ====================
    def setup_menu(self):
        """原生菜单栏已去掉：它会在窗口顶部多出一条系统级横条，与设计稿不符。

        原菜单项全部迁到界面内：
          打开整合包 / 打开路径 / 关闭整合包 -> Step 1 的「选择 / 目录 / 关闭」
          程序设置 / 日志显示设置           -> 侧边栏「设置 / 日志」
          预设管理（打开数据库目录）        -> Step 2 的「数据库」
          刷新所有                          -> 枪包列表工具条的「⟳ 全部刷新」
          使用教程 / 关于 / 强制更新校验数据 -> 设置页「关于 / 数据库」选项卡
          退出                              -> 窗口关闭按钮 + 设置页「退出程序」
        """
        try:
            self.root.config(menu="")
        except Exception:
            pass

    def request_exit(self):
        """界面内的退出入口（与窗口关闭按钮同一套语义）。"""
        if self.is_applying:
            if not ask_yes_no("操作进行中",
                    "正在操作中，确定要退出吗？\n\n程序将在任务完成后自动退出。"):
                return
        self._stop_watcher()
        try:
            self.root.quit()
        except Exception:
            pass

    # ==================== 新手引导更新 ====================
    def _update_guide(self):
        if not self.guide:
            return
        if not self.db_ready:
            self.guide.hide()
            return
        if not self.current_pack_path:
            self.guide.show("step1_select_pack")
            return
        if not self.preset_manager or not self.preset_manager.presets:
            self.guide.show("step2_create_preset")
            return
        if not self.current_selected_preset:
            self.guide.hide()
            return
        info = self.preset_manager.presets.get(self.current_selected_preset)
        if info and not info.get('applied', False):
            self.guide.show("step3_apply")
            return
        self.guide.hide()

    # ==================== 整合包拖入 ====================
    def on_pack_drop(self, event):
        """拖入整合包根目录，或整合包内任意文件/文件夹，自动向上定位 tacz"""
        if self.is_applying or self.loading_presets:
            return
        if not self.db_ready:
            show_warning("提示", "数据库未初始化")
            return
        try:
            files = self.root.tk.splitlist(event.data)
        except Exception:
            files = [event.data]
        if not files:
            return
        raw = files[0].strip()
        # 去掉可能的尾部斜杠和引号
        raw = raw.strip('"').strip("'").rstrip('\\/')
        if not raw:
            return
        try:
            drop_path = Path(raw)
        except Exception:
            return

        tacz_path = locate_tacz_by_path(drop_path)
        if not tacz_path:
            show_error("未找到 tacz",
                f"从该路径未能定位到 tacz 文件夹：\n{drop_path}\n\n"
                f"请拖入整合包根目录，或整合包内的任意文件/文件夹。")
            return
        pack_root = tacz_path.parent
        self.log_manager.log(
            f"从拖入路径定位到整合包: {pack_root}", 'INFO')
        self.load_pack(pack_root)

    # ==================== 打开文件夹 ====================
    def open_pack_folder(self):
        if not self.current_pack_path:
            show_warning("提示", "请先选择一个整合包")
            return
        try:
            if self.current_pack_path.exists():
                os.startfile(str(self.current_pack_path))
                self.log_manager.log(f"已打开整合包路径: {self.current_pack_path}",
                                      'INFO', verbose=True)
            else:
                show_error("错误", f"路径不存在: {self.current_pack_path}")
        except Exception as e:
            self.log_manager.log(f"打开整合包路径失败: {e}", 'ERROR')
            show_error("错误", f"打开失败: {e}")

    def open_tacz_folder(self):
        if not self.tacz_path:
            show_warning("提示", "请先选择一个整合包")
            return
        if not self.tacz_path.exists():
            show_error("错误", f"TACZ 路径不存在: {self.tacz_path}")
            return
        try:
            os.startfile(str(self.tacz_path))
            self.log_manager.log(f"已打开 TACZ 文件夹: {self.tacz_path}", 'INFO',
                                      verbose=True)
        except Exception as e:
            self.log_manager.log(f"打开 TACZ 文件夹失败: {e}", 'ERROR')
            show_error("错误", f"打开失败: {e}")

    # ==================== 设置 ====================
    def open_settings(self):
        if not self.db_ready:
            show_warning("提示", "数据库未初始化，请重启程序")
            return
        # 设置已从弹窗改为侧边栏页面（页面内用选项卡分类）
        self.show_page("settings")

    def _on_settings_saved(self):
        """自动保存回调：只写日志 + 右上角浮一条提示，不再弹模态框打断操作。"""
        # 「已切换到 xx 存储」这类回显属于细节：只在完整日志模式下保留
        self.log_manager.log(
            f"设置已保存: 存储模式={self.settings.storage_mode}, 身份={self.settings.role}",
            'SUCCESS', verbose=True)
        self.toast("设置已自动保存", "success")

    def _on_db_action(self, action: str):
        # 数据库动作（切换/合并/适配）都属于主流程，先回到主界面再执行
        self.show_page("home")
        if action == 'switch':
            self.switch_database()
        elif action == 'merge':
            self.merge_database()
        elif action == 'migrate_legacy':
            self.migrate_legacy_database()

    # ==================== 数据库管理 ====================
    def switch_database(self):
        if self.is_applying:
            show_warning("操作进行中", "请等待当前操作完成")
            return
        folder = filedialog.askdirectory(title="选择新的数据库文件夹",
                                          initialdir=str(PROGRAM_DIR))
        if not folder:
            return
        path = Path(folder)
        if LegacyDatabaseMigrator.is_legacy_database(path):
            if ask_yes_no("检测到旧版数据库",
                "该文件夹是旧版 FGC_database。\n\n"
                "是否先适配为新版数据库？"):
                self.migrate_legacy_database(path)
            return
        if (path / LEGACY_MIGRATED_MARKER).exists():
            show_info("提示",
                "该文件夹是已迁移的旧版数据库。\n\n"
                "如需重新适配，请删除旧库根目录下的\n"
                f"{LEGACY_MIGRATED_MARKER} 文件后再试。")
            return
        if not DatabaseLocator.is_valid_database(path):
            if ask_yes_no("新建数据库",
                "该文件夹不是有效数据库，是否初始化为新数据库？"):
                DatabaseLocator.init_database(path)
            else:
                return
        DatabaseLocator.save_db_path(path)
        self.settings.bind_database(path)
        if self.recent_manager:
            self.recent_manager = RecentPacksManager(path / ".global.json")
        self.log_manager.log(f"数据库已切换: {path}", 'SUCCESS')
        show_info("完成", "数据库已切换，请重新打开整合包。")
        self.close_pack()

    def merge_database(self):
        if not self.db_ready:
            show_warning("提示", "数据库未初始化")
            return
        folder = filedialog.askdirectory(title="选择要合并的数据库文件夹",
                                          initialdir=str(PROGRAM_DIR))
        if not folder:
            return
        src = Path(folder)
        dst = self.settings._settings_file.parent if self.settings._settings_file else None
        if not dst:
            return
        if src == dst:
            show_warning("提示", "不能合并到自身")
            return

        src_presets = [p.name for p in src.iterdir()
                       if p.is_dir() and not p.name.startswith('.')]
        conflicts = [n for n in src_presets if (dst / n).exists()]
        msg = f"将把 {len(src_presets)} 个预设合并到当前数据库。"
        if conflicts:
            msg += f"\n\n其中 {len(conflicts)} 个同名预设冲突:\n" + \
                   "\n".join(conflicts[:10])
            if len(conflicts) > 10:
                msg += f"\n... 还有 {len(conflicts)-10} 个"
        msg += "\n\n冲突预设如何处理？"
        choice = self._ask_conflict_mode(msg)
        if not choice:
            return
        stats = LegacyDatabaseMigrator.migrate_legacy_to_new(
            src, dst, self.log_manager, conflict_mode=choice)
        self.log_manager.log(
            f"合并完成: 迁移 {stats['migrated']}, 重命名 {stats['renamed']}, "
            f"跳过 {stats['skipped']}, 错误 {len(stats['errors'])}", 'SUCCESS')
        if stats['errors']:
            show_warning("部分失败", "\n".join(stats['errors'][:10]))
        else:
            show_info("完成", "数据库合并完成。")
        self.refresh_presets()

    def migrate_legacy_database(self, legacy_path: Path = None):
        if not legacy_path:
            folder = filedialog.askdirectory(title="选择旧版 FGC_database 文件夹",
                                              initialdir=str(PROGRAM_DIR))
            if not folder:
                return
            legacy_path = Path(folder)

        if not LegacyDatabaseMigrator.is_legacy_database(legacy_path):
            if (legacy_path / LEGACY_MIGRATED_MARKER).exists():
                if not ask_yes_no("已迁移过",
                    f"该数据库已被标记为「已迁移」:\n{legacy_path}\n\n"
                    f"是否仍要再次适配？（可能产生重复预设）"):
                    return
            else:
                show_error("错误", "所选文件夹不是旧版数据库")
                return

        dst = (self.settings._settings_file.parent
               if self.settings._settings_file else DEFAULT_DB_DIR)

        if self.settings.storage_mode == 'isolated':
            if ask_yes_no("选择目标数据库",
                f"当前为隔离存储模式。\n\n"
                f"是否将旧库适配到全局默认数据库？\n"
                f"{DEFAULT_DB_DIR}\n\n"
                f"选“否”可手动选择目标数据库。"):
                dst = DEFAULT_DB_DIR
            else:
                folder = filedialog.askdirectory(title="选择目标数据库文件夹",
                                                  initialdir=str(PROGRAM_DIR))
                if not folder:
                    return
                dst = Path(folder)
                if not DatabaseLocator.is_valid_database(dst):
                    if ask_yes_no("新建数据库",
                        "目标不是有效数据库，是否初始化为新数据库？"):
                        DatabaseLocator.init_database(dst)
                    else:
                        return

        if not ask_yes_no("确认适配",
            f"将把旧版数据库:\n{legacy_path}\n\n"
            f"适配并合并到:\n{dst}\n\n"
            f"是否继续？"):
            return

        after_mode = self._ask_after_migrate()
        if not after_mode:
            return

        self.progress_bar.pack(fill=X, pady=(0, 4))
        self.progress_label.pack(fill=X, pady=(0, 4))
        self.progress_bar.set(0)
        self.progress_label.configure(text="准备适配...")
        self._disable_buttons(True)
        self.select_pack_btn.configure(state="disabled")

        def progress_cb(c, t, m):
            if t > 0:
                pct = c / t
                ui_call(self.root, lambda p=pct: self.progress_bar.set(p))
                ui_call(self.root, lambda m=m, c=c, t=t: self.progress_label.configure(
                    text=f"{m} ({c}/{t})"))
            # 只处理重绘空闲任务：原来用 update() 会连带处理用户事件，
            # 拖拽窗口大小时每个进度回调都会重入一次完整事件循环，明显卡顿
            ui_call(self.root, lambda: self.root.update_idletasks())

        def worker():
            try:
                stats = LegacyDatabaseMigrator.migrate_legacy_to_new(
                    legacy_path, dst, self.log_manager,
                    conflict_mode='rename',
                    progress_callback=progress_cb,
                    after_migrate=after_mode)
                ui_call(self.root, self._on_migrate_finished, stats, after_mode)
            except Exception as e:
                self.log_manager.log(f"适配旧库出错: {e}", 'ERROR')
                ui_call(self.root, self._on_migrate_finished,
                                {'migrated': 0, 'renamed': 0, 'skipped': 0,
                                 'errors': [str(e)], 'disposed': 'none'},
                                after_mode)

        threading.Thread(target=worker, daemon=True).start()

    def _on_migrate_finished(self, stats: dict, after_mode: str):
        self.progress_bar.pack_forget()
        self.progress_label.pack_forget()
        self._disable_buttons(False)
        self.select_pack_btn.configure(state="normal")
        if self.current_pack_path:
            self.open_pack_btn.configure(state="normal")
            self.open_tacz_btn.configure(state="normal")

        disposed = stats.get('disposed', 'none')
        disposed_text = {
            'marked': "原库已标记为「已迁移」，下次不再提示",
            'recycled': "原库已移入回收站，可随时恢复",
            'deleted': "原库已删除（无法移入回收站）",
            'none': "原库保持原样",
        }.get(disposed, "原库保持原样")

        if stats['errors']:
            self.log_manager.log(
                f"适配完成，但有 {len(stats['errors'])} 个错误", 'WARNING')
            err_text = "\n".join(stats['errors'][:10])
            if len(stats['errors']) > 10:
                err_text += f"\n... 还有 {len(stats['errors'])-10} 个"
            show_warning("部分失败",
                f"旧版数据库适配完成，部分预设失败:\n\n{err_text}")
        else:
            self.log_manager.log(
                f"旧版数据库适配完成: 迁移 {stats['migrated']}, "
                f"重命名 {stats['renamed']}, 跳过 {stats['skipped']}",
                'SUCCESS')
            show_info("完成",
                f"旧版数据库适配完成。\n\n"
                f"迁移预设: {stats['migrated']}\n"
                f"重命名: {stats['renamed']}\n"
                f"跳过: {stats['skipped']}\n\n"
                f"{disposed_text}")

        self.refresh_presets()
        self._update_guide()

    def _ask_after_migrate(self) -> str | None:
        dlg_w = DLG_CHOICE[0]
        card = make_card(get_overlay_host(), self.root, width=dlg_w,
                          escape_value=None, title="迁移后处理")
        frame = card.body

        make_label(frame, text="迁移完成后，如何处理旧版数据库？",
                    fg=C_TEXT_MAIN, font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, pady=(0, PAD_INNER))
        desc = make_label(frame,
            text="建议选择「标记为已迁移」，保留原库作为备份。",
            fg=C_TEXT_SECONDARY, font_size=FS_SMALL)
        desc.configure(wraplength=dlg_w - 2 * PAD_DIALOG, justify=LEFT, anchor=W)
        desc.pack(anchor=W, fill=X, pady=(0, PAD_GAP))

        mode_var = StringVar(value=self.last_after_migrate_mode)
        for text, val, tip in [
            ("标记为已迁移（推荐）", "mark",
             "  在旧库写入标记文件，下次不再提示，原数据保留"),
            ("移入回收站", "delete",
             "  迁移成功后把旧库整目录移入回收站，可随时恢复"),
            ("保留原库（不标记）", "keep",
             "  不做任何处理，下次启动仍会提示适配"),
        ]:
            radio = ctk.CTkRadioButton(frame, text=text, variable=mode_var, value=val,
                                        text_color=C_TEXT_MAIN,
                                        font=(FONT_FAMILY, FS_SMALL),
                                        fg_color=C_ACCENT,
                                        hover_color=C_ACCENT_HOVER,
                                        border_color=C_BORDER)
            radio.pack(anchor=W, pady=(PAD_MICRO, 0))
            card.register_focusable(radio)
            make_label(frame, text=tip, fg=C_TEXT_MUTED, font_size=FS_TINY).pack(
                anchor=W, padx=PAD_INDENT, pady=(0, PAD_XS))

        def on_ok():
            self.last_after_migrate_mode = mode_var.get()
            card.close(mode_var.get())

        def on_cancel():
            card.close(None)

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill=X, side=BOTTOM, pady=(PAD_GAP, 0))
        ok_btn = make_button(btn_frame, "确定", command=on_ok, accent=True)
        ok_btn.pack(side=RIGHT, padx=PAD_XS)
        cancel_btn = make_button(btn_frame, "取消", command=on_cancel)
        cancel_btn.pack(side=RIGHT)
        card.register_focusable(ok_btn)
        card.register_focusable(cancel_btn)
        return card.wait()

    def _ask_conflict_mode(self, message: str) -> str | None:
        dlg_w = DLG_CHOICE[0]
        card = make_card(get_overlay_host(), self.root, width=dlg_w,
                          escape_value=None, title="冲突处理")
        frame = card.body
        lbl = make_label(frame, text=message, fg=C_TEXT_MAIN, font_size=FS_BODY)
        lbl.configure(wraplength=dlg_w - 2 * PAD_DIALOG, justify=LEFT, anchor=W)
        lbl.pack(anchor=W, fill=X, pady=(0, PAD_GAP))

        mode_var = StringVar(value="rename")
        for text, val in [
            ("重命名冲突预设（推荐，不丢数据）", "rename"),
            ("跳过冲突预设（保留现有）", "skip"),
            ("覆盖冲突预设（危险，会删除现有）", "overwrite"),
        ]:
            radio = ctk.CTkRadioButton(frame, text=text, variable=mode_var, value=val,
                                        text_color=C_TEXT_MAIN,
                                        font=(FONT_FAMILY, FS_SMALL),
                                        fg_color=C_ACCENT,
                                        hover_color=C_ACCENT_HOVER,
                                        border_color=C_BORDER)
            radio.pack(anchor=W, pady=PAD_MICRO)
            card.register_focusable(radio)

        def on_ok():
            card.close(mode_var.get())

        def on_cancel():
            card.close(None)

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill=X, side=BOTTOM, pady=(PAD_GAP, 0))
        ok_btn = make_button(btn_frame, "确定", command=on_ok, accent=True)
        ok_btn.pack(side=RIGHT, padx=PAD_XS)
        cancel_btn = make_button(btn_frame, "取消", command=on_cancel)
        cancel_btn.pack(side=RIGHT)
        card.register_focusable(ok_btn)
        card.register_focusable(cancel_btn)
        return card.wait()

    def force_update_validation(self):
        if not self.preset_manager:
            show_warning("提示", "请先加载整合包")
            return
        if not self.current_selected_preset:
            show_warning("提示", "请先选择一个预设")
            return
        if not ask_yes_no("危险操作警告",
            "强制更新校验数据是危险操作！\n\n"
            "确定要继续吗？", icon='warning'):
            return
        name = self.current_selected_preset
        info = self.preset_manager.presets.get(name)
        if not info:
            return
        from_tacz = info.get('applied', False)
        if self.preset_manager.update_preset_index(name, from_tacz=from_tacz):
            self.refresh_gunpacks(use_cache=False)
            self.log_manager.log(f"已强制更新预设 '{name}' 的校验数据", 'WARNING')
            show_info("完成", f"预设 '{name}' 的校验数据已强制更新。")
        else:
            show_error("错误", "强制更新失败，请查看日志")

    # ==================== 身份提示 ====================
    def _show_role_dialog(self, title, message) -> str:
        dlg_w = DLG_CHOICE[0]
        card = make_card(get_overlay_host(), self.root, width=dlg_w,
                          escape_value='ok', title=title)
        frame = card.body
        msg_label = make_label(frame, text=message, fg=C_TEXT_MAIN, font_size=FS_BODY)
        msg_label.configure(wraplength=dlg_w - 2 * PAD_DIALOG, justify=LEFT, anchor=W)
        msg_label.pack(anchor=W, fill=X, pady=(0, PAD_GAP))

        dont_remind_var = BooleanVar(value=False)
        check = ctk.CTkCheckBox(frame, text="本次启动不再提醒",
                                variable=dont_remind_var,
                                text_color=C_TEXT_MAIN, font=(FONT_FAMILY, FS_SMALL),
                                fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER,
                                border_color=C_BORDER)
        check.pack(anchor=W, pady=(PAD_XS, PAD_GAP))
        card.register_focusable(check)

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill=X, side=BOTTOM, pady=(PAD_GAP, 0))

        def on_ok():
            card.close('ok')

        def on_export():
            card.close('export')

        if self.settings.role == "developer":
            export_btn = make_button(btn_frame, "导出增量更新", command=on_export,
                                      accent=True)
            export_btn.pack(side=RIGHT, padx=PAD_XS)
            card.register_focusable(export_btn)
        ok_btn = make_button(btn_frame, "确定", command=on_ok)
        ok_btn.pack(side=RIGHT)
        card.register_focusable(ok_btn)
        result = card.wait()
        # 关键：不管用户是点「确定」、按 ESC、还是点窗口的 ✕ 关掉，
        # 只要勾了「本次启动不再提醒」就得生效 —— 之前只在 on_ok 里读，
        # 用 ESC/✕ 关掉就白勾了。
        try:
            if dont_remind_var.get():
                self.dont_remind_this_session = True
        except Exception:
            pass
        return result

    def _check_applied_changes(self, preset_name):
        try:
            if not self.preset_manager.has_changes(preset_name):
                return
            changes = self.preset_manager.detect_changes(preset_name)
            self.log_manager.log(f"检测到已应用预设 '{preset_name}' 有未同步的变更:", 'WARNING')
            if changes['added']:
                self.log_manager.log(f"  新增: {', '.join(changes['added'][:5])}"
                                      + (" ..." if len(changes['added']) > 5 else ""), 'INFO')
            if changes['removed']:
                self.log_manager.log(f"  移除: {', '.join(changes['removed'][:5])}"
                                      + (" ..." if len(changes['removed']) > 5 else ""), 'ERROR')
            if changes['modified']:
                self.log_manager.log(f"  修改: {', '.join(changes['modified'][:5])}"
                                      + (" ..." if len(changes['modified']) > 5 else ""), 'PROCESS')
            if self.dont_remind_this_session:
                return
            if self.settings.role == "developer":
                msg = (f"检测到已应用预设 '{preset_name}' 有以下变更:\n\n"
                       f"  • 新增: {len(changes['added'])} 个\n"
                       f"  • 移除: {len(changes['removed'])} 个\n"
                       f"  • 修改: {len(changes['modified'])} 个\n\n"
                       f"作为开发者，建议您立即导出增量更新以便分享给其他人。\n\n"
                       f"是否立即导出？")
                if self._show_role_dialog("检测到枪包变更", msg) == 'export':
                    self.export_incremental()
            else:
                msg = (f"检测到已应用预设 '{preset_name}' 有以下变更:\n\n"
                       f"  • 新增: {len(changes['added'])} 个\n"
                       f"  • 移除: {len(changes['removed'])} 个\n"
                       f"  • 修改: {len(changes['modified'])} 个\n\n"
                       f"请检查枪包是否符合预期。\n\n"
                       f"如变更非预期，请按照报错条目修改枪包文件。\n"
                       f"如变更符合预期，可忽略此提示。")
                self._show_role_dialog("检测到枪包变更", msg)
        except Exception as e:
            self.log_manager.log(f"检查变更时出错: {e}", 'WARNING')

    # ==================== 最近打开 ====================
    RECENT_H = 118   # 展开后的固定高度（列表 5 行 + 内边距）

    def toggle_recent(self):
        if self.recent_visible:
            self.recent_visible = False
            self.recent_toggle_btn.configure(text="▼ 最近")
            self._animate_recent(1, hide_after=True)
        else:
            self.recent_visible = True
            self.update_recent_list()
            self.recent_toggle_btn.configure(text="▲ 最近")
            self.recent_frame.pack(fill=BOTH, expand=True)
            try:
                self.recent_wrap.place(relx=0.0, rely=1.0, relwidth=1.0,
                                        height=1)
                self.recent_wrap.lift()
            except Exception:
                pass
            self._animate_recent(self.RECENT_H)

    def _animate_recent(self, target, hide_after=False):
        """折叠面板的高度补间：0 -> 118 展开，118 -> 0 收起。"""
        start = float(getattr(self, "_recent_height", 1.0))
        if start == target:
            try:
                self.recent_wrap.configure(height=max(1, int(target)))
            except Exception:
                pass
            if hide_after:
                self.recent_frame.pack_forget()
            return

        def frame(e, raw):
            self._recent_height = lerp(start, float(target), e)
            try:
                # 只改浮层自己的高度：兄弟控件不动，页面不重排
                self.recent_wrap.place_configure(height=max(1, int(self._recent_height)))
            except Exception:
                pass

        def done():
            self._recent_height = float(target)
            try:
                self.recent_wrap.place_configure(height=max(1, int(target)))
            except Exception:
                pass
            if hide_after:
                try:
                    self.recent_frame.pack_forget()
                except Exception:
                    pass
                try:
                    self.recent_wrap.place_forget()   # 完全撤下，不占位
                except Exception:
                    pass

        frame(0.0, 0.0)
        tween(self.recent_wrap, "height", 190, frame, done, easing=ease_out_cubic)

    def update_recent_list(self):
        if not hasattr(self, 'recent_listbox'):
            return
        self.recent_listbox.delete(0, END)
        if not self.recent_manager:
            self.recent_listbox.insert(END, "(数据库未初始化)")
            self.recent_listbox.itemconfig(0, fg=C_TEXT_MUTED)
            return
        for item in self.recent_manager.get_all():
            name = item.get('name', '未知')
            path = item.get('path', '')
            self.recent_listbox.insert(END, f"{name}  ({path})")
        if self.recent_listbox.size() == 0:
            self.recent_listbox.insert(END, "(暂无最近打开)")
            self.recent_listbox.itemconfig(0, fg=C_TEXT_MUTED)

    def on_recent_double_click(self, event):
        sel = self.recent_listbox.curselection()
        if not sel or not self.recent_manager:
            return
        idx = sel[0]
        recent = self.recent_manager.get_all()
        if idx >= len(recent):
            return
        path = recent[idx].get('path', '')
        if not Path(path).exists():
            show_error("错误", f"路径不存在: {path}")
            return
        self.load_pack(Path(path))

    # ==================== 拖放（预设/更新包） ====================
    def on_drop_file(self, event):
        if self.is_applying or self.loading_presets:
            return
        try:
            files = self.root.tk.splitlist(event.data)
        except Exception:
            files = [event.data]
        if not files:
            return
        raw = files[0].strip('"').strip("'")
        if not raw:
            return
        self.handle_import_file(Path(raw))

    def select_import_file(self):
        if self.is_applying or self.loading_presets:
            return
        if not self.preset_manager:
            show_warning("提示", "请先选择整合包")
            return
        p = filedialog.askopenfilename(
            title="选择预设包或增量更新包",
            filetypes=[("Pulses Swap 包", "*.fgcpack *.fgcupdate"),
                       ("完整预设包", "*.fgcpack"),
                       ("增量更新包", "*.fgcupdate"),
                       ("所有文件", "*.*")])
        if p:
            self.handle_import_file(Path(p))

    def handle_import_file(self, file_path: Path):
        if not self.preset_manager:
            show_warning("提示", "请先选择整合包")
            return
        if self.is_applying:
            show_warning("操作进行中", "请等待当前操作完成")
            return
        if not file_path.exists():
            show_error("错误", f"文件不存在: {file_path}")
            return
        suffix = file_path.suffix.lower()
        if suffix == '.fgcupdate':
            self.do_import_incremental(file_path)
        elif suffix == '.fgcpack':
            self.do_import_preset(file_path)
        else:
            try:
                with zipfile.ZipFile(file_path, 'r') as zf:
                    if '_increment.json' in zf.namelist():
                        self.do_import_incremental(file_path)
                    else:
                        self.do_import_preset(file_path)
            except Exception as e:
                show_error("错误", f"无法识别文件: {e}")

    # ==================== 整合包管理 ====================
    def select_pack(self):
        if not self.db_ready:
            show_warning("提示", "数据库未初始化，请重启程序")
            return
        if self.is_applying:
            show_warning("操作进行中", "请等待当前操作完成")
            return
        if self.loading_presets:
            show_info("加载中", "预设列表正在加载，请稍候...")
            return
        folder = filedialog.askdirectory(title="选择整合包根目录")
        if not folder:
            return
        self.load_pack(Path(folder))

    def load_pack(self, pack_path: Path):
        if not self.db_ready:
            show_warning("提示", "数据库未初始化")
            return
        tacz_path = pack_path / 'tacz'
        if not tacz_path.exists() or not tacz_path.is_dir():
            show_error("错误", "未找到tacz文件夹，请选择正确的整合包根目录")
            return

        legacy_dirs = LegacyDatabaseMigrator.find_legacy_databases(pack_path)
        if legacy_dirs:
            if ask_yes_no("检测到旧版数据库",
                f"在整合包中发现旧版数据库:\n{legacy_dirs[0]}\n\n"
                f"是否适配到当前数据库？\n"
                f"（可选择迁移后标记或删除原库）"):
                self.root.after(200, lambda p=legacy_dirs[0]:
                                 self.migrate_legacy_database(p))

        self.current_pack_path = pack_path
        self.tacz_path = tacz_path

        pack_db_path = self.settings.get_db_path(pack_path)
        pack_db_path.mkdir(parents=True, exist_ok=True)

        self.pack_path_label.configure(text=str(pack_path), text_color=C_SUCCESS)
        self.pack_status_label.configure(text="状态: 已加载 ✓", text_color=C_SUCCESS)
        self._update_sidebar_status()
        self.pack_name_label.configure(text="当前预设: 无", text_color=C_ACCENT)
        self.open_pack_btn.configure(state="normal")
        self.open_tacz_btn.configure(state="normal")

        self.preset_manager = PresetManager(pack_db_path, self.log_manager,
                                             tacz_path, pack_name=pack_path.name)
        if self.recent_manager:
            self.recent_manager.add(str(pack_path), pack_path.name)
            if self.recent_visible:
                self.update_recent_list()

        has_presets = any(p.is_dir() for p in pack_db_path.iterdir()
                          if not p.name.startswith('.'))
        if not has_presets:
            self._create_default_preset()

        self._start_watcher()

        self.loading_presets = True
        self._start_loading_dots("加载中")
        self._disable_buttons(True)
        self.preset_listbox.delete(0, END)
        self.preset_listbox.insert(END, "正在加载预设列表，请稍候...")
        self.preset_listbox.itemconfig(0, fg=C_TEXT_MUTED)
        threading.Thread(target=self._load_presets_thread, daemon=True).start()

    def _load_presets_thread(self):
        try:
            self.preset_manager.load_all_presets(use_cache=True)
        except Exception as e:
            safe_print("加载预设线程出错:", traceback.format_exc())
            self.log_manager.log(f"加载预设失败: {e}", 'ERROR')
        finally:
            # 无论成功失败都要回到主线程收尾（否则按钮会一直锁着）
            ui_call(self.root, self._on_presets_loaded)

    def _on_presets_loaded(self):
        # 兜底放在最前面：只要回调跑到，界面就绝不能留在「按钮全禁用」的状态。
        # 之前加载线程一旦出错，_disable_buttons(True) 就再也解不开，
        # 表现就是「所有按钮按下去都没反应」。
        self.loading_presets = False
        self._stop_loading_dots()
        self._disable_buttons(False)
        self._set_pack_dependent_buttons(True)
        try:
            self._on_presets_loaded_body()
        except Exception as exc:
            safe_print("预设加载完成回调出错:", traceback.format_exc())
            self.log_manager.log(f"预设加载完成回调出错: {exc}", 'ERROR')

    def _on_presets_loaded_body(self):
        self._update_preset_list()
        # 单行日志模式下这条就是「加载完成」的主信息（细节条目见完整日志）
        pack_name = (self.current_pack_path.name
                     if self.current_pack_path else "整合包")
        self.log_manager.log(
            f"整合包已就绪: {pack_name} · 预设 {len(self.preset_manager.presets)} 个",
            'SUCCESS')
        if self.preset_manager.current_preset:
            self._check_applied_changes(self.preset_manager.current_preset)
        if self.preset_manager.presets:
            first = None
            for name, info in self.preset_manager.presets.items():
                if info.get('applied', False):
                    first = name
                    break
            if not first:
                first = list(self.preset_manager.presets.keys())[0]
            if first:
                for i in range(self.preset_listbox.size()):
                    if preset_name_of(self.preset_listbox.get(i)) == first:
                        self.preset_listbox.selection_set(i)
                        self.on_preset_selected(None)
                        break
        self._update_guide()

    def _disable_buttons(self, disabled: bool):
        state = "disabled" if disabled else "normal"
        try:
            self.create_preset_btn.configure(state=state)
            self.export_preset_btn.configure(state=state)
            self.export_incremental_btn.configure(state=state)
            self.refresh_preset_btn.configure(state=state)
            self.refresh_gunpack_btn.configure(state=state)
            self.open_tacz_btn.configure(state=state)
            self.save_version_btn.configure(state=state)
            self.apply_btn.configure(state=state)
            self.select_pack_btn.configure(state=state)
            self.open_db_btn.configure(state=state)
        except Exception:
            pass

    def _set_pack_dependent_buttons(self, enabled: bool) -> None:
        """只开关「依赖已加载整合包」的按钮。

        与「选择整合包 / 打开数据库」区分开：后两者任何时候都要可用，
        否则关掉一个包就再也选不了下一个。
        """
        state = "normal" if enabled else "disabled"
        for name in ("open_pack_btn", "close_pack_btn", "open_tacz_btn",
                     "apply_btn", "create_preset_btn", "export_preset_btn",
                     "export_incremental_btn", "refresh_preset_btn",
                     "refresh_gunpack_btn", "save_version_btn"):
            btn = getattr(self, name, None)
            if btn is not None:
                try:
                    btn.configure(state=state)
                except Exception:
                    pass

    # ==================== 加载指示动画 ====================
    def _start_loading_dots(self, prefix="刷新中"):
        """加载文字脉冲：小圆点逐帧增长（关掉动画时自动降级为静态一次到位）。"""
        def frame(e, raw):
            dots = "." * min(3, int(raw * 4))
            try:
                self.loading_label.configure(text=f"{prefix}{dots}")
            except Exception:
                pass

        frame(0.0, 0.0)
        if ANIMATIONS_ENABLED:
            tween(self.loading_label, "dots", 560, frame,
                  on_done=lambda: self._start_loading_dots(prefix),
                  easing=ease_linear)
        else:
            try:
                self.loading_label.configure(text=f"{prefix}…")
            except Exception:
                pass

    def _stop_loading_dots(self):
        cancel_tween(self.loading_label, "dots")
        try:
            self.loading_label.configure(text="")
        except Exception:
            pass

    def _animate_label_color(self, label, start, target, duration=190):
        """文字颜色过渡：状态/标题更新时不做生硬的瞬间换色。"""
        def frame(e, raw):
            try:
                label.configure(text_color=lerp_color(start, target, e))
            except Exception:
                pass

        frame(0.0, 0.0)
        tween(label, "color", duration, frame, easing=ease_out_cubic,
              fps=FPS_COLOR)

    def _create_default_preset(self):
        if not self.preset_manager:
            return
        if "default" in self.preset_manager.presets:
            return
        if self.preset_manager.create_preset("default", "v1.0.0"):
            gunpacks = self.preset_manager._get_gunpacks_from_folder(self.tacz_path)
            self.preset_manager.presets["default"]['gunpacks'] = gunpacks
            self.preset_manager.presets["default"]['applied'] = True
            self.preset_manager.current_preset = "default"
            index_data = {'name': "default", 'version': "v1.0.0",
                          'gunpacks': gunpacks, 'applied': True,
                          'incremental_count': 0}
            dp = Path(self.preset_manager.presets["default"]['path'])
            with open(dp / 'index.json', 'w', encoding='utf-8') as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)
            self.preset_manager.save_cache()
            self.pack_name_label.configure(text="当前预设: default")
            self.log_manager.log("默认预设创建成功", 'SUCCESS')

    def close_pack(self):
        if self.is_applying:
            show_warning("操作进行中", "请等待当前操作完成")
            return
        if self.loading_presets:
            show_info("加载中", "预设列表正在加载，请稍候...")
            return
        self._stop_watcher()
        self.current_pack_path = None
        self.tacz_path = None
        self.preset_manager = None
        self.current_selected_preset = None
        self.pack_path_label.configure(text="未选择", text_color=C_TEXT_SECONDARY)
        self.pack_status_label.configure(text="状态: 未加载", text_color=C_ERROR)
        self.pack_name_label.configure(text="当前预设: 无", text_color=C_ACCENT)
        self.preset_listbox.delete(0, END)
        self.gunpack_listbox.delete(0, END)
        self.preset_name_label.configure(text="预设: 未选择")
        self.preset_version_label.configure(text="版本号: 无")
        self.preset_status_label.configure(text="状态: 未应用")
        self.gunpack_count_label.configure(text="共 0 个枪包")
        self.version_entry.delete(0, END)
        # 关闭后只有「整合包相关」的按钮该灰掉；「选择整合包 / 数据库」必须
        # 保持可用 —— 之前这里调了 _disable_buttons(True) 把包括「选择」在内
        # 的所有按钮全禁掉，之后没有任何地方再解开，关掉一个包就再也选不了
        # 下一个（用户反馈「选择是灰的」）。
        self._disable_buttons(False)
        self._set_pack_dependent_buttons(False)
        self.log_manager.log("已关闭整合包", 'INFO', verbose=True)
        self._update_sidebar_status()
        self._update_guide()

    # ==================== TACZ 监控 ====================
    def _start_watcher(self):
        self._stop_watcher()
        if not HAS_WATCHDOG:
            self.log_manager.log(
                "未安装 watchdog，文件变更检测依赖手动刷新\n"
                "安装方法: pip install watchdog", 'WARNING')
            return
        if not self.tacz_path or not self.tacz_path.exists():
            return
        self.tacz_watcher = TaczWatcher(self.tacz_path,
                                         on_change_callback=self._on_tacz_changed,
                                         log_manager=self.log_manager)
        self.tacz_watcher.start()

    def _stop_watcher(self):
        if self.tacz_watcher:
            try:
                self.tacz_watcher.stop()
            except Exception:
                pass
            self.tacz_watcher = None

    def _on_tacz_changed(self):
        try:
            ui_call(self.root, self._do_tacz_refresh)
        except Exception:
            pass

    def _do_tacz_refresh(self):
        if self.is_applying or self.loading_presets:
            return
        if not self.preset_manager or not self.current_selected_preset:
            return
        info = self.preset_manager.presets.get(self.current_selected_preset)
        if not info or not info.get('applied', False):
            return
        self.refresh_gunpacks(use_cache=False)

    # ==================== 预设管理 ====================
    def _update_sidebar_status(self):
        """侧边栏底部状态卡：镜像 Step1/Step2 的状态，避免侧边栏下半部空着。"""
        try:
            self.sb_pack_label.configure(
                text=(self.current_pack_path.name if self.current_pack_path
                      else "未选择"))
        except Exception:
            pass
        for src, dst in ((self.pack_status_label, self.sb_status_label),
                         (self.pack_name_label, self.sb_preset_label)):
            try:
                dst.configure(text=src.cget("text"),
                              text_color=src.cget("text_color"))
            except Exception:
                pass

    def _update_preset_list(self):
        if not self.preset_manager:
            return
        self.preset_listbox.delete(0, END)
        for name, info in self.preset_manager.presets.items():
            # 「已应用」用文字前缀标注，不用底色 —— 底色是选中态的专属视觉，
            # 两者都用浅绿会出现「两个都被点亮」的错觉（用户截图反馈过）。
            applied = bool(info.get('applied', False))
            self.preset_listbox.insert(
                END, (PRESET_MARK_APPLIED + name) if applied else name)
            if applied:
                idx = self.preset_listbox.size() - 1
                self.preset_listbox.itemconfig(idx, fg=C_SUCCESS)
        if self.preset_manager.current_preset:
            self.pack_name_label.configure(text=f"当前预设: {self.preset_manager.current_preset}")
        else:
            self.pack_name_label.configure(text="当前预设: 无")
        if self.current_selected_preset:
            for i in range(self.preset_listbox.size()):
                if (preset_name_of(self.preset_listbox.get(i))
                        == self.current_selected_preset):
                    self.preset_listbox.selection_set(i)
                    break
        self._update_sidebar_status()

    def refresh_presets(self):
        if not self.preset_manager or self.loading_presets:
            return
        self.loading_presets = True
        self._start_loading_dots("刷新中")
        self._disable_buttons(True)
        threading.Thread(target=self._refresh_presets_thread, daemon=True).start()

    def _refresh_presets_thread(self):
        try:
            self.preset_manager.load_all_presets(use_cache=False)
        except Exception as e:
            self.log_manager.log(f"刷新预设失败: {e}", 'ERROR')
        finally:
            ui_call(self.root, self._on_refresh_presets_done)

    def _on_refresh_presets_done(self):
        # 同上：先解锁，再做其余收尾
        self.loading_presets = False
        self._stop_loading_dots()
        self._disable_buttons(False)
        self._set_pack_dependent_buttons(True)
        try:
            self._update_preset_list()
            self.log_manager.log("预设列表刷新完成", 'INFO', verbose=True)
            self._update_guide()
        except Exception as exc:
            safe_print("预设刷新回调出错:", traceback.format_exc())
            self.log_manager.log(f"预设刷新回调出错: {exc}", 'ERROR')

    def on_preset_selected(self, event):
        if not self.preset_manager or self.loading_presets:
            return
        sel = self.preset_listbox.curselection()
        if not sel:
            return
        name = preset_name_of(self.preset_listbox.get(sel[0]))
        self.current_selected_preset = name
        info = self.preset_manager.presets.get(name)
        if not info:
            return
        self.preset_name_label.configure(text=f"预设: {name}")
        self._animate_label_color(self.preset_name_label, C_TEXT_MUTED, C_ACCENT)
        version = info.get('version', 'v1.0.0')
        self.preset_version_label.configure(text=f"版本号: {version}")
        status = "已应用 ✓" if info.get('applied', False) else "未应用"
        self.preset_status_label.configure(text=f"状态: {status}")
        self._animate_label_color(
            self.preset_status_label, C_TEXT_MUTED,
            C_SUCCESS if info.get('applied') else C_WARNING)
        self.version_entry.delete(0, END)
        self.version_entry.insert(0, version)
        if info.get('applied', False):
            self.apply_btn.configure(state="disabled", text="已应用 ✓")
            self.export_incremental_btn.configure(state="normal")
        else:
            self.apply_btn.configure(state="normal", text="Step 4 · 一键替换")
            self.export_incremental_btn.configure(state="disabled")
        self.export_preset_btn.configure(state="normal")
        self.refresh_gunpacks(use_cache=False)
        self.log_manager.log(f"选择预设: {name}", 'INFO', verbose=True)
        self._update_sidebar_status()
        self._update_guide()

    def show_preset_context_menu(self, event):
        if not self.preset_manager or self.loading_presets:
            return
        idx = self.preset_listbox.nearest(event.y)
        if idx < 0:
            return
        name = preset_name_of(self.preset_listbox.get(idx))
        info = self.preset_manager.presets.get(name)
        if not info:
            return
        self.preset_listbox.selection_clear(0, END)
        self.preset_listbox.selection_set(idx)
        self.on_preset_selected(None)
        menu = Menu(self.root, tearoff=0, bg=C_PANEL_BG, fg=C_TEXT_MAIN,
                    activebackground=C_ACCENT_SOFT, activeforeground=C_ACCENT,
                    font=(FONT_FAMILY, FS_SMALL))
        menu.add_command(label="迁移预设…",
                          command=lambda: self.migrate_preset(name))
        menu.add_separator()
        menu.add_command(label="重命名", command=lambda: self.rename_preset(name))
        menu.add_separator()
        if name != "default":
            if info.get('applied', False):
                menu.add_command(label="删除预设 (已应用，请先切换)", state=DISABLED)
            else:
                menu.add_command(label="删除预设",
                                  command=lambda: self.delete_preset(name))
        menu.post(event.x_root, event.y_root)

    def migrate_preset(self, preset_name: str):
        if not self.preset_manager or self.loading_presets:
            return
        if self.is_applying:
            show_warning("操作进行中", "请等待当前操作完成")
            return

        info = self.preset_manager.presets.get(preset_name)
        if not info:
            return
        if info.get('applied', False):
            show_warning("提示",
                f"预设 '{preset_name}' 当前已应用。\n\n"
                f"请先切换到其他预设，再执行迁移。")
            return

        target_type = self._ask_migrate_target()
        if not target_type:
            return

        if target_type == 'pack':
            folder = filedialog.askdirectory(title="选择目标整合包根目录")
            if not folder:
                return
            target_pack = Path(folder)
            if not (target_pack / 'tacz').exists():
                show_error("错误",
                    "目标文件夹不是有效的整合包（缺少 tacz 文件夹）")
                return
            target_db = self.settings.get_db_path(target_pack)
        else:
            folder = filedialog.askdirectory(title="选择目标数据库文件夹",
                                              initialdir=str(PROGRAM_DIR))
            if not folder:
                return
            target_db = Path(folder)
            if not target_db.exists():
                show_error("错误", f"目标数据库不存在: {target_db}")
                return
            if not DatabaseLocator.is_valid_database(target_db):
                if ask_yes_no("新建数据库",
                    "目标文件夹不是有效数据库，是否初始化为新数据库？"):
                    DatabaseLocator.init_database(target_db)
                else:
                    return

        target_db.mkdir(parents=True, exist_ok=True)

        conflict_mode = 'rename'
        if (target_db / preset_name).exists():
            if not ask_yes_no("预设已存在",
                f"目标数据库中已存在预设 '{preset_name}'。\n\n"
                f"是否覆盖？（原预设会被移入回收站）"):
                return
            conflict_mode = 'overwrite'

        src_path = Path(info['path'])
        target_path = target_db / preset_name

        if not ask_yes_no("确认迁移",
            f"将把预设 '{preset_name}' 迁移到:\n{target_db}\n\n"
            f"源预设会被删除（移入回收站，可找回）。\n\n"
            f"是否继续？"):
            return

        self.progress_bar.pack(fill=X, pady=(0, 4))
        self.progress_label.pack(fill=X, pady=(0, 4))
        self.progress_bar.set(0)
        self.progress_label.configure(text="准备迁移...")
        self._disable_buttons(True)

        def worker():
            try:
                if target_path.exists():
                    if conflict_mode == 'overwrite':
                        self.preset_manager._safe_remove(target_path)
                shutil.copytree(src_path, target_path)

                idx = target_path / 'index.json'
                if idx.exists():
                    with open(idx, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    data['applied'] = False
                    with open(idx, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)

                src_removed = self.preset_manager._safe_remove(src_path)

                ui_call(self.root, self._on_migrate_preset_finished,
                                True, preset_name, target_db, src_removed)
            except Exception as e:
                self.log_manager.log(f"迁移预设失败: {e}", 'ERROR')
                ui_call(self.root, self._on_migrate_preset_finished,
                                False, preset_name, target_db, False)

        threading.Thread(target=worker, daemon=True).start()

    def _ask_migrate_target(self) -> str | None:
        dlg_w = DLG_SMALL[0]
        card = make_card(get_overlay_host(), self.root, width=dlg_w,
                          escape_value=None, title="迁移预设")
        frame = card.body

        make_label(frame, text="迁移预设到：",
                    fg=C_TEXT_MAIN, font_size=FS_SUBHEAD, bold=True).pack(
                        anchor=W, pady=(0, PAD_GAP))

        mode_var = StringVar(value="pack")
        radio_pack = ctk.CTkRadioButton(frame, text="另一个整合包（使用其数据库）",
                                         variable=mode_var, value="pack",
                                         text_color=C_TEXT_MAIN,
                                         font=(FONT_FAMILY, FS_SMALL),
                                         fg_color=C_ACCENT,
                                         hover_color=C_ACCENT_HOVER,
                                         border_color=C_BORDER)
        radio_pack.pack(anchor=W, pady=(PAD_MICRO, 0))
        card.register_focusable(radio_pack)
        make_label(frame, text="  选择整合包根目录，预设会迁移到该整合包的数据库",
                    fg=C_TEXT_MUTED, font_size=FS_TINY).pack(
                        anchor=W, padx=PAD_INDENT, pady=(0, PAD_TIGHT))

        radio_db = ctk.CTkRadioButton(frame, text="另一个数据库（直接选择数据库文件夹）",
                                       variable=mode_var, value="db",
                                       text_color=C_TEXT_MAIN,
                                       font=(FONT_FAMILY, FS_SMALL),
                                       fg_color=C_ACCENT,
                                       hover_color=C_ACCENT_HOVER,
                                       border_color=C_BORDER)
        radio_db.pack(anchor=W, pady=(PAD_MICRO, 0))
        card.register_focusable(radio_db)
        make_label(frame, text="  选择已存在的数据库，或新建一个空数据库",
                    fg=C_TEXT_MUTED, font_size=FS_TINY).pack(
                        anchor=W, padx=PAD_INDENT, pady=(0, PAD_TIGHT))

        def on_ok():
            card.close(mode_var.get())

        def on_cancel():
            card.close(None)

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill=X, side=BOTTOM, pady=(PAD_GAP, 0))
        ok_btn = make_button(btn_frame, "下一步", command=on_ok, accent=True)
        ok_btn.pack(side=RIGHT, padx=PAD_XS)
        cancel_btn = make_button(btn_frame, "取消", command=on_cancel)
        cancel_btn.pack(side=RIGHT)
        card.register_focusable(ok_btn)
        card.register_focusable(cancel_btn)
        return card.wait()

    def _on_migrate_preset_finished(self, success: bool, preset_name: str,
                                     target_db: Path, src_removed: bool):
        self.progress_bar.pack_forget()
        self.progress_label.pack_forget()
        self._disable_buttons(False)
        if self.current_pack_path:
            self.open_pack_btn.configure(state="normal")
            self.open_tacz_btn.configure(state="normal")

        if success:
            self.log_manager.log(
                f"预设 '{preset_name}' 已迁移到: {target_db}", 'SUCCESS')
            if src_removed:
                self.log_manager.log(
                    f"源预设已移入回收站，可随时找回", 'INFO')
            show_info("迁移成功",
                f"预设 '{preset_name}' 已迁移到:\n{target_db}\n\n"
                f"源预设已{'移入回收站' if src_removed else '保留'}。")
            self.refresh_presets()
        else:
            show_error("迁移失败", "预设迁移失败，请查看日志")

    def rename_preset(self, preset_name):
        if not self.preset_manager or self.loading_presets:
            return
        from tkinter import simpledialog
        new_name = simpledialog.askstring("重命名预设",
                                            f"请输入新的预设名称 (当前: {preset_name}):",
                                            initialvalue=preset_name)
        if not new_name or not new_name.strip():
            return
        new_name = new_name.strip()
        if new_name == preset_name:
            return
        if new_name in self.preset_manager.presets:
            show_error("错误", f"预设 '{new_name}' 已存在")
            return
        for char in r'\/:*?"<>|':
            if char in new_name:
                show_error("错误", f"预设名称不能包含非法字符: {char}")
                return
        self.root.config(cursor="watch")
        try:
            if self.preset_manager.rename_preset(preset_name, new_name):
                self._update_preset_list()
                for i in range(self.preset_listbox.size()):
                    if preset_name_of(self.preset_listbox.get(i)) == new_name:
                        self.preset_listbox.selection_set(i)
                        self.on_preset_selected(None)
                        break
                show_info("成功", f"预设已重命名为: {new_name}")
            else:
                show_error("错误", "预设重命名失败")
        finally:
            self.root.config(cursor="")

    def delete_preset(self, preset_name):
        if not self.preset_manager or self.loading_presets:
            return
        if preset_name == "default":
            show_warning("提示", "不能删除默认预设")
            return
        info = self.preset_manager.presets.get(preset_name)
        if not info:
            return
        if info.get('applied', False):
            show_warning("提示",
                f"预设 '{preset_name}' 已应用，请先切换到其他预设再删除")
            return
        if not ask_yes_no("确认删除",
                f"确定要删除预设 '{preset_name}' 吗？\n\n此操作不可恢复！"):
            return
        try:
            if self.preset_manager.delete_preset(preset_name):
                if self.current_selected_preset == preset_name:
                    self.current_selected_preset = None
                    self.preset_name_label.configure(text="预设: 未选择")
                    self.preset_version_label.configure(text="版本号: 无")
                    self.preset_status_label.configure(text="状态: 未应用")
                    self.version_entry.delete(0, END)
                    self.apply_btn.configure(state="disabled", text="Step 4 · 一键替换")
                    self.export_preset_btn.configure(state="disabled")
                    self.export_incremental_btn.configure(state="disabled")
                    self.gunpack_listbox.delete(0, END)
                    self.gunpack_count_label.configure(text="共 0 个枪包")
                self._update_preset_list()
                show_info("成功", f"预设 '{preset_name}' 已删除")
                self._update_guide()
            else:
                show_error("错误", "删除预设失败")
        except Exception as e:
            show_error("错误", f"删除失败: {e}")

    def create_preset(self):
        if not self.preset_manager or self.loading_presets:
            return
        from tkinter import simpledialog
        name = simpledialog.askstring("创建预设", "请输入预设名称:")
        if not name or not name.strip():
            return
        name = name.strip()
        if name in self.preset_manager.presets:
            show_error("错误", f"预设 '{name}' 已存在")
            return
        version = simpledialog.askstring("版本号", "请输入版本号 (可选，默认 v1.0.0):")
        if version is None:
            return
        version = version.strip() or "v1.0.0"
        if self.preset_manager.create_preset(name, version):
            path = Path(self.preset_manager.presets[name]['path'])
            try:
                os.startfile(str(path))
            except Exception:
                pass
            self._update_preset_list()
            show_info("创建成功",
                f"预设 '{name}' 创建成功！\n\n"
                f"版本号: {version}\n\n"
                f"请在打开的文件夹中放入枪包文件(ZIP和文件夹)\n"
                f"然后点击「刷新」按钮更新索引。")
            self._update_guide()

    def save_version(self):
        if not self.preset_manager or not self.current_selected_preset:
            return
        v = self.version_entry.get().strip() or "v1.0.0"
        if self.preset_manager.update_preset_version(self.current_selected_preset, v):
            self.preset_version_label.configure(text=f"版本号: {v}")
            self.log_manager.log(f"版本号已更新为: {v}", 'SUCCESS')

    # ==================== 导出 ====================
    def export_preset(self):
        if not self.preset_manager or not self.current_selected_preset or self.loading_presets:
            show_warning("提示", "请先选择一个预设")
            return
        if self.is_applying:
            show_warning("操作进行中", "请等待当前操作完成")
            return

        name = self.current_selected_preset
        info = self.preset_manager.presets.get(name)
        if not info:
            return

        if name == "default":
            show_warning("无法导出",
                "不允许导出名为 'default' 的预设。\n\n"
                "请先通过右键菜单「重命名」将该预设改为其他名称，再执行导出。")
            return

        version = info.get('version', 'v1.0.0')
        default_fn = generate_export_filename(name, version, False)
        p = filedialog.asksaveasfilename(
            title="导出完整预设包", initialfile=default_fn,
            defaultextension=".fgcpack",
            filetypes=[("Pulses Swap 完整包", "*.fgcpack")])
        if not p:
            return
        export_path = Path(p)

        self.set_busy_state(True, "导出")
        self.progress_bar.pack(fill=X, pady=(0, 4))
        self.progress_label.pack(fill=X, pady=(0, 4))
        self.progress_bar.set(0)
        self.progress_label.configure(text="准备导出...")

        def worker():
            def cb(c, t, m):
                self.show_progress(c, t, m)
            try:
                ok = self.preset_manager.export_preset(name, export_path, cb)
                ui_call(self.root, self._on_export_finished, ok, export_path)
            except Exception as e:
                self.log_manager.log(f"导出错误: {e}", 'ERROR')
                ui_call(self.root, self._on_export_finished, False, export_path)
        threading.Thread(target=worker, daemon=True).start()

    def export_incremental(self):
        if not self.preset_manager or not self.current_selected_preset or self.loading_presets:
            show_warning("提示", "请先选择一个预设")
            return
        if self.is_applying:
            show_warning("操作进行中", "请等待当前操作完成")
            return
        name = self.current_selected_preset
        info = self.preset_manager.presets.get(name)
        if not info:
            return
        if not info.get('applied', False):
            show_warning("提示", "只能对已应用的预设导出增量更新")
            return
        changes = self.preset_manager.detect_changes(name)
        total = len(changes['added']) + len(changes['removed']) + len(changes['modified'])
        if total == 0:
            show_info("提示", "未检测到任何变更，无需导出")
            return
        if not ask_yes_no("确认导出增量包",
            f"检测到以下变更:\n\n"
            f"新增: {len(changes['added'])} 个\n"
            f"移除: {len(changes['removed'])} 个\n"
            f"修改: {len(changes['modified'])} 个\n\n"
            f"是否导出增量更新包？\n\n"
            f"注意：导出后将自动同步校验数据。"):
            return
        pack_name = self.current_pack_path.name if self.current_pack_path else "Unknown"
        version = info.get('version', 'v1.0.0')
        next_inc = info.get('incremental_count', 0) + 1
        default_fn = generate_export_filename(pack_name, version, True, next_inc)
        p = filedialog.asksaveasfilename(
            title="导出增量更新包", initialfile=default_fn,
            defaultextension=".fgcupdate",
            filetypes=[("Pulses Swap 增量更新包", "*.fgcupdate")])
        if not p:
            return
        export_path = Path(p)
        self.set_busy_state(True, "导出更新")
        self.progress_bar.pack(fill=X, pady=(0, 4))
        self.progress_label.pack(fill=X, pady=(0, 4))
        self.progress_bar.set(0)
        self.progress_label.configure(text="准备导出...")

        def worker():
            def cb(c, t, m):
                self.show_progress(c, t, m)
            try:
                ok = self.preset_manager.export_incremental(name, export_path, cb)
                ui_call(self.root, self._on_export_inc_finished, ok, export_path)
            except Exception as e:
                self.log_manager.log(f"导出增量包错误: {e}", 'ERROR')
                ui_call(self.root, self._on_export_inc_finished, False, export_path)
        threading.Thread(target=worker, daemon=True).start()

    def _on_export_finished(self, success, export_path):
        self.hide_progress()
        self.set_busy_state(False, "")
        if success:
            show_info("导出成功", f"预设已导出到:\n{export_path}")
        else:
            show_error("导出失败", "预设导出失败，请查看日志")
        self._update_preset_list()

    def _on_export_inc_finished(self, success, export_path):
        self.hide_progress()
        self.set_busy_state(False, "")
        if success:
            show_info("导出成功",
                f"增量更新包已导出到:\n{export_path}\n\n"
                f"校验数据已自动同步为最新")
        else:
            show_error("导出失败", "增量包导出失败，请查看日志")
        self._update_preset_list()
        self.refresh_gunpacks(use_cache=False)

    # ==================== 导入 ====================
    def do_import_preset(self, import_path: Path):
        self.set_busy_state(True, "导入")
        self.progress_bar.pack(fill=X, pady=(0, 4))
        self.progress_label.pack(fill=X, pady=(0, 4))
        self.progress_bar.set(0)
        self.progress_label.configure(text="准备导入...")

        def worker():
            def cb(c, t, m):
                self.show_progress(c, t, m)
            try:
                ok = self.preset_manager.import_preset(import_path, cb)
                ui_call(self.root, self._on_import_finished, ok, import_path)
            except Exception as e:
                self.log_manager.log(f"导入错误: {e}", 'ERROR')
                ui_call(self.root, self._on_import_finished, False, import_path)
        threading.Thread(target=worker, daemon=True).start()

    def do_import_incremental(self, import_path: Path):
        self.set_busy_state(True, "导入更新")
        self.progress_bar.pack(fill=X, pady=(0, 4))
        self.progress_label.pack(fill=X, pady=(0, 4))
        self.progress_bar.set(0)
        self.progress_label.configure(text="准备导入...")

        def worker():
            try:
                ok = self.preset_manager.import_incremental(import_path)
                ui_call(self.root, self._on_import_inc_finished, ok, import_path)
            except Exception as e:
                self.log_manager.log(f"导入增量包错误: {e}", 'ERROR')
                ui_call(self.root, self._on_import_inc_finished, False, import_path)
        threading.Thread(target=worker, daemon=True).start()

    def _on_import_finished(self, success, import_path: Path):
        self.hide_progress()
        self.set_busy_state(False, "")
        if not success:
            show_error("导入失败", "预设导入失败，请查看日志")
            return
        self._update_preset_list()
        self.refresh_gunpacks(use_cache=False)
        self._update_guide()
        self._ask_delete_source_package(import_path, "预设导入成功！")

    def _on_import_inc_finished(self, success, import_path: Path):
        self.hide_progress()
        self.set_busy_state(False, "")
        if not success:
            show_error("更新失败", "增量更新失败，请查看日志")
            return
        self.refresh_gunpacks(use_cache=False)
        self._update_preset_list()
        self._update_guide()
        self._ask_delete_source_package(import_path, "增量更新已成功应用！")

    def _ask_delete_source_package(self, import_path: Path, success_msg: str):
        try:
            if not import_path.exists():
                show_info("导入完成", success_msg)
                return
            try:
                size_str = format_size(import_path.stat().st_size)
            except Exception:
                size_str = "未知"
            reply = ask_yes_no(
                "导入完成",
                f"{success_msg}\n\n"
                f"是否删除源压缩包以节省存储空间？\n\n"
                f"文件: {import_path.name}\n"
                f"大小: {size_str}\n"
                f"位置: {import_path.parent}\n\n"
                f"（会移入回收站，可随时找回）")
            if not reply:
                return
            if move_to_recycle_bin(import_path):
                self.log_manager.log(
                    f"已将源压缩包移至回收站: {import_path.name}", 'SUCCESS')
                return
            try:
                import_path.unlink()
                self.log_manager.log(
                    f"已删除源压缩包（无法移入回收站）: {import_path.name}", 'SUCCESS')
            except Exception as e:
                self.log_manager.log(f"删除源压缩包失败: {e}", 'WARNING')
                show_warning("警告",
                    f"删除源压缩包失败，请手动处理。\n\n错误: {e}")
        except Exception as e:
            self.log_manager.log(f"处理源压缩包时出错: {e}", 'WARNING')
            show_info("导入完成", success_msg)

    # ==================== 进度条 ====================
    def show_progress(self, current, total, message=""):
        if total > 0:
            pct = current / total
            ui_call(self.root, lambda: self._animate_progress(pct))
            ui_call(self.root, lambda: self.progress_label.configure(
                text=f"{message} ({current}/{total})"))
        ui_call(self.root, lambda: self.root.update_idletasks())

    def _animate_progress(self, target):
        """进度条曲线推进，避免长任务里一格一格地跳。"""
        start = float(getattr(self, "_progress_value", 0.0))
        if abs(target - start) < 0.0005:
            return

        def frame(e, raw):
            self._progress_value = lerp(start, target, e)
            try:
                self.progress_bar.set(self._progress_value)
            except Exception:
                pass

        frame(0.0, 0.0)
        tween(self.progress_bar, "value", 170, frame, easing=ease_out_cubic)

    def hide_progress(self):
        ui_call(self.root, lambda: self.progress_bar.pack_forget())
        ui_call(self.root, lambda: self.progress_label.pack_forget())
        ui_call(self.root, lambda: setattr(self, "_progress_value", 0.0))
        ui_call(self.root, lambda: self.root.update_idletasks())

    def set_busy_state(self, busy, operation=""):
        if busy:
            self.is_applying = True
            self.apply_btn.configure(state="disabled", text=f"{operation}中...")
            self.export_preset_btn.configure(state="disabled")
            self.export_incremental_btn.configure(state="disabled")
            self.create_preset_btn.configure(state="disabled")
            self.refresh_preset_btn.configure(state="disabled")
            self.refresh_gunpack_btn.configure(state="disabled")
            self.select_pack_btn.configure(state="disabled")
            self.open_pack_btn.configure(state="disabled")
            self.open_tacz_btn.configure(state="disabled")
            self.save_version_btn.configure(state="disabled")
            self.open_db_btn.configure(state="disabled")
            self.close_pack_btn.configure(state="disabled")
            self.preset_listbox.config(state=DISABLED)
        else:
            self.is_applying = False
            self.apply_btn.configure(state="normal", text="Step 4 · 一键替换")
            self.export_preset_btn.configure(state="normal")
            self.create_preset_btn.configure(state="normal")
            self.refresh_preset_btn.configure(state="normal")
            self.refresh_gunpack_btn.configure(state="normal")
            self.select_pack_btn.configure(state="normal")
            self.save_version_btn.configure(state="normal")
            self.open_db_btn.configure(state="normal")
            self.close_pack_btn.configure(state="normal")
            if self.current_pack_path:
                self.open_pack_btn.configure(state="normal")
                self.open_tacz_btn.configure(state="normal")
            self.preset_listbox.config(state=NORMAL)
            if not self.current_selected_preset:
                self.apply_btn.configure(state="disabled")

    # ==================== 枪包列表 ====================
    def refresh_gunpacks(self, use_cache: bool = False):
        if not self.preset_manager or not self.current_selected_preset or self.loading_presets:
            self.gunpack_listbox.delete(0, END)
            self.gunpack_count_label.configure(text="共 0 个枪包")
            return
        preset_name = self.current_selected_preset
        if preset_name not in self.preset_manager.presets:
            self.gunpack_listbox.delete(0, END)
            self.gunpack_count_label.configure(text="共 0 个枪包")
            return

        self.gunpack_listbox.delete(0, END)
        info = self.preset_manager.presets[preset_name]

        current = self.preset_manager.get_current_gunpacks_for_preset(
            preset_name, use_cache=use_cache)
        if use_cache and not current:
            current = self.preset_manager.get_current_gunpacks_for_preset(
                preset_name, use_cache=False)

        if current:
            conv = {}
            for n, v in current.items():
                if isinstance(v, list):
                    conv[n] = {'type': 'zip', 'size': 0, 'file_count': 1}
                else:
                    conv[n] = v
            current = conv

        indexed = info.get('gunpacks', {})
        if indexed:
            conv = {}
            for n, v in indexed.items():
                if isinstance(v, list):
                    conv[n] = {'type': 'zip', 'size': 0, 'file_count': 1}
                else:
                    conv[n] = v
            indexed = conv

        if not current and not indexed:
            self.gunpack_listbox.insert(END, "(此预设暂无枪包)")
            self.gunpack_listbox.itemconfig(0, fg=C_STATUS_EMPTY)
            self.gunpack_count_label.configure(text="共 0 个枪包")
            return

        cur_names = set(current.keys())
        idx_names = set(indexed.keys())
        missing = sorted(idx_names - cur_names)
        extra = sorted(cur_names - idx_names)
        modified = []
        normal = []
        for n in sorted(cur_names & idx_names):
            if not fingerprints_match(current[n], indexed[n]):
                modified.append(n)
            else:
                normal.append(n)

        location = "Tacz文件夹" if info.get('applied', False) else "预设文件夹"
        total = len(missing) + len(extra) + len(modified) + len(normal)

        for name in missing:
            self.gunpack_listbox.insert(END, f"× {name}")
            i = self.gunpack_listbox.size() - 1
            self.gunpack_listbox.itemconfig(i, fg=C_STATUS_MISSING, bg=C_STATUS_MISSING_BG)

        for name in extra:
            self.gunpack_listbox.insert(END, f"⊙ {name}")
            i = self.gunpack_listbox.size() - 1
            self.gunpack_listbox.itemconfig(i, fg=C_STATUS_EXTRA, bg=C_STATUS_EXTRA_BG)

        for name in modified:
            self.gunpack_listbox.insert(END, f"~ {name}")
            i = self.gunpack_listbox.size() - 1
            self.gunpack_listbox.itemconfig(i, fg=C_STATUS_MODIFIED, bg=C_STATUS_MODIFIED_BG)

        for name in normal:
            self.gunpack_listbox.insert(END, f"✓ {name}")
            i = self.gunpack_listbox.size() - 1
            self.gunpack_listbox.itemconfig(i, fg=C_STATUS_NORMAL, bg=C_STATUS_NORMAL_BG)

        if missing or extra or modified:
            self.gunpack_count_label.configure(
                text=f"共 {total} 个枪包 (正常:{len(normal)} "
                     f"缺失:{len(missing)} 多余:{len(extra)} 变更:{len(modified)})")
        else:
            self.gunpack_count_label.configure(
                text=f"共 {total} 个枪包 (来自 {location})")

        if missing or extra or modified:
            lines = [f"预设 '{preset_name}' 校验结果 (从{location}读取):"]
            if normal:
                pv = ', '.join(normal[:5]) + (" ..." if len(normal) > 5 else "")
                lines.append(f"  ✓ 正常: {len(normal)} 个 ({pv})")
            if missing:
                pv = ', '.join(missing[:5]) + (" ..." if len(missing) > 5 else "")
                lines.append(f"  × 缺失: {len(missing)} 个 ({pv})")
            if extra:
                pv = ', '.join(extra[:5]) + (" ..." if len(extra) > 5 else "")
                lines.append(f"  ⊙ 多余: {len(extra)} 个 ({pv})")
            if modified:
                pv = ', '.join(modified[:5]) + (" ..." if len(modified) > 5 else "")
                lines.append(f"  ~ 变更: {len(modified)} 个 ({pv})")
            self.log_manager.log("\n".join(lines), 'WARNING')
        else:
            self.log_manager.log(f"预设 '{preset_name}' 所有枪包校验通过 ✓ (共 {total} 个)", 'SUCCESS')

    # ==================== 预设应用 ====================
    def apply_preset(self):
        if not self.preset_manager or not self.tacz_path or self.loading_presets:
            return
        if self.is_applying:
            show_warning("操作进行中", "请等待当前操作完成")
            return
        if not self.current_selected_preset:
            show_warning("提示", "请先选择一个预设")
            return
        name = self.current_selected_preset
        if name not in self.preset_manager.presets:
            return
        if self.preset_manager.presets[name].get('applied', False):
            show_info("提示", f"预设 '{name}' 已经应用")
            return
        if not ask_yes_no("确认替换",
                f"确定要应用预设 '{name}' 吗？\n\n这将替换Tacz文件夹中的所有枪包！"):
            return

        self._stop_watcher()
        self.set_busy_state(True, "替换")
        self.progress_bar.pack(fill=X, pady=(0, 4))
        self.progress_label.pack(fill=X, pady=(0, 4))
        self.progress_bar.set(0)
        self.progress_label.configure(text="准备替换...")

        def cb(c, t, m):
            self.show_progress(c, t, m)

        def worker():
            try:
                result = self.preset_manager.apply_preset(name, cb)
                ui_call(self.root, self._on_apply_finished, result)
            except Exception as e:
                self.log_manager.log(f"错误: {e}", 'ERROR')
                ui_call(self.root, self._on_apply_finished, False)
        threading.Thread(target=worker, daemon=True).start()

    def _on_apply_finished(self, success):
        self.hide_progress()
        self.set_busy_state(False, "")
        if success:
            self._update_preset_list()
            self.refresh_gunpacks(use_cache=False)
            if self.preset_manager and self.preset_manager.current_preset:
                for i in range(self.preset_listbox.size()):
                    if (preset_name_of(self.preset_listbox.get(i))
                            == self.preset_manager.current_preset):
                        self.preset_listbox.selection_set(i)
                        self.on_preset_selected(None)
                        break
            self.log_manager.log("预设应用成功！", 'SUCCESS')
        else:
            show_error("错误", "预设应用失败，请查看日志")
        self._start_watcher()
        self._update_guide()

    # ==================== 通用功能 ====================
    def toggle_log_mode(self):
        if self.log_manager:
            self.show_full_log = not self.show_full_log
            self.log_manager.set_show_full(self.show_full_log)
            self.log_toggle_btn.configure(
                text="显示单条日志" if self.show_full_log else "显示完整日志")

    def clear_log(self):
        if self.log_manager:
            self.log_manager.clear()

    def refresh_all(self):
        if self.loading_presets:
            show_info("加载中", "预设列表正在加载，请稍候...")
            return
        self.refresh_presets()
        if self.current_selected_preset:
            self.refresh_gunpacks(use_cache=False)
        self.log_manager.log("所有数据已刷新", 'INFO')

    def open_preset_manager(self):
        if not self.preset_manager:
            show_warning("提示", "请先加载整合包")
            return
        try:
            os.startfile(str(self.preset_manager.database_path))
        except Exception as e:
            self.log_manager.log(f"打开文件夹失败: {e}", 'ERROR')

    def show_tutorial(self):
        show_info("使用教程",
            f"{PROJECT_NAME} v{VERSION}\n作者: {AUTHOR}\n\n"
            "【基础使用】\n"
            "Step 1 · 拖入整合包根目录（或整合包内任意文件）\n"
            "Step 2 · 创建预设并放入枪包，或拖入现成 .fgcpack\n"
            "Step 3 · 填写版本号，点保存\n"
            "Step 4 · 选择预设，点「一键替换」切换\n\n"
            "【拖入整合包】\n"
            "可直接拖入整合包根目录，也可拖入整合包内任意文件，\n"
            "程序会自动向上查找 tacz 文件夹。\n\n"
            "【拖入预设包/更新包】\n"
            "拖入 .fgcpack 或 .fgcupdate 即可自动导入。\n"
            "遇到同名预设会询问是否替换。\n\n"
            "【数据库】\n"
            "默认隔离存储：每个整合包独立预设库\n"
            "可在设置切换为合并存储（共用预设）\n\n"
            "【迁移预设】\n"
            "右键预设 → 迁移预设…\n\n"
            "【旧版数据库适配】\n"
            "设置 → 数据库管理 → 适配旧版数据库\n\n"
            "【打开TACZ】\n"
            "枪包列表右上角「打开TACZ」按钮")

    def show_about(self):
        # 「关于」已并入设置页的选项卡，不再弹独立信息框
        self.show_page("settings")
        if self.settings_page is not None:
            self.settings_page.show_about_tab()

    def show_about_detail(self):
        db_str = "未初始化"
        if self.settings._settings_file:
            db_str = str(self.settings._settings_file.parent)
        show_info("关于",
            f"{PROJECT_NAME} v{VERSION}\n\n"
            f"作者: {AUTHOR}\n"
            "描述: Minecraft Tacz 模组枪包快速切换工具\n\n"
            "功能特点:\n"
            "  - 快速切换枪包预设\n"
            "  - 拖入整合包内任意文件自动定位 tacz\n"
            "  - 拖入预设包/更新包自动导入，重名询问\n"
            "  - 默认隔离存储，避免文件重名\n"
            "  - 右键预设可迁移到其他整合包/数据库\n"
            "  - 旧版 FGC v2 数据库适配\n"
            "  - 数据库管理（切换/合并/适配）\n"
            "  - 增量更新（含原始校验数据校验）\n"
            "  - watchdog 实时文件监控\n"
            "  - 枪包列表状态着色\n"
            "  - Windows 原生回收站删除\n"
            "  - 一键打开整合包路径 / TACZ 文件夹\n"
            "  - 新手引导（Step1/2/3/4）\n"
            "  - Win11 透明修复（打包版可用）\n\n"
            f"数据库位置: {db_str}\n"
            f"当前模式: {'合并存储' if self.settings.storage_mode == 'merged' else '隔离存储'}\n\n"
            "UI: Pulses 水墨淡色主题")


# ==================== 程序入口 ====================
def apply_window_icon(window) -> None:
    """设置窗口/任务栏/Alt-Tab 图标。任一方式失败都不影响启动。"""
    # 1) Windows：iconbitmap(default=...) 最稳，同时作用于后续所有 toplevel
    try:
        ico = resource_path("icon.ico")
        if IS_WINDOWS and ico.exists():
            window.iconbitmap(default=str(ico))
    except Exception:
        pass
    # 2) 跨平台：iconphoto。PhotoImage 必须挂在对象上保留引用，
    #    否则被 GC 回收后图标会消失。
    try:
        png = resource_path("icon.png")
        if png.exists():
            img = PhotoImage(file=str(png))
            window.iconphoto(True, img)
            window._pulses_icon_ref = img
    except Exception:
        pass


# Windows 任务栏按钮的图标不取窗口图标，而是取进程 AppUserModelID 对应的图标
# （快捷方式图标 / exe 内嵌图标）。不显式设置时任务栏会退回 Tk 默认羽毛图标。
# 取值与 installer.iss 的 publisher 命名保持一致。
APP_USER_MODEL_ID = "Pulses0Studio.PulsesSwap"


def _apply_opaque_window(hwnd) -> None:
    """把 Win11 窗口设成完全不透明（禁用 Mica / Acrylic 背景材质）。

    关键在 DWMWA_SYSTEMBACKDROP_TYPE(38)：值 0 是「自动」，系统会自己挑
    Mica/Acrylic —— 那就是壁纸透进来的原因；必须显式设成 1(DWMSBT_NONE)。
    """
    if not IS_WINDOWS:
        return
    try:
        none_backdrop = ctypes.c_int(1)      # DWMSBT_NONE
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 38, ctypes.byref(none_backdrop), ctypes.sizeof(none_backdrop))
    except Exception:
        pass
    try:
        # Win11 早期版本用未公开的 DWMWA_MICA_EFFECT(1029)，关掉它兜底
        mica_off = ctypes.c_int(0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 1029, ctypes.byref(mica_off), ctypes.sizeof(mica_off))
    except Exception:
        pass
    try:
        light_titlebar = ctypes.c_int(0)     # 浅色标题栏（与主题一致）
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(light_titlebar),
            ctypes.sizeof(light_titlebar))
    except Exception:
        pass
    try:
        # 33 = DWMWA_WINDOW_CORNER_PREFERENCE：按设计令牌给窗口圆角
        corner = ctypes.c_int(DWM_CORNER_PREF)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner))
    except Exception:
        pass


def _set_app_user_model_id() -> None:
    """设置进程 AppUserModelID。必须在任何 Tk 窗口创建之前调用，否则不生效。"""
    if not IS_WINDOWS:
        # ctypes.windll 只在 Windows 上存在，非 Windows 直接短路，避免 AttributeError
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID)
    except Exception:
        pass


def main():
    # 第一件事：任务栏图标归属必须在任何窗口存在之前定好
    _set_app_user_model_id()
    # 第二件：DPI 感知也要在窗口创建之前声明，否则 Windows 会拉伸位图（字糊）
    detected_scale = enable_dpi_awareness()
    # 第三件：把 Windows 定时器精度提到 1ms，否则补间只有 ~30fps（一卡一卡）
    enable_high_resolution_timer()
    if HAS_DND:
        try:
            root = TkinterDnD.Tk()
            root.configure(bg=C_WINDOW_BG)
        except Exception:
            root = ctk.CTk()
    else:
        root = ctk.CTk()

    # 窗口图标：源码运行取 packaging/，打包运行取 sys._MEIPASS
    apply_window_icon(root)

    # 字体回退链：root 就绪后解析一次，供所有控件工厂使用
    apply_font_fallbacks()
    # 自绘控件（Canvas / grid minsize）要按同一系数放大，别和 CTk 控件错位
    scale = sync_ui_scale(root)
    safe_print(f"DPI 检测: {detected_scale:.2f} · UI 缩放: {scale:.2f}")

    # ==================== Win11 透明修复（第一道） ====================
    try:
        root.attributes('-alpha', 1.0)
    except Exception:
        pass
    try:
        root.wm_attributes('-alpha', 1.0)
    except Exception:
        pass
    try:
        root.attributes('-transparentcolor', '')
    except Exception:
        pass
    try:
        root.configure(fg_color=C_WINDOW_BG)
    except Exception:
        try:
            root.configure(bg=C_WINDOW_BG)
        except Exception:
            pass

    def _disable_dwm(hwnd_root):
        if not IS_WINDOWS:
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(hwnd_root.winfo_id())
            if not hwnd:
                hwnd = hwnd_root.winfo_id()
            _apply_opaque_window(hwnd)
        except Exception:
            pass

    try:
        root.update_idletasks()
        _disable_dwm(root)
    except Exception:
        pass
    # ================================================================

    app = PulsesSwapApp(root)

    try:
        root.after(80, lambda: _disable_dwm(root))
    except Exception:
        pass

    def on_closing():
        # 退出语义与界面内的「退出程序」完全一致（见 request_exit）
        app.request_exit()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()