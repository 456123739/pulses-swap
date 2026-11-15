# 【新UI】Pulses Swap 分支 · 交接 / 续开发包

> 生成时间：2026-11-08 11:5x（Asia/Shanghai）
> 用途：原会话 `session-5a5350c1` 因上下文超限（2.03M tokens > 1.05M）报废后，
> 新会话靠这一份 + 同目录 `USER_PROMPTS.md` 直接进入开发，不必重读原对话。

---

## 0. 一句话状态

新 UI（PyWebView + React）已经走到 **v3.1.9 并发布**，仓库干净、227 个 Python 测试全绿、
前端可构建；**本地开发环境已重建**（venv + node_modules + Playwright）。
唯一缺的外部资源是 **gh 未登录**（发布 / 看 CI 日志需要）。

---

## 1. 关键路径

| 用途 | 路径 |
|---|---|
| 主仓库（新 UI 线，HEAD） | `/home/admin/111/pulses-swap` |
| CTk 2.8.x 工作树 | `/home/admin/111/pulses-swap-ctk`（分支 `fix/ctk-2.8.1`） |
| Python venv（本次新建） | `/home/admin/111/pulses-swap/.venv` |
| 前端源码 | `src/pulses_web/web/src/`（App.jsx 1077 行 / styles.css 834 行） |
| 前端产物 | `src/pulses_web/web/dist/`（`npm run build` 生成，已构建） |
| 原会话全文（可 grep） | `/home/admin/111/_history/newui-swap/session.jsonl`（95MB） |
| 原会话用户需求（384 条） | `/home/admin/111/_history/newui-swap/USER_PROMPTS.md` |
| 原会话助手阶段总结 | `/home/admin/111/_history/newui-swap/ASSISTANT_TIMELINE.md` |
| 早前导出的可读版 | `/vol2/@appshare/Harness/exported-sessions/新UI-Pulses-Swap分支.md`（2.9MB，仅助手侧、已截断） |

---

## 2. 版本与分支现状

- `VERSION = "3.1.9"`（`src/pulses/core/paths.py:48`），`package.json` 同为 3.1.9。
- HEAD：`release/ctk-2.8.0` @ `dddc34d`（工作树干净）。
  - ⚠️ 分支名是历史包袱：**3.1.5 ~ 3.1.9 的提交实际落在这条 `release/ctk-2.8.0` 上**。
- `feature/webview` @ `364dd25` = 3.1.4，是 HEAD 的祖先（新 UI 线的旧检查点）。
- `fix/ctk-2.8.1` @ `4838d97`，从 `fe81bae`（2.8.0 同步点）拉出。
- `origin/main` 落后 94 个提交；本地 tag 只到 `v3.1.2`（3.1.5+ 的 tag 由 GitHub Release 侧创建）。
- 最近发布：<https://github.com/456123739/pulses-swap/releases/tag/v3.1.9>
  - `PulsesSwap-Setup-3.1.9.exe` `7828266b…`
  - `PulsesSwap-Portable-3.1.9.zip` `38d432aa…`
  - `PulsesSwap-src-v3.1.9.zip` `b127d278…`

---

## 3. 架构地图（新 UI 线）

```
src/main.py                 旧 CTk 入口（仅 2.x 回滚用）
src/pulses_web_main.py      新入口：只起 PyWebView
src/pulses/…                CTk 界面 + 本地核心（路径/平台/文件/任务/managers）
src/online/                 在线同步（无 tkinter 依赖，可无头测试）
  service.py (1431) 编排：scan/check/plan/publish/sync
  provider_lanzou.py (679) / provider_lanzou_account.py (595)  蓝奏云会话与分享
  publisher.py (414) / downloader.py (406) / updater.py (251)
  manifest.py (320) / diff.py (256) / hashing.py (353) / packing.py
src/pulses_web/             WebView 桥
  api.py (350)              js_api 白名单（`Api._methods` 必须登记）
  controller.py (1017)      业务编排、启动检查、状态快照
  events.py (241)           EventPump + JobRunner（单写者队列）
  main.py (243)             窗口、DND、启动日志/MessageBox
src/pulses_web/web/src/     React 19 + motion/vite
  App.jsx  bridge.js  components/Icons.jsx  styles.css
```

数据流：`window.api.invoke` → `Api` 方法 → `JobRunner`（串行写） → `Controller` → `OnlineService`
→ 事件只经 `EventPump` 推回前端；前端**不得**直接改状态。

---

## 4. 环境与命令（已在本机验证）

