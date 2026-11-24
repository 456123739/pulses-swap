# 存档 · WebView 线（archive/webui）

> 这是 **Pulses Swap 新界面（PyWebView + React）** 这条线的存档目录。
> 旧界面（Python / CustomTkinter）那条线用 `archive/python-ui/`，两边不共用清单和 Release。

小文件进 git（文档、清单、脚本、小截图），大文件挂 Release（会话原文、大素材），
git 里只留 `sha256` 和拉取脚本，既不撑大历史，换机器也能一键取回。

## 目录

```
archive/webui/
├── manifest.json                     清单（schema 2：items + releases + 隔离规则）
├── tools/fetch_archive.py            下载 / 校验 / 解包（--list / --check / --id / --dest）
└── history/2026-11/
    ├── RESUME.md                     交接：分支 / 架构 / 命令 / 坑位 / 文档债
    ├── USER_PROMPTS.md               原会话 384 条用户需求（已脱敏）
    ├── ASSISTANT_TIMELINE.md         助手阶段总结与发布记录
    ├── easier-STATUS.md              Pulses Easier 新界面现状核对
    └── easier-shots/*.png            Easier 界面截图（6 态 + 真机 e2e）
```

大会话挂在 Release `archive-webui-2026-11`，不在 git 里：

- `session-5a5350c1.sanitized.jsonl.zst`（10.6 MB）—— 2026-10-07..11-07 的新界面 3.0.x→3.2.0 开发会话
- `session-5cfbc263.sanitized.jsonl.zst`（2.6 MB）—— 2026-11-16..11-24 的 3.3.x 业务修复会话

## 取用

```bash
python archive/webui/tools/fetch_archive.py --list      # 看清单
python archive/webui/tools/fetch_archive.py             # 下载缺的并校验
python archive/webui/tools/fetch_archive.py --unpack    # 校验后解压成 .jsonl
python archive/webui/tools/fetch_archive.py --check     # 只校验本地已有文件
```

公开 Release 不需要凭证；改成草稿/私有后设置 `GITHUB_TOKEN` 即可。

## 隔离规则（两条线并行开发）

| 线 | 分支 / 工作树 | 存档目录 | Release |
|---|---|---|---|
| 新界面（WebView） | `release/webui-3.2` · `/home/admin/111/pulses-swap-web` | `archive/webui/**` | `archive-webui-2026-11` |
| 旧界面（Python/CTk） | `fix/ctk-2.8.x` · `/home/admin/111/pulses-swap-ctk`（及主目录的 `release/ctk-2.8.0`） | `archive/python-ui/**` | 由那条线自己维护 |

- 各自只改自己的目录与 release，**不要动对方的 manifest**；
- 共享仓库根下的 `README.md`、`.gitignore` 改动尽量小，冲突时以本文档为准重排；
- 合并分支时，`archive/` 下按子目录各自保留，不合并清单。

## 脱敏

上传前已把下面这些替换成 `REDACTED`：GitHub token（`gho_*`/`ghp_*`/`github_pat_*`）、
URL 里的 `x-access-token:*`、蓝奏账号手机号、账号密码明文、JSON 里的 `password` 字段。
**不要把未脱敏的原始日志传上来。**
