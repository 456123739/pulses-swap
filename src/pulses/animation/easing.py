"""缓动曲线与颜色插值。"""
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
