# Pulses Swap 交接文档（v3.0.0 WebView）

> 给接手的人 / AI 看的：这个软件被拆成了哪些文件、每个文件干什么、
> 数据怎么流动、改哪里、怎么跑测试、怎么打包。
> 阅读顺序建议：本文 §1 → §2 → §4 → 需要时查 §3。

---

## 1. 一句话概括

一个 **Python + customtkinter** 的桌面工具：把 Minecraft 的 TACZ 枪包按「预设」分组，
一键把某组枪包换进游戏的 `tacz` 目录；同时把预设发布到**蓝奏云**，
玩家绑定分享链接后可以增量同步。

- 版本：`3.0.0`（`src/pulses/core/paths.py` 里的 `VERSION`）
- 入口：`src/main.py` → `pulses.ui.app.main()`
- 依赖：`customtkinter` `tkinterdnd2` `watchdog` `Pillow`（见 `requirements.txt`）
- 不依赖任何第三方网络库（HTTP 全用标准库 `urllib`）

---

## 2. 目录结构

```
pulses-swap/
├── src/
│   ├── main.py                 入口（3 行，调 pulses.ui.app.main）
│   ├── pulses_swap.py          兼容壳：老代码 from pulses_swap import * 仍可用
│   ├── pulses/                 界面 + 本地逻辑
│   └── online/                 在线同步（不依赖 tkinter，可命令行跑）
├── packaging/                  打包配置 + 各种验证脚本
├── tests/                      单元 / 集成测试（194 个）
├── docs/                       方案、教程、交接文档
└── requirements.txt
```

**关键分层原则**

| 层 | 位置 | 是否依赖 tkinter |
|---|---|---|
| 主题 / 核心 / 动画 / 控件 | `src/pulses/{theme,core,animation,widget}` | 是 |
| 界面（页面 / 弹窗 / mixin） | `src/pulses/{ui,pages,dialogs}` | 是 |
| 在线同步 | `src/online/` | **否**（可在命令行、测试里直接用） |

`online/` 完全不 import tkinter，所以能在无显示环境跑集成测试。

---

## 3. 文件清单（按职责）

### 3.1 入口与兼容层

| 文件 | 行数 | 职责 |
|---|---|---|
| `src/main.py` | 24 | 唯一入口，调用 `pulses.ui.app.main()` |
| `src/pulses_swap.py` | 53 | 兼容壳：模块级 `__getattr__` 转发到 `pulses.*`，读可变全局时优先读 `config` |
| `src/pulses/__init__.py` | 1 | 空 |

### 3.2 主题与核心（`src/pulses/theme` `src/pulses/core`）

| 文件 | 行数 | 职责 |
|---|---|---|
| `theme/palette.py` | 152 | 颜色 / 圆角 / 尺寸 / 间距令牌（`C_*` `R_*` `H_*` `PAD_*` `FS_*`） |
| `theme/typography.py` | 109 | 字体栈、`resolve_font_family()`、`apply_font_fallbacks()`（结果同步回 `config`） |
| `core/paths.py` | 156 | `VERSION`、程序目录、数据目录解析、`resource_path()`、数据库位置读写 |
| `core/platform.py` | 386 | DPI 感知与缩放（`enable_dpi_awareness` `sync_ui_scale` `px` `tk_font` `lock_ctk_scaling`）、Win11 不透明（`make_window_opaque` `refresh_window_opacity` `_apply_opaque_window`）、回收站 |
| `core/state.py` | 52 | 运行时可变全局：`UI_SCALE`、`ANIMATIONS_ENABLED` |
| `core/tasks.py` | 96 | worker → 主线程投递（`ui_call` / `start_ui_pump`），替代跨线程 `root.after` |
| `core/files.py` | 144 | 文件指纹、`format_size`、`sanitize_filename`、`locate_tacz_by_path` |
| `config.py` | 20 | 聚合层：把上面四个再导出，保持 `config.X` 调用方式 |

> **改颜色 / 间距 / 字号 → 只改 `theme/palette.py`**。

### 3.3 动画（`src/pulses/animation`）

| 文件 | 行数 | 职责 |
|---|---|---|
| `animation/easing.py` | 168 | 缓动曲线（含三条弹簧）、`lerp_color`、`_TWEENS` 注册表 |
| `animation/tween.py` | 257 | `tween()` 调度器、`attach_hover_glow()`、销毁时清理补间 |

| 曲线 | 用途 |
|---|---|
| `ease_out_cubic` | 位移默认 |
| `ease_out_spring` | 弹窗入场（过冲 ~7%） |
| `ease_out_pill` | 分段控件滑块（过冲 ~5%） |
| `ease_out_soft_spring` | 颜色 / 描边（过冲 ~3%） |
| `ease_out_back` | Toast |

> 动画开关：`config.ANIMATIONS_ENABLED`。关闭时 `tween()` 一帧到位，逻辑不变。

### 3.4 控件（`src/pulses/widget`）

| 文件 | 行数 | 职责 |
|---|---|---|
| `button.py` | 135 | `AnimatedButton`：hover / 按下 / 松开都是逐帧混色 |
| `segmented.py` | 331 | `CanvasSegmented`：自绘分段控件（导航、选项卡、单选） |
| `stack.py` | 308 | `SlideStack`：页面栈，推入/推出（页面停靠在视口外，不用 hidden） |
| `toast.py` | 122 | `Toast`：右上角浮出提示 |
| `factory.py` | 583 | `make_button` `make_entry` `make_label` `make_section_header` `make_list_scroll` `make_checkbox` `FormField` `attach_entry_focus` `attach_entry_menu` `ellipsize` `open_url` |
| `cards.py` | 656 | `PresetCard`（三行文字按宽度省略）/ `CardList` / `ScrollArea` / `StatusDot` / `EmptyState` |
| `diffrow.py` | 361 | `DiffRow` / `DiffList`（逐项勾选）/ `InfoRow` / `InfoList`（只读） |

### 3.5 界面（`src/pulses`）

