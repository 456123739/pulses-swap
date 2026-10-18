
"""
Pulses Swap 兼容入口（历史入口，保留给测试与打包配置）。

真正的代码已经拆到 pulses/ 包里：
    pulses/config.py     主题常量 / 路径 / 字体尺寸令牌 / 运行时可变状态
    pulses/utils.py      回收站 / 线程投递 / DPI / 小工具
    pulses/animation.py  补间动画引擎
    pulses/widgets.py    自绘控件与控件工厂
    pulses/dialogs.py    覆盖层对话框 / 消息框 / 数据库定位
    pulses/managers.py   设置 / 日志 / 引导 / 最近 / 监控 / 预设
    pulses/pages.py      设置页
    pulses/app.py        主窗口与 main()

注意：这里刻意不用 `from ... import *`，否则可变全局（如 ANIMATIONS_ENABLED）
会被复制成快照。全部走模块级 __getattr__ 动态转发，读到的永远是最新值。
"""
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent))

from pulses import config, utils, animation, widget, dialogs, managers, pages, app  # noqa: E402

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
