"""Pulses Swap 3.x WebView 入口（旧 src/pulses_swap.py 保留为 2.x 回滚入口）。"""
from __future__ import annotations

import sys
from pathlib import Path

# 源码运行：让 pulses、online 都可导入
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pulses_web.main import main

if __name__ == "__main__":
    main()