| 文件 | 行数 | 职责 |
|---|---|---|
| `dialogs.py` | 1000 | 窗口内覆盖层弹窗（`OverlayCard`）、`show_info/warning/error`、`ask_*`、数据库定位与迁移对话框 |
| `managers.py` | 1156 | 数据层：`AppSettings` `LogManager` `GuideManager` `RecentPacksManager` `TaczWatcher` `PresetManager` |
| `pages.py` | 672 | 设置页（常规 / 数据库 / 关于，含「在线同步」分组） |
| `ui/window.py` | 420 | `WindowMixin`：窗口骨架、侧边栏、页面切换、Win11 不透明防护、菜单 |
| `ui/page_home.py` | 651 | `HomePageMixin`：主界面三列布局、拖入、最近面板 |
| `ui/packs.py` | 790 | `PacksMixin`：整合包加载、预设卡片/选中、右键菜单、重命名/删除、TACZ 监控 |
| `ui/transfer.py` | 503 | `TransferMixin`：应用预设、导入/导出、进度条、忙碌态 |
| `ui/database.py` | 440 | `DatabaseMixin`：数据库定位 / 切换 / 合并 / 迁移 |
| `ui/page_log.py` | 94 | `LogPageMixin`：日志页 |
| `ui/misc.py` | 236 | `MiscMixin`：身份提示、教程入口、杂项 |
| `ui/online.py` | 1778 | `OnlineMixin`：**所有在线相关界面**（卡片状态、来源、同步、发布、身份登录、详情、诊断） |
| `ui/app.py` | 238 | 装配 `PulsesSwapApp(8 个 mixin)` + `main()`（含 Win11 不透明与缩放锁） |

> 主窗口是 mixin 拼起来的：`PulsesSwapApp(WindowMixin, HomePageMixin, LogPageMixin,`
> `DatabaseMixin, PacksMixin, TransferMixin, MiscMixin, OnlineMixin)`。
> 每个 mixin 只依赖 `self.xxx` 上的约定属性（见 §5）。

### 3.6 在线同步（`src/online`）

| 文件 | 行数 | 职责 |
|---|---|---|
| `errors.py` | 113 | 统一异常：`message / detail / hint / retryable` + 11 个子类 |
| `acw.py` | 71 | 蓝奏 `acw_sc__v2` 人机校验的纯 Python 解法 |
| `hashing.py` | 336 | 文件 sha256、**树摘要**、`HashCache`、`scan_local` |
| `manifest.py` | 320 | manifest（JSON-in-CFG）规范化 / 完整性校验 / 原子写 / 版本比较 |
| `packing.py` | 122 | 确定性打包、防穿越与防炸弹的解包 |
| `diff.py` | 252 | 两方比对 → `Plan`（角色动作、阻塞项、统计、默认勾选） |
| `provider_lanzou.py` | 669 | 匿名分享解析：列表 / 直链 / 人机校验 / 流式下载 / 重试 |
| `provider_lanzou_account.py` | 575 | 账号操作：登录 / 建目录 / 流式上传 / 删除 / 分享 |
| `downloader.py` | 273 | 下载到暂存 + 当场校验（含传输包摘要） |
| `updater.py` | 251 | 原子替换、目录两步改名 + journal、崩溃恢复 |
| `publisher.py` | 414 | 建目录 → 删云端多余 → 上传 → manifest 最后替换 → 取分享 |
| `trash.py` | 139 | 系统回收站（Windows / freedesktop） |
| `paths.py` | 86 | 状态目录布局（`.online/`） |
| `service.py` | 1393 | 门面：绑定 / 检查 / 同步 / 发布 / 诊断 / 记账 / index.json |
| `__init__.py` | 38 | 公开 API |

---

## 4. 数据流

### 4.1 本地（预设切换）

```
整合包目录/tacz  ←── apply_preset() ──→ 数据库/<预设名>/
      │                                     │
      └── 当前生效的枪包                      └── 未生效的预设（index.json + 枪包）
```

- `PresetManager.apply_preset()` 把当前 `tacz` 里的枪包**移回**原预设，再把目标预设的枪包**移入** `tacz`
- 受保护、不参与移动的：`tacz-pre.toml`、`blacklist.txt`、`tacz_default_gun/`、`index.json` 等

### 4.2 在线同步（玩家）

```
① check()
   云端分享 ──list_files──> 找 _pulses_manifest.cfg（旧版 .txt 兜底）──fetch──> manifest
   本地目录 ──scan_local(HashCache)──> files[]
        └── diff.compare(local, cloud, role="player") ──> Plan
② sync(plan, selection)
   Downloader: 逐项下载到 staging → 校验（zip 比 sha256 / folder 比树摘要）
   Installer : 原子替换进正式目录（目录用两步改名 + journal）
   _finish() : 更新 index.json / version.txt / 本地 manifest / sources.json
```

**本地内容目录（`root`）随预设状态变化**：

| 预设状态 | `root` |
|---|---|
| 未应用 | `数据库/<预设名>/` |
| 已应用 | `整合包/tacz/` |

`PresetRef(name, path, root, applied)` 就是干这个的：`path` 存元数据，`root` 放内容。

### 4.3 发布（开发者）

```
publish_plan(): ensure_path(云端路径) → folder_share → 用分享链接读云端 manifest
                → scan_local → diff.compare(role="developer")
publish():      删云端多余 → 逐个上传（文件夹先打包）→ manifest(generation+1) → 分享
```

### 4.4 状态目录

```
PulsesSwap_database/.online/
├── sources.json              每个预设的源（链接 / 密码 / 云端路径 / 上次版本 / 历史）
├── account.json              开发者账号（打码保存）
├── cloud/<preset>-<hash>.json 上次拉到的云端 manifest（离线可用）
├── local/<preset>-<hash>.json 上次算出的本地 manifest（展示缓存）
├── cache/<root-hash>.json     哈希缓存（按内容目录区分）
└── staging/<preset>-<hash>/   下载暂存 + journal.json
```

> 目录名以 `.` 开头是必须的：预设扫描会跳过隐藏目录，否则它会被当成一个预设。

---

## 5. 关键约定

### 5.1 manifest 格式

云端 manifest 的文件名是 `_pulses_manifest.cfg`，**内容仍然是 JSON**。
蓝奏的扩展名白名单实测拒绝 `.json` / `.toml` / `.yaml` / `.ini` / `.xml`，
`.cfg` 可以上传；所以只改后缀，不换格式。解析直接用标准库 `json`
（C 实现），比 INI/CFG 解析更快，也不会引入第二套结构。旧版
`_pulses_manifest.txt`（同样 JSON）仍然兼容读取，发布一次后自动换成 `.cfg`。

