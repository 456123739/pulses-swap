"""
Pulses Swap 启动入口

    python main.py

真正的代码在 pulses/ 包里，按职责分层：
    pulses/config.py     主题常量 / 路径 / 字体与尺寸令牌 / 运行时可变状态
    pulses/utils.py      回收站 / 线程投递 / DPI / 小工具
    pulses/animation.py  补间动画引擎
    pulses/widgets.py    自绘控件与控件工厂
    pulses/dialogs.py    覆盖层对话框 / 消息框 / 数据库定位
    pulses/managers.py   设置 / 日志 / 引导 / 最近 / 监控 / 预设
    pulses/pages.py      设置页
    pulses/app.py        主窗口与 main()
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pulses.app import main  # noqa: E402

if __name__ == "__main__":
    main()