```bash
cd /home/admin/111/pulses-swap

# Python 依赖（已装进 .venv）
.venv/bin/python -c "import customtkinter, webview, PIL, watchdog; print('ok')"

# 核心测试：227 个，约 50s，全绿（2026-11-08 复跑）
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q

# 前端构建（1.1s，产物 412KB js + 49KB css）
cd src/pulses_web/web && npm run build

# 前端黑盒（Playwright，chromium 已就绪）
# 需要在 8765 端口伺服 dist：python3 -m http.server 8765 --bind 127.0.0.1
node test-layout.mjs                      # 通过
node test-ui.mjs                          # 通过（截图目录 /tmp/web_shots 被 admin 占用时需改路径）
```

> 2026-11-08 复跑：227 单测通过、`vite build` 通过、`test-layout.mjs` 通过、`test-ui.mjs` 通过
> （把脚本里的 `/tmp/web_shots` 临时改名到可写目录后跑）。

**本机限制**：无 `DISPLAY`、无 Xvfb、无 PyGObject → 起不了真实窗口。
UI 验收靠 Playwright 无头 + GitHub Actions 的 Windows WebView 实操自测（32 项）。

---

## 5. 发布流程

- 打 tag `v3.x.y` 推上去 → `.github/workflows/build-web.yml`：
  前端构建 → 核心测试 → Playwright 黑盒 → 布局测试 → PyInstaller → 安装器 → Windows WebView 实操自测 → 上传 Release 资产。
- 发布前必须：`paths.VERSION`、`package.json` 两处版本一致 + `docs/changelog.md` 补条目。
- **当前阻塞**：`gh auth status` = 未登录。需要 `gh auth login`（或 `GH_TOKEN`）才能推 tag、建 Release、查 CI。

---

## 6. 硬约束 / 已踩过的坑（务必保留）

完整清单在 `docs/handover.md` 的「v3.0.0 WebView 迁移坑位」「v3.1.1 新增坑位」等小节，最关键的：

1. js_api 方法跑在独立线程 → 所有写操作走 `JobRunner`，不要在 api 里直接改状态。
2. 事件只能由 EventPump 推；worker 不得 `evaluate_js`。
3. 窗口 `hidden=False` 先显示，再绑 DND / 起事件泵；启动异常写 `webview-startup.log` + 原生 MessageBox。
4. 拖入路径用 `pywebviewFullPath`，并保留 `handle_drop_pending` 兜底（DOM drop 失败时前端把 files 交给 Python）。
5. 前端能调的一键 API 必须登记进 `Api._methods`（`online.sync.auto` / `publish.auto` / `*.all` 等）。
6. 启动检查节流：启动只检查「已绑定 + 未应用 + 超过 15 分钟」，缓存快路径 `check(prefer_cache=True, cache_ttl=900)`；手动检查/一键更新始终强制走网络。
7. 改 UI 必须过两套测试（Python 227 + `test-ui.mjs`/`test-layout.mjs`），再做打包冒烟。

---

## 7. 文档债 / 已知缺口（接手先知道）

1. `docs/changelog.md` 顶部仍是 **v2.8.0 / v3.1.4**，**3.1.5–3.1.9 没有条目**。
2. `docs/handover.md` 标题写的是 **v3.1.4**，3.1.5–3.1.9 期间的新坑（TTL 缓存、Windows 自测固定窗口、CI 单独上传截图等）未归档。
3. `docs/test-report.md` 主体是 2.6.0/2.7.x 的实测；3.1.x 的证据在 CI 产物与 Release 资产里，没有本地报告。
4. 真机上传/下载 smoke 需要真实蓝奏账号，本机没有凭证。
5. `origin/main` 落后 94 个提交，新 UI 线没有推到 main。

---

## 8. 这个用户怎么验收（从 384 条需求里提炼）

- **不要反复推 CI 试错**：本地一次改全、跑绿，再推一次快速验证。
- **业务流程必须真的走通**：玩家/开发者两条线都要跑；绝不能出现「做了但用户找不到/不会用」。
- **一键化优先**，高级操作收进折叠区；入口要显眼。
- 汇报用中文，给证据：测试数量、截图、CI job 结论、产物哈希。
- 先修完再提交，不要半成品提交。

---

## 9. 下一步候选（等用户点方向）

1. 补文档债：changelog 3.1.5–3.1.9、handover 升级到 3.1.9（零风险，1 次提交）。
2. 3.2.0 功能线：由用户指定（例如冲突提示/备份、跨设备、批量预设管理等）。
3. 工程化：分支归位（`feature/webview` FF 到 HEAD 或新开 `feature/webview-3.2`）、main 同步策略、gh 登录与发布自动化。
