# 存档与资源（archive）

这里管的是**代码之外、但以后还要用**的东西：几条会话的完整记录、逐轮界面截图、
前端依赖包。它们体积大、几乎不 diff，塞进 git 只会把仓库撑大，所以：

| 放哪 | 放什么 | 为什么 |
|---|---|---|
| **git** | 文档、清单、脚本、小截图（< 5 MB/张） | 要跟代码同版本、要能看 diff |
| **Release 资产** | 会话原文（压缩）、依赖包、大截图集 | 二进制，一次上传、按 sha256 校验取回 |
| **不归档** | TACZ 模组、Chrome for Testing、PCL2 启动器 | 第三方版权 + 随时能重新下载 |

清单在 [`manifest.json`](manifest.json)：每条资源的大小、sha256、来源、取用方式都在里面。

## 目录

```text
archive/
├── manifest.json                  清单（schema 2：items / in_git / purged）
├── README.md                      本文件
├── tools/
│   ├── fetch_archive.py           下载 + 校验 + 解包
│   ├── sanitize_session.py        会话 JSONL 脱敏（上传前必跑）
│   └── publish_asset.py           上传新资产（REST + 断点重试 + digest 校验）
├── cache/                         下载落地目录（已 gitignore）
└── history/2026-11/
    ├── RESUME.md                  交接说明（分支 / 架构 / 命令 / 坑位 / 文档债）
    ├── USER_PROMPTS.md            384 条用户需求原文（已脱敏）
    ├── ASSISTANT_TIMELINE.md      助手阶段总结与发布记录
    ├── easier-STATUS.md           Pulses Easier 新界面现状核对
    └── easier-shots/*.png         Easier 界面截图（6 态 + 真机 e2e）
```

## 取用

```bash
python archive/tools/fetch_archive.py --list      # 看清单
python archive/tools/fetch_archive.py             # 下载缺的，全部校验 sha256
python archive/tools/fetch_archive.py --check     # 只校验本地已有文件
python archive/tools/fetch_archive.py --unpack    # 校验后再解包
```

公开 Release 不需要凭证；如果以后把存档改成草稿/私有，`export GITHUB_TOKEN=...` 即可。

**还原前端依赖**（离线/断网时替代 `npm ci`）：

```bash
python archive/tools/fetch_archive.py --id web-node_modules --unpack --dest src/pulses_web/web
```

## 这一批存了什么

| id | 内容 | 体积 | 在哪 |
|---|---|---|---|
| `session-5a5350c1` | 【新UI】Pulses Swap 分支 · 6664 条消息 / 139 轮（3.0.x → 3.1.9） | 10.6 MB | `archive-2026-11` |
| `session-b59b64a4` | 2.x 界面打磨线 · 5422 条消息 / 122 轮（顶栏 / 动画 / 自动保存） | 9.2 MB | `archive-2026-11` |
| `ctk-ui-shots-2026-11` | customtkinter 时期的 92 张界面截图 | 64.4 MB | `archive-2026-11` |
| `web-node_modules` | 前端依赖包（锁 `package-lock.json` @ `5f4c7582`） | 21.8 MB | `bundle-3.2.0` |

两条会话都来自父会话 `session-76da53c0`（2026-10-07 起），各自继承了它的历史事件，
所以清单里的时间跨度写作 `2026-10-29 .. 11-07/11-08`，不是从 10-07 算起。

## 脱敏

`archive/` 会进公开仓库，所以会话原文上传前必须过 `sanitize_session.py`：

```bash
python archive/tools/sanitize_session.py 原始.jsonl 输出.jsonl --report
```

规则：`gho_/ghp_/ghu_/ghs_/ghr_` 与 `github_pat_` 令牌、URL 里的 `x-access-token:XXX`、
JSON 的 `password/passwd/pwd/secret/token/api_key`、「账号186…」里的手机号、
「密码abc123」里的密码；从「密码xxx」抽出来的明文会在全文再替换一次（同一密码常在后文单独出现）。

脚本只打印命中条数，不打印原文；输出幂等，可以重复跑。**不要**把未脱敏的日志传上来。

## 加一批新存档

1. 文档、截图放 `archive/history/YYYY-MM/`；大文件打包（`tar --sort=name ... | zstd -19`，便于复现 hash）；
2. 会话先脱敏再压缩：`sanitize_session.py` → `zstd -19`；
3. 上传：`python archive/tools/publish_asset.py --tag <tag> --file <文件>`（已存在且内容不同要加 `--replace`）；
4. 在 `manifest.json` 的 `items` 里补 `id / size / sha256 / release_tag / unpack`，README 的表格同步加一行；
5. 本地副本确认可校验后再删，删掉的写进 `purged`，注明理由和怎么再造。

版本约定：

- **批次**按年月（`2026-11`），tag 用 `archive-YYYY-MM`；
- **构建环境包**跟版本走（`bundle-3.2.0`），文件名带 `package-lock.json` 的 sha256 前 8 位，lock 变了就重新打；
- 每次更新 `updated_at`，历史条目只增不改——要改内容就换 `id`/文件名，别偷偷覆盖。

## 本批清理记录

`manifest.json` 的 `purged` 里有完整列表（含恢复方式）。摘要：

- 第三方下载：`/tmp/chrome`(261 MB)、`/tmp/pcl2work`(175 MB)、`/tmp/v2prev`(203 MB，旧版本 dist 可重建)；
- 测试素材：`/tmp/chs.zip`(115 MB)、`/tmp/big100.jar`(100 MB)、`/tmp/e2e-pack`(84 MB)、
  `/tmp/tacz_default_gun*.tmp`(238 MB)；
- 会话原文副本：`/tmp/s59.jsonl`、`/tmp/ui_swap_session.jsonl`、`_history/newui-swap/session*.jsonl`，
  压缩脱敏版已在 Release 里，本地不再留。

这些都可以按 `purged[].restore` 的说明重新造出来，所以删了不心疼；
真正的原始资料（会话、截图、交接文档）都在 git 或 Release 里。