```json
{
  "format": "pulses-manifest",
  "schema": 2,
  "name": "SSR预设包",
  "version": "2026.10.18",
  "generation": 7,
  "min_app": "2.5.0",
  "generated_at": "2026-10-18T01:00:00Z",
  "notes": "新增 3 把枪，修贴图",
  "manifest_sha256": "…",
  "files": [
    {"path": "gun_alpha.zip", "type": "zip", "size": 41943040,
     "sha256": "9f2c…", "packed_size": 41943040,
     "packed_sha256": "9f2c…"},
    {"path": "gun_beta.zip", "type": "folder", "target": "gun_beta",
     "size": 52428800, "files": 42, "sha256": "7d1a…",
     "packed_size": 39800000, "packed_sha256": "…"}
  ]
}
```

| 字段 | 含义 |
|---|---|
| `format` | 固定 `pulses-manifest`，防止把别的 JSON 误当 manifest |
| `schema` | 当前 2；高于程序支持版本时提示升级 |
| `manifest_sha256` | 对整份 manifest（不含本字段）的规范化 sha256，读入时校验 |
| `path` | 上传到网盘的文件名，**也是比对唯一键**（不区分大小写） |
| `type` | `zip` 原样 / `folder` 解压到 `target` / `file` 其他 |
| `sha256` | 内容摘要；`folder` 是**树摘要** |
| `size` / `packed_size` | 逻辑体积 / 传输体积 |
| `packed_sha256` | 传输包摘要；`folder` 为 zip 的 sha256，下载后先验包再解压 |

本地缓存 `cloud/<preset>.json` / `local/<preset>.json` 仍然是 JSON（不经过网盘），
同样带 `manifest_sha256`；旧缓存没有该字段也能读。

> `manifest_sha256` 是**完整性校验**，不是数字签名：能发现传输损坏、误改、
> 手改漏改，但不能阻止有意的重新计算。真正的防篡改需要服务端签名/私钥，
> 当前蓝奏分享模式做不到，别把它宣传成"不可伪造"。

### 5.2 树摘要（folder 类型的 sha256）

```
h = sha256("pulses-tree-v1\n")
for (rel, size, file_sha) in sorted(树里每个文件):
    h.update(rel + "\0" + size + "\0" + file_sha + "\n")
```

只取决于内容，与打包细节无关 → 开发者算一次、玩家解压后再算一次，能对上。

### 5.3 不进 manifest 的东西

`index.json` / `version.txt` / `description.txt` / `tacz-pre.toml` / `blacklist.txt` /
`tacz_default_gun/`（兼容 `tacz-default-gun/`）/ `_pulses_manifest.cfg` / `_pulses_manifest.txt` / 隐藏文件。见 `hashing.EXCLUDED_NAMES` 与 `service._sanitize_cloud()`。

### 5.4 网盘接口（2026 版，已实测）

| 动作 | 接口 |
|---|---|
| 登录 | `GET accounts.woozooo.com/accounts.php?action=login&ref=lanzoui.com`（先过 acw）→ `POST` `task=uselogin&username&password&ref` → 跟随 `msgs` |
| 列目录 | `POST pc.woozooo.com/doupload.php` `task=47` |
| 建目录 | 同上 `task=2` |
| 列文件 | 同上 `task=5` |
| 删文件 | 同上 `task=6` |
| 分享 | 同上 `task=18`（完整地址在 `info.new_url`） |
| 上传 | `POST pc.woozooo.com/html5up.php`，multipart，目录用 `folder_id_bb_n` |
| 下载直链 | `/fn` → `apifile/ajaxfile.php`，**必须带 `websign=2`** |

### 5.5 mixin 之间依赖的约定属性

`OnlineMixin` 假设 `self` 上有：`root`、`log_manager`、`preset_manager`、`tacz_path`、
`settings`（`AppSettings`）、`db_ready`、`current_selected_preset`、
以及 `preset_cards`、`_update_preset_list()`、`on_preset_selected()`、`toast()`。

---

## 5.6 文档索引

| 文档 | 给谁看 |
|---|---|
| `docs/swap-online.md` | 方案与设计决策（含视觉体系 §14、功能清单核对） |
| `docs/tutorial-player.md` | 玩家端操作教程 + 教程动画分镜 |
| `docs/tutorial-developer.md` | 开发者端操作教程 + 教程动画分镜 |
| `docs/tutorial-animation-brief.md` | 做教程动画的 AI：去哪拿信息、什么不能改 |
| `docs/handover.md` | 本文：代码结构与交接 |

## 6. 怎么跑

```bash
# 源码运行
python src/main.py

# 单元 + 集成测试（182 个）
python -m unittest discover -s tests -t .

# 打包：一份 spec 出三端
pyinstaller packaging/pulses_swap.spec --noconfirm --clean
```

| 平台 | 产物 | 说明 |
|---|---|---|
| Windows 10/11（主要用户） | `dist/PulsesSwap/PulsesSwap.exe` → Inno Setup 安装器 | 图标用 `icon.ico`；Win10 上 DWM 属性不认会自动跳过，不影响启动 |
| macOS | `dist/PulsesSwap.app` | 必须走 `BUNDLE`，否则只是个 Unix 可执行文件；图标用 `icon.icns`；Intel / Apple Silicon 各打一份 |
| Linux | `dist/PulsesSwap/` | 仅开发自测用，不对外发布 |

**图标 / logo**：三端共用 `packaging/icon.{ico,png,icns}`，由 `make_icon.py` 生成。
想换成自己的 logo，把图放到 `packaging/logo.png` 再跑一次：

```bash
python packaging/make_icon.py     # 三个格式一起重出
```

CI（`.github/workflows/build.yml`）在推 `v*` tag 时自动构建 Windows 安装器 +
macOS 双架构 + Linux，并发布到 Release；手动 dispatch 只出 artifact。

**没有 CI 也能出 Windows 包**（PyInstaller 不能交叉编译，必须在 Windows 上跑）：

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

产物：`dist\PulsesSwap\PulsesSwap.exe`（目录版）+ `dist\installer\*.exe`（装了 Inno Setup 才有）。

**绿色版 zip 的结构**（CI 的「打包绿色版」步骤生成，解压即用）：

```
PulsesSwap-Portable-2.5.0.zip
├─ PulsesSwap.exe            ← 双击就能跑
├─ _internal\                ← 运行时
├─ PulsesSwap_database\      ← 空数据库（已带 .settings.json / .global.json）
│                            ← 程序在自身目录发现它就自动使用，不再弹「选择数据库」
└─ 使用说明.txt
```

