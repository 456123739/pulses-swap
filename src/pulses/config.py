"""
公共配置层（聚合）

真正的实现在下面几处，这里统一再导出，保持 `config.X` 的调用方式不变：
    theme/palette.py     颜色 / 形状 / 尺寸令牌
    theme/typography.py  字体令牌与回退
    core/paths.py        版本 / 路径 / 资源定位
    core/state.py        运行时可变状态（UI_SCALE / ANIMATIONS_ENABLED）
"""
from __future__ import annotations

from .theme.palette import *          # noqa: F401,F403
from .theme.typography import *       # noqa: F401,F403
from .core.paths import *             # noqa: F401,F403
from .core.state import *             # noqa: F401,F403
from .theme import palette, typography  # noqa: F401
from .core import paths, state          # noqa: F401

# 主题令牌里定义了 FONT_FAMILY 等可变项，读的时候走子模块，避免快照
from .theme.typography import FONT_FAMILY  # noqa: F401
