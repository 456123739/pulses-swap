#!/usr/bin/env python3
"""把 DSH 会话 JSONL 脱敏，供 archive/ 归档使用。

为什么要单独一个脚本：会话原文里会出现 token、云盘账号密码、URL 凭证。
`archive/` 的内容会进公开仓库（Release 资产 + git 文档），所以上传前必须过一遍。

用法：
    python archive/tools/sanitize_session.py 原始.jsonl 输出.jsonl
    python archive/tools/sanitize_session.py 原始.jsonl 输出.jsonl --report

规则（命中即替换为 REDACTED，脚本不会打印任何原始密钥）：
    token          gho_/ghp_/ghu_/ghs_/ghr_ 与 github_pat_ 令牌
    url-token      https://x-access-token:XXX@github.com 里的 XXX
    json-field     JSON 里的 password / passwd / pwd / secret / token / api_key
    lanzou-account 「账号18612345678」里的手机号
    cn-password    「密码abc123」里的密码

第二条通道：从 `密码xxx` 里抽出来的明文会在整份文件里再全局替换一遍
（同一个密码常在后面对话里单独出现），所以输出是幂等的、可重复跑。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

REDACTED = "REDACTED"

# 每条规则：(名字, 正则, 替换)。用函数替换，避免 re.sub 里反斜杠转义踩坑。
RULES: list[tuple[str, str]] = [
    ("token", r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    ("url-token", r"(?<=x-access-token:)[^@\s\"']+"),
    ("json-field", r"\"(?:password|passwd|pwd|secret|token|api_key|apikey)\"\s*:\s*\"[^\"]*\""),
    ("lanzou-account", r"(?<=账号)1[3-9]\d{9}"),
    ("cn-password", r"(?<=密码)[A-Za-z0-9_@#!$%^&*+=.~-]{3,}"),
]

# 从这些规则里抽出的明文，会在全文件范围内再替换一次。
PROPAGATE = {"lanzou-account", "cn-password"}


def compile_rules() -> list[tuple[str, re.Pattern[str]]]:
    return [(name, re.compile(pattern)) for name, pattern in RULES]


def sanitize_text(text: str, rules, extra: list[str] | None = None) -> tuple[str, Counter]:
    """对一段文本套用全部规则，返回 (脱敏后文本, 命中计数)。"""
    counts: Counter = Counter()
    for secret in extra or []:                      # 先替换已知密码，避免被后续规则打断
        if secret and secret in text:
            counts["propagated"] += text.count(secret)
            text = text.replace(secret, REDACTED)
    for name, pattern in rules:
        def _sub(m: re.Match[str], name: str = name) -> str:
            counts[name] += 1
            if name == "json-field":
                key = m.group(0).split(":", 1)[0]
                return f"{key}: \"{REDACTED}\""
            return REDACTED
        text = pattern.sub(_sub, text)
    return text, counts


def collect_secrets(text: str, rules) -> list[str]:
    """把「密码xxx」这类明文收集起来，供全文替换。

    两道保险，避免把 JSON 标点（`","`、`\\\\`）当成密码全文替换掉：
    候选必须含字母或数字、长度 >= 5、且在文中出现次数不超过 2000。
    """
    found: set[str] = set()
    for name, pattern in rules:
        if name not in PROPAGATE:
            continue
        for m in pattern.finditer(text):
            value = m.group(0)
            if not value or value == REDACTED:
                continue
            if len(value) < 5 or not re.search(r"[A-Za-z0-9]", value):
                continue
            if text.count(value) > 2000:
                continue
            found.add(value)
    return sorted(found, key=len, reverse=True)


def sanitize_file(source: Path, target: Path, *, report: bool = False) -> Counter:
    rules = compile_rules()
    with source.open("r", encoding="utf-8", errors="replace") as src:
        secrets = collect_secrets(src.read(), rules)   # 第一遍：收集明文密码

    total: Counter = Counter()
    with source.open("r", encoding="utf-8", errors="replace") as src, \
            target.open("w", encoding="utf-8") as dst:
        for line in src:
            cleaned, counts = sanitize_text(line, rules, secrets)
            total.update(counts)
            dst.write(cleaned)

    if report:
        for name in ("token", "url-token", "json-field", "lanzou-account",
                     "cn-password", "propagated"):
            if total.get(name):
                print(f"  {name:16s} {total[name]}")
        print(f"  共替换 {sum(total.values())} 处 -> {target}")
    return total


def iter_records(path: Path):
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def summarize(path: Path) -> dict:
    """给 manifest 用的统计：行数、消息数、时间跨度（毫秒时间戳转天）。"""
    records = list(iter_records(path))
    kinds = Counter(r.get("type", "") for r in records)
    times = [r["createdAt"] for r in records if r.get("type") == "session"]
    return {
        "lines": len(records),
        "messages": kinds.get("user/message", 0) + kinds.get("assistant/message", 0),
        "turns": kinds.get("turn/start", 0),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="DSH 会话 JSONL 脱敏")
    ap.add_argument("source", type=Path)
    ap.add_argument("target", type=Path)
    ap.add_argument("--report", action="store_true", help="打印命中统计（不含原文）")
    args = ap.parse_args(argv)

    if not args.source.exists():
        raise SystemExit(f"找不到 {args.source}")
    args.target.parent.mkdir(parents=True, exist_ok=True)
    sanitize_file(args.source, args.target, report=args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