数据库位置优先级：程序目录可写 → 用程序目录（绿色版）；
不可写（如 `C:\Program Files`）→ 自动退到 `%LOCALAPPDATA%\PulsesSwap`。

无显示环境跑界面测试（本机做法）：

```bash
export XDG_RUNTIME_DIR=/tmp/xdg
export DISPLAY=:99          # weston headless + Xwayland
```

---

## 7. 验证脚本（`packaging/`）

| 脚本 | 作用 | 需要网络 |
|---|---|---|
| `ui_snapshot.py` | 导出控件树 JSON，改前改后比对 | 否 |
| `ui_audit.py` | 全流程 + 所有按钮逐个点击 | 否 |
| `anim_invariants.py` | 动画中间帧不变量（含 logo 幕布切页） | 否 |
| `ui_process_check.py` | 全流程操作过程 + 幕布重入/改目标 | 否 |
| `scale_check.py` | 100% / 125% / 150% 三档布局 | 否 |
| `online_ui_check.py` | 在线界面冒烟（身份/来源/同步/发布） | 否 |
| `online_e2e.py` | 两端全流程 15 阶段（含失败/重启） | 否（本地模拟服务） |
| `online_smoke.py` | 真实分享：列表 / 下载 / 校验 | **是** |
| `lanzou_live_upload.py` | 真实账号：上传 / 分享 / 下载回验 | **是** |
| `lanzou_live_publish.py` | 真实账号：完整发布闭环 | **是** |
| `win_dwm_check.py` | Win11 不透明逻辑 | 否 |
| `startup_check.py` | **走真实入口 `main()`**，确认打包后能启动 | 否 |
| `window_anim_check.py` | 主窗口出现/关闭动画：起始透明下移、结束回矩形、关闭隐藏 | 否 |
| `scroll_check.py` | 多列表滚轮路由 / CTk 不解绑 / Listbox / 60 张卡片滚动 | 否 |
| `lanzou_publish_release.py` | 把 dist 里的产物传到网盘下载文件夹（凭据走环境变量） | **是** |

> 界面截图：本机是 weston(headless) + Xwayland，组合器把窗口内容放在自己的
> pixmap 里，`XGetImage` / `CopyArea` 都拿不到像素，`weston-screenshooter`
> 在 headless 后端直接断言失败。**要截图请在普通桌面上跑**；
> 需要精确排版数据就用 `ui_snapshot.py` 导出的控件树 JSON。

> 后三个 `lanzou_live_*` / `online_smoke` 会打真实网盘，**别频繁跑**（有封号风险）。
> 凭据只从环境变量 `PULSES_LANZOU_USER` / `PULSES_LANZOU_PASS` 读，不落盘。

---

## 8. 改哪里

| 想改什么 | 去哪 |
|---|---|
| 配色 / 圆角 / 间距 / 字号 | `theme/palette.py` |
| 字体回退 | `theme/typography.py` |
| 动画曲线 / 时长 | `animation/easing.py`、各控件的 `tween(...)` 调用 |
| 主界面布局 | `ui/page_home.py` |
| 预设卡片长相 | `widget/cards.py` |
| 弹窗样式 | `dialogs.py`（`add_title/add_subtitle/add_divider/add_buttons`） |
| 表单字段（标签+输入+提示+报错） | `widget/factory.py` 的 `FormField` |
| 字号阶梯 | `theme/typography.py`（`FS_TINY`…`FS_DISPLAY`） |
| 在线界面的文案 / 流程 | `ui/online.py` |
| 差异判定规则 | `online/diff.py` |
| 同步落盘 / 原子替换 | `online/updater.py` |
| 网盘接口 | `online/provider_lanzou*.py` |
| manifest 字段 | `online/manifest.py` |

---

## 9. 已知限制

| 限制 | 说明 |
|---|---|
| 单文件 100MB | 蓝奏免费账号上限，超出会被 `diff` 标红 |
| 扩展名白名单 | `.json` / `.toml` / `.yaml` 传不上去；manifest 用 `.cfg` 后缀，内容是 JSON |
| 不支持断点续传 | 蓝奏不给 Range，失败整包重来（文件级重试有） |
| 文件夹型枪包粒度 | 内容一变就整包重传 |
| 无玩家回滚 | 设计如此：云端为准，覆盖不备份 |
| 网盘风控 | 机房 IP 可能要求人机验证；家庭宽带正常 |
| 登录要 acw 校验 | 已实现，但网盘改版时需要跟着改 |

---

## 10. 历史与坑（读代码前先看这段）

1. **主窗口原本是 7399 行单文件**，后来拆成 `theme/core/animation/widget/ui` 分层，
   再按职责拆成 8 个 mixin。`src/pulses_swap.py` 是兼容壳。
2. **页面栈不能用 `state="hidden"`**：隐藏的 canvas window 不会被 Tk 重新布局，
   切回来会是 384×483 的旧尺寸（表现为"撕裂"）。现在页面停靠在视口外。
3. **CTk 控件尺寸不能乘 `px()`**：CTk 自己会按 `widget_scaling` 放大，
   再乘一次就是双重缩放（125% 下卡片高 134 而不是 115）。
   `px()` 只用于 `tk.Canvas` 尺寸、`grid minsize`、`place` 偏移。
4. **用 `grid` 布局的卡片要 `grid_propagate(False)`**，只写 `pack_propagate` 高度仍会被内容顶开。
5. **补间要在控件销毁时清理**：CTk 的 `bind` 绑在内部 Canvas 上，
   不能用 `event.widget` 判断，要用闭包捕获控件本身（见 `tween._install_destroy_guard`）。
6. **`.online` 必须是隐藏目录**，否则会被预设扫描当成一个预设。
7. **在线检查的并发**：检查中再次请求会排队补跑（`_online_recheck`），
   否则卡片会停在旧状态。
8. **蓝奏的三个坑**：登录换域名、上传换 `/html5up.php`、下载要 `websign=2`。
   这三个都是真实账号实测出来的，mock 里也加了对应校验防止回归。
