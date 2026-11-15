# 会话存档（archive）

这里放**不适合进 git 大文件**、但以后还要复用的工作存档：会话记录、交接文档、界面截图。

- 代码与文档进 git；
- 大文件（压缩后的会话）挂 **Release 资产**，git 里只留清单和拉取脚本，避免仓库膨胀。

## 目录

```
archive/
├── manifest.json                     版本 / 文件 / sha256 / 脱敏说明
├── tools/fetch_archive.py            下载 + 校验 + 解压
└── history/2026-11/
    ├── RESUME.md                     Pulses Swap 新界面交接（分支/架构/命令/坑位/文档债）
    ├── USER_PROMPTS.md               原会话 384 条用户需求（已脱敏）
    ├── ASSISTANT_TIMELINE.md         助手阶段总结与发布记录
    ├── easier-STATUS.md              Pulses Easier 新界面现状核对
    ├── easier-shots/*.png            Easier 界面截图（6 态 + 真机 e2e）
    └── (session-*.zst 不在这里)      见 Release 资产
```

## 取用

```bash
python archive/tools/fetch_archive.py          # 下载到 archive/cache/ 并校验 sha256
python archive/tools/fetch_archive.py --unpack # 校验后解压成 .jsonl
python archive/tools/fetch_archive.py --check  # 只校验本地已有文件
```

公开 release 不需要凭证；如果存档被改成草稿/私有，设置 `GITHUB_TOKEN` 即可。

## 存的是什么

`session-5a5350c1`（【新UI】Pulses Swap 分支，6025 条消息，2026-10-07 → 11-07），
是 3.0.x → 3.1.9 的全部开发过程。原会话因上下文超限（2.03M tokens）终止，
这里存的是 JSONL 事件流的 zstd 压缩包，可用 `zstd -d` 或上面的脚本解开。

格式说明：一行一个事件（DSH session v4），主要类型 `user/message`、`assistant/message`、
`tool/call`、`tool/result`、`turn/start`、`turn/end`。用 `grep`/`jq` 就能查某次改动。

## 脱敏

上传前已经把这些替换成 `REDACTED`：GitHub token（`gho_*` / `ghp_*` / `github_pat_*`）、
URL 里的 `x-access-token:*`、蓝奏账号手机号、账号密码、JSON 里的 `password` 字段。
**不要**把未脱敏的原始日志再传上来。

## 版本管理

- 每批存档一个目录（`history/YYYY-MM/`）+ manifest 条目；
- 大文件挂到同名 release（如 `archive-2026-11`），**不要**直接 commit；
- 新增/替换资产时同步更新 `manifest.json` 的 `sha256` 和 `size`。
