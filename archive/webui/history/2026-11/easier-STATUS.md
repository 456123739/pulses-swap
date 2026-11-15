# Pulses Easier · 新界面（WebView）现状

> 核对时间：2026-11-08 12:0x（Asia/Shanghai）
> 全部结论都来自当场跑的命令，不是从文档抄的。

## 0. 一句话

新界面（React + pywebview）已经**并进 main 并随 v0.11.2 一起发布**，默认
`ui_mode=auto`（有 WebView2 就走新界面，失败退回 Tk）；今天复跑：**603 个单测全过、
前端构建通过、真前端+真 Api 的端到端全过**。

## 1. 仓库与分支

| 项 | 值 |
|---|---|
| 仓库 | `/home/admin/NS/pulses_easier` |
| 当前分支 | `main` @ `03cbac7`（`release: v0.11.2 源码包`） |
| 远端 | 与 `origin/main` 一致；另有 `ghd/main` 领先一个提交（`d3016a2` 界面：策略行对齐 + 石墨灰） |
| 新 UI 分支 | `feat/ui-web-render` @ `3388637`（0.10.0「新界面首发」）——**已完全包含在 main 里**，尖端比 main 旧 |
| 未提交 | 只有 `?? docs/logo-cover-window.png`（未跟踪截图，非代码） |
| 版本 | `app/core/__init__.py` `__version__ = "0.11.2"`；`web/package.json` 0.1.0（前端包版本，独立于产品版本） |

> 所以「最新版新 UI」= **main 上的 0.11.2**，不是 `feat/ui-web-render` 的尖端。

## 2. 新界面由什么组成

```
app/ui_web/                 2966 行（host / api / events / controller / flow / dev / launch）
  host.py      pywebview 宿主：1440×860，最小 1000×620，DOM 拖放接 Python，http_server=True
  api.py       js_api 三方法（invoke / pick_path / handle_drop），信封 {ok, data|error}
  events.py    EventBus + EventPump（60fps 合批、顺序保留、上限丢弃）
  controller.py 无 UI 控制器：快照/身份/设置/整合包/最近打开/对话框
  flow.py      更新流程无头实现（导入→比对→策略→任务→下载→执行→复核）
  launch.py    受监督启动：子进程 + 就绪文件，25s 未就绪杀掉退回 Tk
               ⚠️ 只有 `python -m app.ui_web.launch` 和测试用到它；main.py 的 auto
               实际是"进程内起新界面 + 异常/非 0 退出退回 Tk"
web/            React 19 + TS + Zustand + framer-motion + Vite（33 个 ts/tsx，约 6.7k 行）
  dist/         431 KB js + 32 KB css（今天重新构建过）
```

启动选择（`main.py`）：`PULSES_UI=web|auto|tk` 覆盖；否则读
`~/.pulses_easier/config.json` 的 `ui_mode`，默认常量
`app/core/database.py: DEFAULT_UI_MODE = "auto"`。
`auto` = 先起新界面，WebView2 缺失或没就绪就继续走 Tk。

## 3. 0.11.x 三个功能（最近一轮的主线）

- **0.11.0**：开发者端从本地实例一键制作更新包（移植 PCL2 导出/探查/index 逻辑）。
- **0.11.1**：整合包占用锁（`msvcrt.locking` / `fcntl.flock`，崩溃自动释放）+ 扫描→更新之间的变更守卫。
- **0.11.2**：更新途中被外部程序改动 → **暂停并让玩家选**（继续以更新包为准 / 重新扫描 / 取消），安全点暂停不留半截文件。

## 4. 今天复跑的验证

| 项 | 结果 |
|---|---|
| `pytest tests -q` | **603 passed in 85.71s** |
| `npm run build`（tsc -b + vite build） | 通过，486 modules，4.57s |
| `scripts/dev/run_ui_e2e.py`（真前端 + 真 Api + 真磁盘） | **全部通过**：主流程 A–H、真下载（含 5MiB 分片）、中止、续传、关闭守卫、开发者导出 `.eapack` 校验 |
| 截图 | `web/scripts/shots.mjs` 出 6 张；另有 e2e 真机截图 |

## 5. 截图证据（本目录 `shots/`）

| 文件 | 内容 |
|---|---|
| `01-main.png` | 主界面：STEP1 定位 / STEP2 更新包 / 更新策略 / 变更内容 / 日志，v0.11.2 |
| `02-download.png` | 下载中：主按钮变「取消下载」、进度条、槽位面板 |
| `03-developer.png` | 开发者端：制作更新包 |
| `04-preferences.png` | 首选项抽屉 |
| `05-whitelist.png` | 白名单抽屉 |
| `06-blocked.png` | 受阻/待补入态 |
| `real-e2e.png` | 真跑一遍更新后的真实界面（真 Api、真磁盘、临时夹具目录） |

> 前 6 张是"真前端产物 + 演示状态注入"（`shots.mjs` 的夹具），版本号已按 0.11.2 核对；
> 最后一张是端到端跑完后的真实状态，路径是临时夹具。

## 6. 未完成（仓库 `docs/UI-重建进度.md` 自己列的）