9. **Win11「没写半透明却半透明」的真凶是 CTk 自己**：
   `ScalingTracker.check_dpi_scaling()` 每 100ms 轮询 DPI，一旦判定变化就
   `attributes("-alpha", 0.15)` → 改缩放 → `attributes("-alpha", 1)`。
   在 Win11 上这会重新触发 DWM 材质评估（Mica/亚克力回来），
   中途抛异常还会永久停在 15%。修法是 `lock_ctk_scaling()`：
   关掉 `deactivate_automatic_dpi_awareness`、摘掉轮询、把 DPI 缓存归一成 1.0，
   再显式设我们自己的缩放。**别再往 `_opacity_tick` 里加逻辑**，它现在只是兜底。
   标题栏另外用 `DWMWA_CAPTION_COLOR(35)/BORDER_COLOR(34)/TEXT_COLOR(36)` 上色，
   不设的话 DWM 会给标题栏铺一层带材质的底，同样透壁纸。
10. **原生 Tk 控件的字号必须是负数**：`tk.Canvas` 文字、`tk.Listbox` 的正数字号
    是「磅」，会被 `tk scaling` 再乘一次（100% 下 1.33 倍、150% 下 2 倍），
    和 CTk 的像素字号对不上。统一走 `tk_font(family, size_px, weight)`。
    CTk 控件则相反：**不要**套 `px()`，它自己会缩放。
11. **`from x import *` 不会带出下划线开头的名字**：拆分后 `main()` 里的
    `_set_app_user_model_id` / `_apply_opaque_window` 就是这样丢的 ——
    所有测试都直接 `PulsesSwapApp(root)`，所以全绿，但打包出来的 exe 一双击就
    NameError。现在这两个给了公开别名（`set_app_user_model_id` /
    `apply_opaque_window`），并由 `packaging/startup_check.py` 守着。
    **改 `main()` 之后一定跑一遍它。**
12. **输入框一律用 `make_entry()` / `FormField`**：右键菜单（剪切/复制/粘贴/全选/清空）、
    聚焦描边、校验变红都在里面，自己 `ctk.CTkEntry(...)` 会漏掉这些。
    校验报错要**先 `focus()` 再 `error()`** —— 聚焦事件是排队投递的，顺序反了红色会被盖掉。
13. **CTk 的 `place()` 不接受 `width/height`**（会抛 `ValueError`，被 `except`
    吞掉后就是"浮层没出现/位置不对"）。正确姿势：先 `place(x=…, y=…, relx=…)`
    落点，再 `place_configure(width=…, height=…)` 改尺寸。
    「最近」下拉就踩过这个坑：它挂在 26px 高的按钮行里，靠 `relx/rely` 定位
    失败后落在 `(0,0)`、把「最近」按钮整个盖住 —— 于是**再也点不到按钮去收起**。
    现在浮层挂在整页（`self.home_page`）上，按按钮行的 root 坐标算位置，
    点外面 / 点按钮 / 切页面 / 换整合包都会 `place_forget()`。
14. **`ylogin` 是会话 ID，不是账号**。旧版 `account.json` 把它当昵称存，
    界面上就是"开发者 · 4654636"（用户会以为登错号），自动登录时还会拿它当
    用户名去 POST。现在：`uid` 只用来判断"有没有登录过"，`username` 存真正的
    登录名（手机号/邮箱），界面只显示 `mask_account()` 打码后的结果；
    旧文件读出来会丢掉那个纯数字昵称。**别再把 uid 显示或当账号用。**
15. **网盘读取必须有时间上限**。分享页解析 + 直链轮询的重试链在网盘抽风时能卡
    好几分钟，界面表现就是"一直在检查、连不上"。现在 `_fetch_manifest_bounded()`
    用工作线程 + `join(timeout)` 兜住（源 25s、总计 45s），账号接口列目录失败时
    直接退回缓存（没缓存就明确报错，**不能假装云端为空** —— 否则界面会显示
    「有 N 项待发布」，用户一发布就是整包重传）；界面侧 `_online_check` 有 90s
    看门狗，并把阶段（连接云端 / 读取云端 / 扫描本地）打到卡片和来源页上。
16. **玩家第一次从云端拉取时，不能要求「先应用再更新」**。那条规则是给开发者发布用的；
    玩家新建的预设是空的，根本没法先应用。真实联调时这里直接把首次同步拦死，
    现在 `_sync_now` 不再检查 applied（同步写预设目录；已应用时写 tacz，两种都安全）。
17. **Tk 变量只能在主线程读**。`open_add_from_cloud` / 来源页「测试连接」的 worker
    里曾经直接 `pwd_var.get()`，抛 `RuntimeError: main thread is not in main loop`，
    线程静默死掉，对话框永远停在「正在读取…」。改成主线程先读值、再把普通字符串
    传进线程。
18. **按钮的 disabled 状态要有人负责**。`publish_btn` 创建时是 disabled，只有
    `set_busy_state(False)` 会顺手放开 —— 开发者重启后点「发布到云端」毫无反应。
    现在它和 `apply_btn` 一起归 `_set_pack_dependent_buttons` / `_disable_buttons` 管。
19. **应用预设要能失败**。只读的 tacz 下，旧代码会「旧文件删不掉、新枪包移进去、
    还标记成已应用」。现在先写探针文件检查可写，清空后校验没有残留、移动后校验
    源目录已空；任何一步失败都把 applied 标记回滚并报错。
20. **独立数据库模式下「切换数据库」没有意义**：每个整合包都用自己的
    `PulsesSwap_database`，切了位置、重新打开整合包又会切回去。现在独立模式会
    明确拒绝并提示先改成「合并数据库」；合并模式切换后会更新 `db_path`，
    并把 `storage_mode` 写回新库（新库默认是 isolated，不写回会被冲掉）。
21. **替换预设要有事务性回滚**。`_move_items` 失败后不能继续搬（半成品更大），
    而且必须把「已经搬进 tacz 的新预设文件」搬回预设目录 —— 否则下次重试的
    `_clear_dir` 会把它们删掉，真的丢枪包。现在按阶段（reclaim / clear / load）
    回滚：回收阶段失败就保持原预设 applied（绝不删），装载阶段失败就把新文件搬回。
22. **「必须先应用」要守在所有入口**：卡片主按钮、卡片动作、右键、预览弹窗、
    `_run_publish` 本身都要检查；只在 `_publish_now` 拦，会被 `open_publish_dialog`
    绕过。
