# Pulses Swap

Tacz 枪包一键切换工具 · v2.7.7

面向 Minecraft Tacz 模组玩家的枪包管理工具：拖入整合包 → 选预设 → 一键替换，
支持增量同步、二次校验、多预设管理与版本号管理；同步下载默认 4 线程并发。

v2.7.4 起界面改为「折叠图标侧栏 + 全局管理页」：悬停展开侧栏、玩家/开发者
滑动切换、管理页集中查看/检查/更新/发布预设，设置页右侧直接看运行日志。
开发者不必先加载整合包，也可以先登录蓝奏云管理云端。

## 下载

到 [Releases](../../releases) 页面下载：

| 平台 | 文件 | 说明 |
|---|---|---|
| Windows | `PulsesSwap-Setup-x.y.z.exe` | 安装器，双击安装 |
| Windows | `PulsesSwap-Portable-x.y.z.zip` | **绿色版**：解压即用，数据在同目录，不写注册表 |
| Linux | `PulsesSwap-linux-x86_64.tar.gz` | 解压后直接运行 `PulsesSwap` |

## 从源码运行

```bash
pip install -r requirements.txt
python src/pulses_swap.py
```

## 构建

安装包由 GitHub Actions 自动构建（见 `.github/workflows/build.yml`）：

- 推送 `v*` tag → 自动构建 Windows 安装器 + Linux 包，并发布 Release
- 手动触发 workflow → 只产出 artifact，用于验证

本地构建：

```bash
pip install -r requirements.txt pyinstaller
pyinstaller packaging/pulses_swap.spec --noconfirm --clean
```

## 目录结构

```
src/pulses_swap.py        主程序（单文件）
packaging/
  pulses_swap.spec        PyInstaller 配置
  installer.iss           Inno Setup 安装器脚本
.github/workflows/build.yml
requirements.txt
```

## 说明

- 界面为无顶栏布局：左侧为导航栏（主界面 / 设置 / 日志），选中项由一个带曲线
  动画的滑块指示；页面切换为整页推入/推出过渡。
- 设置项（存储模式、用户身份）改完即时生效并自动保存，无需点保存按钮。
- 用户数据（预设、数据库、日志）保存在程序目录下的 `PulsesSwap_database/`，
  卸载时不会删除。
- 旧版 `FGC_database` 会在首次启动时自动迁移。
- v2.7.7 延续 PCL 风格的快速弹出/收回动画：出现时从下方轻轻上浮并淡入，关闭时下移淡出；收窗从窗口当前位置开始，移动/最大化后不会先跳回启动位置。