1. Tk 完整对齐：检查点/中断残留恢复、应用阶段「最低空间」提示、多显示器 DPI。
2. 拖放：DOM 拖放已接，Windows 实机路径未验。
3. 槽位面板：没显示"磁盘策略限制后的有效并发"。
4. 虚拟列表：现在用 `content-visibility` 折中。
5. 主题：只有深色，没有浅色/跟随系统。

## 7. 信息不一致 —— 已修（2026-11-08）

原先列的 7 条，逐条核对后：**5 条确实存在并已修，1 条是我自己判断错了，1 条受权限限制没动。**

| # | 问题 | 处理 |
|---|---|---|
| 1 | README 只写「界面基于 CustomTkinter」，没提新界面 | ✅ 已改：开头说明两套界面 + 新增「## 界面」一节（怎么切、默认 auto、WebView2 依赖） |
| 2 | `main.py` 注释写「默认（tk）」「默认旧界面」，常量却是 `DEFAULT_UI_MODE="auto"` | ✅ 已改：模块 docstring、界面选择注释、`_saved_ui_mode()` 注释统一成 auto |
| 3 | `docs/UI-重建进度.md` 停在 468 项单测 / 12 项 Playwright / 474 项 | ✅ 已改：603 项单测、19 项界面检查、e2e 105 处 `check()`、harness 69 处；并注明该文件记录的是 0.10.0 那一轮，现状以 CHANGELOG 为准 |
| 4 | 文档说「默认受监督子进程」，实际 `main.py` 是进程内启动 | ✅ 已改：进度文档写清「auto = 进程内，异常/非 0 退回 Tk」；`launch.py` docstring 说明它只在显式调用时生效；顺带修了 `child_command()` 源码模式的入口（原来指向 launch.py 自己会套娃，现在指向 main.py，cwd 也跟着改） |
| 5 | `~/.pulses_easier/config.json` 的 `db_path` 指向已消失的 `/tmp/pe-e2e-api-*/db` | ⚠️ 未改：该目录属 `admin`、当前会话是 `Harness`，无写权限。影响很小——`database.get_db_path()` 发现目录不存在会返回 None，下次启动只是重新选一次库。想清掉：`python3 -c "import json,pathlib;p=pathlib.Path.home()/'.pulses_easier/config.json';c=json.loads(p.read_text());c.pop('db_path',None);p.write_text(json.dumps(c,indent=2))"` |
| 6 | `web/tsconfig.tsbuildinfo` 被 git 跟踪，每次构建都脏 | ✅ 已修：加进 `.gitignore` + `git rm --cached` |
| 7 | 「CHANGELOG 没有新界面章节」 | ❌ **我判断错了**：`CHANGELOG.md` 里有完整的 `v0.10.0 — 新界面（React + pywebview）`，0.10.2/0.10.3/0.10.4 也都在。只是它在文件第 144 行，我第一次只看了前 40 行 |

另外补了两处内部文档（`.gitignore` 里，不进版本库）：
- `docs/AI-协作交接.md`：核对时间 → 2026-11-08、版本 → 0.11.2、测试 → 603 项、补上 0.11.0–0.11.2 三版内容与 `ui_mode=auto`。
- `docs/AI-记忆继承.md`：顶部加时效提示（快照写于 2026-10-31，分支/默认界面/测试数已过时），命令里的 474 → 603。

## 8. 本次落地（2026-11-08）

- 提交 `78f451a`：`docs: 对齐新界面信息（README / 进度文档 / 注释），修受监督启动入口`
- 提交 `c740101`：`docs: 收敛 README 界面说明（共用 app/core，flow.py 只属于新界面）`
- 两次都已推送到 GitHub `main`（`03cbac7..c740101`）。
- 改动文件：`README.md`、`main.py`、`app/ui_web/launch.py`、
  `docs/UI-重建进度.md`、`.gitignore`（并从索引移除 `web/tsconfig.tsbuildinfo`）。
- 另改了两份不进版本库的内部文档：`docs/AI-协作交接.md`、`docs/AI-记忆继承.md`。
- 复跑：`pytest tests -q` → 603 passed；`test_web_bridge.py` → 20 passed；
  `python -m app.ui_web.launch` 冒烟无残留进程（子进程入口已指向 main.py）。

## 9. 环境（已就绪，可直接开发）

```bash
cd /home/admin/NS/pulses_easier
.venv/bin/python -m pytest tests -q                    # 603 项，85s
cd web && npm run build                                 # tsc + vite
node scripts/shots.mjs http://127.0.0.1:8095/index.html shots   # 截图（需先静态伺服 dist）
CHROMIUM=/home/admin/.cache/ms-playwright/chromium-1194/chrome-linux/chrome \
  ../.venv/bin/python ../scripts/dev/run_ui_e2e.py      # 真前端 + 真 Api 端到端
```

- Python 3.11.2 / pytest 9.2.0（仓库自带 `.venv`）
- Node v22.20.0；`web/node_modules` 完整；Playwright 内核 `chromium-1194` 已就位
- 本机无 `DISPLAY`、无 WebView2 → **真实窗口只能在你 Windows 机器上验**，CI 里也一样起不来（既有结论）
- `gh` 未登录 → 现在查不了 CI / 发不了版