23. **切换数据库后要按新库的 role 重刷整套界面**（徽标/主题/主操作/设置页分区）。
    切库只改 `settings` 不改界面，会出现「数据库是玩家、界面还是开发者」。
    独立数据库模式下「切换数据库」本身没有意义，直接拒绝并提示先改合并模式。
24. **预设改名要迁移在线绑定**：`sources.json`、云端/本地 manifest 缓存、UI 的
    `online_states` 都按预设名做 key；只改文件夹名，云端路径和分享链接会“消失”。
25. **进度回调来自工作线程**：`show_progress` 里所有 Tk 操作必须先 `ui_call`
    回主线程，否则进度条不刷新（异常还会被 try 吞掉，表现为“卡住”）。
26. **云端文件名不能只靠“原名”**：蓝奏对同名文件既可能改名、也可能存成两条同名
    记录（真机实测），玩家按名字找会拿到旧的那条。发布器现在给每次上传一个带
    内容指纹的唯一名（`name.<sha8>.ext`），manifest 用 `cloud` 字段记录它，下载器
    按 `cloud` 取、按 `path` 落盘；旧文件在 manifest 提交后按 **id** 清理（能清掉
    同名重复）。改发布/下载逻辑时别把这个字段丢了。
27. **`sources.json` 的读改写不要跨网络**：`_folder_of` 在 `ensure_path`（网络）
    之后重新 `get` 再写 `folder_id`，否则会用请求前的旧快照覆盖掉期间写入的
    分享链接/发布历史。

## v2.7.4 新增坑位（务必保留）

1. **侧边栏悬停不能用子控件 Enter/Leave**：Tk 的 crossing 事件被子控件吞掉，只在 `self.sidebar` 上绑定会出现“只有空白背景能展开”。现在用 root `<Motion>` + 指针坐标判定；展开/收起动画由 `sidebar_shell` 的宽度补间驱动。改动时不要退回只绑父控件。
2. **压暗工作区已移除**：`_dim_content` 遍历 CTk 控件换色会在 Linux 上卡 200ms，且 Windows 本来就不走这条路径；现在 `_show_dim()` 直接 return，侧栏靠边框/圆角区分层级。不要恢复黑色 Toplevel/逐控件压暗。
3. **CloudBrowser 不能有 `self._root`**：它会覆盖 Tkinter 的 `_root()` 方法，`winfo_children()`/`theme_widgets()` 直接 TypeError；字段名是 `_root_path`。
4. **`make_menu_button` 依赖 `popup_menu` 导入**：factory.py 必须 `from .popup import popup_menu`；否则所有“更多/上传”菜单静默失效。PopupMenu 的 host 可能是按钮，root 要从 `winfo_toplevel()` 取，不能假设 `host.root`。
5. **PopupMenu 外部点击**：root 的 `<Button-1>` 先于按钮 `<ButtonRelease>` 触发，`_on_click_outside` 必须先判断事件控件是否在 panel 内，否则菜单项永远点不中。
6. **SlideStack 初始化尺寸是 1×1**：`_on_configure` 必须把所有非当前页停到新视口外，不能只摆当前页；否则设置页首次打开会显示成“数据库”页（多页叠在 x=1）。
7. **CanvasSegmented 的 width/height/item_height 是“未缩放值”**：内部会乘 `px()`；新代码不要再传 `px(...)`，否则 125%/150% 下双倍放大。
8. **DND 测试必须用 `TkinterDnD.Tk()`**：`ctk.CTk()` 没加载 tkdnd，`drop_target_register` 会静默失败；产品 main() 已用 TkinterDnD.Tk。整卡拖拽要在状态行创建后再次 `_register_drop_tree(pack_group)`，并同时注册 CTk 控件的 `_canvas/_label`。
9. **设置页/管理页职责**：设置页只放偏好与数据库；管理页是全局预设操作区（总览、行内动作、快捷操作、云端文件、日志）。不要把上传/同步入口塞回设置页。
10. **角色兜底**：UI 隐藏按钮不够；`_publish_now`/`_run_publish`/`OnlineService.publish(role=...)` 都有开发者守卫，`_run_sync`/`open_sync_dialog` 有玩家守卫。新增入口必须走同一守卫。
11. **manifest 是 `.cfg` 后缀，内容是 JSON**：蓝奏真实账号实测拒绝 `.json/.toml/.yaml/.ini/.xml`，只接受 `.cfg`；所以只改后缀，解析仍走 `json`（快、只有一套结构）。新发布只写 `_pulses_manifest.cfg`，读取时兼容旧 `_pulses_manifest.txt`（JSON）。`manifest_sha256` 必须校验，`packed_sha256` 必须在解压前校验；不要把 `.cfg` 改成 INI 或别的结构，否则会多一套解析和校验分支。
12. **玩家同步默认完全同步**：`AppSettings.online_sync_clean` 默认 `True`，本地多余枪包默认勾选，`service.sync` 走 `Installer.remove_local()` → `trash.delete()`，优先进回收站。`online_sync_clean_set` 用来区分"旧版本默认 false"和"用户显式选了保留"；升级迁移时不要把显式 false 也改掉。设置页文案是「同步方式：完全同步 / 保留多余」。
13. **ScrollArea 不要 bind_all/unbind_all**：CTkScrollableFrame 自己也用 bind_all 绑滚轮；在 `<Leave>` 里 `unbind_all` 会把设置页/管理页/侧边栏的滚动一起解掉。现在每个 root 只装一次 `_scroll_wheel_dispatch`，按 `event.widget` 的 master 链找最近的 ScrollArea；不要退回按 Enter/Leave 动态绑定的写法。
14. **卡片滚动不要逐事件补间**：连续滚轮会不断 cancel/restart 150ms 补间，实际只挪一点，卡片一多就卡。现在 `ScrollArea.scroll_by()` 直接 `canvas.yview_moveto(target)`；滚动期间用模块级 `_SCROLL_ACTIVE_UNTIL` 暂停 hover 补间。Listbox 同理用原生 `yview_scroll`。
15. **启动先 withdraw 再 deiconify**：Tk 创建后默认会先映射小窗口；`main()` 现在先 `root.withdraw()`，`PulsesSwapApp` 建完、`update_idletasks()`、`_center_window()` 后再 `root.deiconify()`。不要在 UI 建好前提前显示窗口。
16. **旧版预设没有本地 manifest 也要能用**：`OnlineService.scan()` 每次都会扫描当前目录并 `save_local_manifest()`；如果 `.online/local/<preset>.json` 不存在，会现场算一份并落盘（日志可见）。不要改成“只读缓存、缺失就跳过”，否则老预设第一次检查会没有本地清单。
17. **并发下载每个线程一个 LanzouShare**：`LanzouShare` 内含 cookie、一次性令牌和 `_acw_done`，不能跨线程共用；`Downloader` 用 `threading.local()` + `clone()` 给每个线程独立会话。`ThreadPoolExecutor` 的 `workers` 默认 4，结果必须按输入顺序返回；`on_progress` 要按 `completed + in_flight` 聚合，别让每个线程各报各的。
18. **侧栏外壳只抬一次**：`sidebar_shell` 是 native Frame，`sidebar` 是里面的 CTkFrame；装配时 `sidebar_shell.lift()` 一次即可盖住 `content_col`。不要在每次 `_sidebar_expand()` 里重复 lift，会触发整栏重绘、把首帧动画拖慢。
19. **别再给侧栏加黑色 Toplevel 遮罩**：Windows/DWM 下 Toplevel 会先以不透明黑帧映射，再开始 alpha 补间，表现为闪黑/重绘。`_show_dim()` 现在直接 return；侧栏靠边框/圆角区分层级。`scale_check` 断言 `_sidebar_dim is None`。
20. **OverlayCard 要被宽度撑住**：CTkFrame 的 `width=680` 会被内容反向压成 322；现在 body 里放一条透明宽度撑条，卡片自然高度由内容决定。差异清单高度按条目数收缩，不要固定 260px。
21. **设置/弹窗的 wraplength 要 `px()`**：150% 下不缩放会在 620px 处提前换行，右边留一大块空白；`pages.py` 和 `dialogs.py` 已改为 `px(...)`。


