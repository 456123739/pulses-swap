
"""
Pulses Swap 兼容入口（历史入口，保留给测试与打包配置）。

真正的代码已经拆到两个包里：

    pulses/theme/      调色板 / 字体与回退
    pulses/core/       路径 / 状态 / 线程投递 / 文件工具 / 平台(DPI·回收站)
    pulses/animation/  缓动曲线 / 补间调度
    pulses/widget/     按钮 / 分段控件 / 页面栈 / Toast / 卡片 / 差异清单
    pulses/ui/         窗口 / 主界面 / 设置 / 数据库 / 包管理 / 传输 / 在线

    pulses/config.py   聚合层（主题 + 路径 + 状态）
    pulses/utils.py    聚合层（平台 + 线程 + 文件）
    pulses/dialogs.py  覆盖层对话框 / 消息框 / 数据库定位
    pulses/managers.py 设置 / 日志 / 引导 / 最近 / 监控 / 预设
    pulses/pages.py    设置页
    online/            在线同步（不依赖 tkinter）

注意：这里刻意不用 `from ... import *`，否则可变全局（如 ANIMATIONS_ENABLED）
会被复制成快照。全部走模块级 __getattr__ 动态转发，读到的永远是最新值。
"""
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent))

from pulses import config, utils, animation, widget, dialogs, managers, pages
from pulses.ui import app  # noqa: E402

# 顺序：先找能力最全的层，再往下沉
_LAYERS = (app, pages, managers, dialogs, widget, animation, utils, config)


def __getattr__(name):
    # 可变全局（ANIMATIONS_ENABLED / UI_SCALE / FONT_FAMILY）优先从 config 读，
    # 否则会被各模块 `from .config import *` 留下的快照抢先命中
    if hasattr(config, name):
        return getattr(config, name)
    for layer in _LAYERS:
        if hasattr(layer, name):
            return getattr(layer, name)
    raise AttributeError(f"module 'pulses_swap' has no attribute {name!r}")


def __dir__():
    names = set()
    for layer in _LAYERS:
        names.update(n for n in dir(layer) if not n.startswith("_"))
    return sorted(names)


def main():
    return app.main()


if __name__ == "__main__":
    main()
