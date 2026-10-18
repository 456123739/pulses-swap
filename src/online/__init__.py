"""
Pulses Swap 在线枪包体系。

分层：

    errors      统一异常（带 hint / retryable）
    acw         蓝奏人机校验的纯 Python 解法
    hashing     本地扫描、树摘要、哈希缓存
    manifest    manifest 规范化 / 读写 / 版本比较
    packing     确定性打包、安全解包
    diff        两方比对 → Plan
    provider_lanzou          匿名分享（玩家侧）
    provider_lanzou_account  账号操作（开发者侧）
    downloader  下载到暂存并校验
    updater     暂存 → 正式目录（原子替换 + 崩溃恢复）
    trash       送进系统回收站
    paths       状态目录
    service     门面：check / sync

这个包**不依赖 tkinter**，可以直接在命令行和测试里用。
"""
from __future__ import annotations

from .errors import (AuthError, CancelledError, CaptchaError, DiskSpaceError,
                     IntegrityError, ManifestError, NetworkError, OnlineError,
                     PackError, SourceError, UnsupportedError)
from .manifest import (SCHEMA, empty_manifest, index_by_path, is_newer, load,
                       normalize, save, total_size, version_tuple)
from .service import OnlineService, PresetRef, SourceStore, SyncResult

__all__ = [
    "OnlineError", "NetworkError", "AuthError", "SourceError", "CaptchaError",
    "IntegrityError", "DiskSpaceError", "ManifestError", "PackError",
    "CancelledError", "UnsupportedError",
    "SCHEMA", "empty_manifest", "index_by_path", "is_newer", "load",
    "normalize", "save", "total_size", "version_tuple",
    "OnlineService", "PresetRef", "SourceStore", "SyncResult",
]
