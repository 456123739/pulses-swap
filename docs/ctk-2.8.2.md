# Pulses Swap CTk 2.8.2 · 开发者端配色统一

开发者端不再借用玩家端的青绿语义色，所有状态与提示收进石板蓝色系；
玩家端继续使用原来的青绿，两个身份不串色。

## 改了什么

- 新增身份语义色令牌：成功、警告、信息、错误、状态点、状态底、日志标签、
  页面幕布、底部状态栏都从当前身份的 `ROLE_THEME` 取色。
- 动态创建的控件也走 `role_color()`：不会出现「切换身份后新卡片又变回青绿」。
- 开发者端：
  - 强调色 `#4E5F84`
  - 成功/已连接/已应用 `#4E5F84`
  - 警告与普通提示 `#5F6E8C`
  - 信息 `#5E7395`
  - 选中卡片软底 `#E6EBF4`
  - 错误保留低饱和红 `#A15F5F`，避免危险操作失去警示
- 玩家端保持：
  - 强调/成功 `#5BA89A`
  - 选中卡片软底 `#D6E8E4`
- 修复身份色映射的重复键：开发者选中软底 `#E6EBF4` 与状态正常底不能再相同，
  否则切回玩家时选中卡片会被错误映射成 `#E7F1EE`。

## 截图

均来自 2.8.2 实际界面（Linux Xvfb，1280×900）：

| 截图 | 内容 |
| --- | --- |
| [玩家首页](screenshots/ctk-2.8.2/01_home_default.png) | 默认只保留一键更新全部 |
| [玩家管理页](screenshots/ctk-2.8.2/02_manage_default.png) | 默认只保留一键更新全部 |
| [设置默认](screenshots/ctk-2.8.2/03_settings_default.png) | 高级操作关闭 |
| [高级操作首页](screenshots/ctk-2.8.2/04_home_advanced.png) | 手动入口恢复 |
| [高级操作设置](screenshots/ctk-2.8.2/05_settings_advanced.png) | 完整确认/预览/同步方式 |
| [一键更新进行中](screenshots/ctk-2.8.2/06_oneclick_progress.png) | 实际点击后的进度 |
| [一键更新完成](screenshots/ctk-2.8.2/07_oneclick_done.png) | 实际结果“当前预设已是最新” |
| [开发者首页](screenshots/ctk-2.8.2/08_developer_home.png) | 石板蓝强调/选中/提示；未登录状态仅用于配色展示 |
| [开发者管理页](screenshots/ctk-2.8.2/09_developer_manage.png) | 一键上传全部与开发者状态 |

## 验证

- 225 个 Python 测试通过。
- `ui_process_check` 新增身份配色断言，切到开发者再切回玩家，强调色、成功色、
  选中卡片、日志 SUCCESS 标签都正确恢复。
- UI 操作过程审计、布局审计、动画不变量、三档缩放、滚动、启动、窗口动画、
  在线 UI 检查全部通过。
