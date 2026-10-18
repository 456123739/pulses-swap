"""
acw_sc__v2 人机校验的纯 Python 解法。

蓝奏的下载域名（developer*.lanrar.com 等）前面挂了阿里云盾：第一次请求
返回的不是文件，而是一段 JS：

    var arg1='0B9C45EC…';
    (function(a,c){…})(a0i,0x760bf)…

这段 JS 会算出一个值写进 cookie ``acw_sc__v2`` 再刷新页面。
算法是固定的（置换表 + 异或密钥），只是变量名每次随机，
所以这里直接按算法算，不依赖任何变量名。
"""
from __future__ import annotations

import re

# JS 里的置换表，长度与 arg1 一致（40）
_PERMUTATION = [
    0x0F, 0x23, 0x1D, 0x18, 0x21, 0x10, 0x01, 0x26, 0x0A, 0x09,
    0x13, 0x1F, 0x28, 0x1B, 0x16, 0x17, 0x19, 0x0D, 0x06, 0x0B,
    0x27, 0x12, 0x14, 0x08, 0x0E, 0x15, 0x20, 0x1A, 0x02, 0x1E,
    0x07, 0x04, 0x11, 0x05, 0x03, 0x1C, 0x22, 0x25, 0x0C, 0x24,
]
_KEY = "3000176000856006061501533003690027800375"
_ARG1_RE = re.compile(rb"arg1\s*=\s*'([0-9A-Fa-f]{20,64})'")
_COOKIE_NAME = "acw_sc__v2"


def solve(arg1: str) -> str:
    """把页面里的 arg1 算成 acw_sc__v2 的值。"""
    text = str(arg1 or "").strip()
    if len(text) != len(_PERMUTATION):
        raise ValueError(f"arg1 长度异常: {len(text)}")
    slots = [""] * len(_PERMUTATION)
    for index, char in enumerate(text):
        for slot, target in enumerate(_PERMUTATION):
            if target == index + 1:
                slots[slot] = char
    permuted = "".join(slots)
    out = []
    for pos in range(0, min(len(permuted), len(_KEY)), 2):
        try:
            value = int(permuted[pos:pos + 2], 16) ^ int(_KEY[pos:pos + 2], 16)
        except ValueError:
            return ""
        out.append(format(value, "x").zfill(2))
    return "".join(out)


def challenge_arg1(body: bytes) -> str | None:
    """如果响应体是人机校验页，返回其中的 arg1。"""
    if not body or len(body) > 200_000:
        return None
    head = body[:4096]
    if b"acw_sc__v2" not in body and b"arg1" not in head:
        return None
    match = _ARG1_RE.search(body)
    if not match:
        return None
    try:
        return match.group(1).decode("ascii")
    except UnicodeDecodeError:
        return None


def cookie_for(arg1: str) -> str:
    return solve(arg1)


COOKIE_NAME = _COOKIE_NAME
