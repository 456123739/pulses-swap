# React / Python 业务流程端到端验证（模拟数据）

本目录 `business-flow-*-SIMULATED.png` 和 `business-flow-SIMULATED-report.json` 均来自本地模拟蓝奏 HTTP 服务。账号、整合包、预设和 ZIP 都是测试生成的模拟数据，**不是实际蓝奏账号或真实用户文件**。报告不包含密码、Cookie 或令牌。

运行：

```sh
cd /home/admin/111/pulses-swap-web
node src/pulses_web/web/test-business-flow.mjs
```

脚本使用现有 `.venv/bin/python`、web 下已安装的 Playwright 与默认 Chromium `/home/admin/.cache/ms-playwright/chromium-1194/chrome-linux/chrome`。可用 `PLAYWRIGHT_CHROMIUM_EXECUTABLE` 指定另一个浏览器路径。

每次运行先把当前 React 源码实际构建到独立临时目录，然后启动 `tests/ui_bridge_server.py`，仅监听随机回环端口。浏览器页面加载该构建，桌面桥接函数通过 HTTP 传给真实 `Api.invoke`；真实 EventBus 事件经 HTTP 顺序转发给 `window.PS.push`。保留真实 JobRunner 与 AppController。仅注入本地模拟 account_base、隔离存储路径和文件选择器测试路径。所有业务操作由 Playwright 点击及填写 React 表单触发；没有注入 DOM、伪造状态、伪造成功事件或直接调用业务对象完成操作。

流程：打开测试整合包 → 表单登录本地模拟账号 → 切换开发者 → 新建模拟预设 → 导入 alpha.zip → 首传指定 `/PulsesSwap/UI-SIMULATED`、`v2.3.4` 和说明 → 导入 beta.zip → 一键上传至 `v2.3.5`。独立读取模拟 HTTP 服务的存储，核对 `_pulses_manifest.cfg` 的实际 JSON、路径、版本、说明与 ZIP SHA-256；第二次仅上传 beta.zip 对应内容指纹文件和清单，并断言真实页面详情卡已可见 `v2.3.5`，报告记录 `visiblePresetVersion`。

故障场景：第三次从界面导入 gamma.zip 后，使用模拟 HTTP 服务现有故障开关破坏清单下载字节。再点击上传，要求真实任务发出 job.error，所有远端文件摘要、上传/删除记录均保持不变，版本维持 v2.3.5，远端没有 gamma.zip，证明未用历史缓存继续上传。

进程和临时构建/数据库由脚本退出逻辑清理。最终状态、版本和错误详情见同目录 JSON 报告；退出码非 0 表示至少一项断言失败。