## v2.7.5 新增坑位（务必保留）

1. **CTk 控件的真实事件目标不是 widget 本身**：`CTkLabel` 的鼠标事件落在内部 `_label`，`CTkButton` 在 `_text_label`，`CTkFrame` 在 `_canvas`。`CTkLabel.bind()` 返回 None 且可能只绑 Canvas，直接在文字上点会“没反应”。统一用 `pulses.widget.factory.bind_event()`；不要再写裸 `label.bind("<Button-1>", ...)`。
2. **`bind_event` 不能既绑 CTk 又绑内部 Label**：CTk 自己的 `bind()` 可能已经把回调挂到内部目标，重复绑会让 `DiffRow` 的勾选切换两次，看起来像没反应。`bind_event` 现在检测到内部目标时只绑内部目标。
3. **`Event.type` 是 `EventType` 枚举**：`str(EventType.Enter)` 是 `"7"`，不是 `"Enter"`。判断 crossing 要用 `event.type.name`；卡片 hover 之前用 `str(...) == "Enter"`，真实事件永远被当成 Leave。
4. **描边动画必须有宽度**：`border_width=0` 时改 `border_color` 完全不可见。卡片保留 1px 与底色相同的描边，flash/入场只改颜色，不改宽度，避免重排。
5. **侧栏收起后不要被 hover 立刻弹开**：点导航/登录导致收起时，指针还在侧栏里；必须记录 `_sidebar_leave_required`，等指针真正离开后再允许 hover 展开。否则点导航会“收起→弹开”循环。
6. **云端列表按需创建**：空态创建 `CTkScrollableFrame` 会让侧栏首帧多 100ms 以上绘制；`sb_cloud_scroll` 现在初始为 None，有行才创建，空态销毁。`_sidebar_cloud_rows` 只销毁行卡片，不能 `winfo_children()` 全销毁（会碰内部 Canvas）。
7. **隐藏页面不要重建管理列表**：后台检查每个阶段都重建隐藏的 `ManagePresetList`（8 行 CTk 控件）会白卡 200~400ms，正好卡在切页/侧栏动画上。`_refresh_preset_cards()` 只在 `active_page == "manage"` 时重建，否则置脏；进入管理页时强制刷新。
8. **并发下载进度回调可能乱序**：多个线程各自算 `completed + in_flight` 后回调，B 先报 200、A 后报 100 会让进度条倒退。`Downloader._run_parallel` 现在用 `progress_lock` 串行化回调并丢弃倒退值；不要移除。
9. **取消同步不能推进版本**：`Service.sync()` 取消时只装了一部分，`_finish(all_ok=...)` 必须同时考虑 `result.cancelled`；否则 index/manifest 会指向云端新版本，本地却不完整。`last_version`/`last_generation` 也只在 `all_ok` 时更新。
10. **长文案要截断/换行**：Toast 不设 `wraplength` 会撑到窗口外；Step1/侧栏/管理当前预设/详情标题/云端行都要 `ellipsize()`，否则 80 字预设名会压住状态或按钮。
11. **详情页签要显式选中**：`CanvasSegmented` 不会自动知道当前页；`open_preset_detail()` 在 `show(selected)` 后必须 `tab_bar.select(selected, animate=False)`，否则三个页签全是灰字。
12. **加载状态不要提前写“已加载”**：`load_pack()` 只把状态设为“加载中…”，`_on_presets_loaded_body()` 完成后再设“已加载”；失败时设“加载失败”。先写已加载会让用户以为线程卡死。

## v2.7.6 新增坑位（务必保留）

1. **Tk 窗口级动画不要逐帧改尺寸**：`root.geometry("WxH+x+y")` 每次改宽高都会让 Tk 重排整棵控件树；主界面控件多时每帧 20~40ms，动画会明显掉帧。`show_window()` / `_play_window_close()` 只改 `y` 和 `-alpha`，宽高始终等于最终矩形。`window_motion.pop_rect()` 虽然保留 `scale` 参数，但主窗口调用时传 `scale=1.0`。
2. **`winfo_width()` 在 withdraw 状态是 1**：`_center_window()` 不能直接拿它算居中，否则 1280 宽的窗口会按 1x1 的中心偏移到 `+742+1580`。现在 `w<=1 or h<=1` 时回退 `_initial_size`。
3. **窗口补间首帧要从第一帧开始计时**：`tween(..., start_on_first_frame=True)` 的 `start` 初始为 `None`，首次 `step()` 才取 `perf_counter()`。否则 UI 首次布局阻塞 200~400ms，补间会在第一次 `update()` 里直接跳到后半段，用户看到“突然半透明出现”。只给窗口级补间用这个参数；普通控件动画仍按调用时刻计时。
4. **`<Destroy>` 守卫只认宿主自己的销毁**：Tk 的 toplevel 会收到所有子控件的 `<Destroy>`；`_cleanup` 里判断 `widget.winfo_toplevel() is widget` 且 `event.widget is widget`，否则卡片回收会把窗口补间一起取消。
5. **开窗/关窗时暂停 Win11 不透明防护**：`_on_opacity_event` / `_opacity_tick` 在 `_window_animating` 为真时必须直接返回；否则 `<Configure>` / `<Map>` 回调里的 `make_window_opaque()` 会把 alpha 拉回 1.0，动画只剩位移。动画结束后再 `refresh_window_opacity()`。
6. **关闭动画必须先收束开窗动画**：用户刚打开就点关闭时，`_play_window_close()` 先调用 `_finish_window_open()` 取消 `window_open` 补间和 `_window_open_job`，否则两条补间同时写 geometry。
7. **不要用 `Toplevel` 做窗口缩放/旋转**：Windows/DWM 下 Toplevel 会先以不透明黑帧映射，再 alpha 补间，表现为闪黑；PCL 的旋转/缩放是 WPF 合成层能力，Tk 没有等价且稳定的实现。现在的方案是“下移 + 淡入/淡出 + 轻微回弹”，已够接近 PCL 的灵动感，且不牺牲布局性能。
8. **收窗要用“当前”矩形，不能套启动矩形**：用户可能移动/缩放过窗口。`_play_window_close()` 在 `_finish_window_open()` 后解析 `root.geometry()`，普通窗口从当前位置下移 18px 淡出；`zoomed/iconic/withdrawn` 只淡出、不写 geometry。用 `_window_final_rect` 会在关闭瞬间跳回启动位置；`window_anim_check` 有移动窗口后的回归断言。

## v2.7.8 新增坑位（务必保留）

1. **Tk 父容器不裁剪子控件**：幕布不能用一块全高 Frame 从 `y=h` 滑进来，否则下半截会盖住状态条/窗口底部；入场用 `height=h-y` 只覆盖工作区，出场用左右半幕缩窄宽度，不要移出 `page_host`。
2. **Canvas 没有透明背景**：不要用一整块 Canvas 做幕布，移开后露的是 Canvas 底色；这里用原生 Frame 做幕布，logo 单独放在与幕布同色的小 Canvas 上，靠同色融合。
3. **icon.png 自带深色圆角底**：直接贴图会出现方形/圆角拼接；`PageCover._load_logo()` 按亮度把背景 alpha 清零，再用 alpha>18 的 bbox 裁到 S/W 字形。换 logo 图时保持深底浅字，或同步改阈值。
4. **页面必须在幕布下切换**：`_page_covered()` 里先 `_apply_page()`（`stack.show(animate=False)` + settings/manage 刷新），再留 520ms 给布局；不要在幕布还没盖住时先切页面。
5. **快速连点不能叠动画**：覆盖阶段只记 `_page_pending`，盖住后一次到位；露布阶段的新目标在本轮 `_page_revealed()` 后再起一轮，不能同时开两条 reveal。
6. **logo 居中与留白**：字标中心固定 `h/2`，不要按整块文字组的视觉中心去偏；`PULSES 0 Studio · NimShade & DS` 固定在底部 `h-34`，不要塞进字标 Canvas 里，否则小屏会被挤到字标下方。

## v2.7.9 新增坑位（务必保留）

1. **字标不是 icon 贴图**：`PageCover._build_wordmark()` 用 `tkfont.Font.measure()` 逐字定位，`Pulses` 暖白、`Swap` 低饱和青，左侧细竖线；Canvas 底色与幕布同色，只有文字像素。不要把 `icon.png` 的 SW 块重新贴回来。
2. **字标居中按字标 Canvas 算**：`_logo_y()` 用 `h/2 - canvas_h/2`，字标 Canvas 内文字按中心排；底部 `PULSES 0 Studio · NimShade & DS` 固定在 `h-34`，不要塞回字标 Canvas。
3. **身份动画只包 UI 入口**：`_set_role_visual()` 负责 cover → `_set_role()` → 520ms → reveal；`_set_role()` 必须保持同步，`online_e2e`/后台/测试都直接调用它。不要把动画塞进 `_set_role()` 本身。
4. **身份幕布期间禁止切页**：`show_page()` 在 `_role_transition` 时直接返回；否则 page cover 的 `cancel()` 会取消 identity cover，`_role_transition` 永远悬着。
5. **页面幕布可见时身份切换退回即时**：`_set_role_visual()` 检测 `page_cover.visible`，避免第二条幕布抢同一个 Canvas/Frame；页面幕布结束后的身份切换才走完整动画。

## v3.0.0 WebView 迁移坑位（务必保留）

1. **不要重新引入 customtkinter 窗口**：新入口 `src/pulses_web_main.py` 只启动 PyWebView；`pulses/ui` 仅保留旧 2.x 回滚入口。核心模块仍 import customtkinter 是为了兼容旧核心，不是 UI 依赖。
2. **`js_api` 方法线程不安全**：官方说明它们运行在独立线程。所有修改型操作必须走 `pulses_web/events.py` 的 `JobRunner` 单写者队列；不要在 API 方法里直接改 PresetManager/OnlineService。
3. **事件只能从 EventPump 推**：worker 不得直接 `evaluate_js`；EventPump 合并进度、保留 seq，窗口关闭时安全退出。页面重载/窗口销毁时 evaluate_js 异常必须吞掉。
4. **DND 路径用 `pywebviewFullPath`**：Python `window.dom.document.events.drop += DOMEventHandler(..., prevent_default=True, stop_propagation=True)`；React 只负责拖拽覆盖层，不要依赖浏览器 `File.path`。
5. **本地资源走 HTTP**：PyWebView 相对路径自动启 server；不要用 file:// 直接加载 ES Modules/CSS，否则 CSP/CORS 和字体都可能失败。
6. **WebView2 Runtime**：Windows 安装器缺失时运行 Bootstrapper；绿色版必须提示用户安装 Evergreen Runtime。PyInstaller 要带 `pulses_web/web/dist` 和 webview 平台数据。
7. **改 UI 必须过两套测试**：Python 200 个测试 + `src/pulses_web/web/test-ui.mjs`；再跑打包启动冒烟。UI 截图放 `docs/web-ui/`。
