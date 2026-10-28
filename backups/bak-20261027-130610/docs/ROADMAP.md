# 路线图（TUI + GUI 并行发展）

> 更新：2026-10-26 · 现状：TUI 功能与 web 版对齐，135 项回归全过

## 已完成基线

- 解析器 `quiz_parser/`（26 模块）+ 终端版 `core/` `views/` `plugins/`
- 功能：导入/练习/考试/错题/收藏/记录/搜索/统计/导出/备份
- 体验：数字答题、`#` 跳题、单键命令、答题卡、记忆默认值

## 阶段 A：抽服务层（并行发展的地基）

**目标**：业务逻辑只有一份，TUI 与未来 GUI 共用。

| 子项 | 交付物 | 验收 |
|---|---|---|
| A1 | `services/practice.py`：`PracticeSession`（current/submit/skip/jump/finish） | TUI 改调用它，135 项回归全过 |
| A2 | `services/banks.py`：`list_banks/load_bank/import_text/export` | 导入导出行为不变 |
| A3 | `services/stats.py`、`services/records.py` | 统计与记录数字一致 |
| A4 | `API_SCHEMA.md`：bank/question/wrong/record/prefs 字段契约 | 与现前端字段映射表 |

工期：1–2 天 · 风险：中（改核心路径，靠回归兜底）

## 阶段 B：单实例与并发（可选，先做轻量版）

| 子项 | 交付物 |
|---|---|
| B1 | `data/.lock` + 启动检测，防止双开写坏 |
| B2（可选） | 写前重读 + 乐观锁，允许 TUI/GUI 同时开 |

工期：0.5 天 · 风险：低

## 阶段 C：HTTP API（GUI 数据入口）

| 子项 | 接口 |
|---|---|
| C1 | `GET /api/state`、`GET /api/banks`、`GET /api/bank/<key>` |
| C2 | `POST /api/answer`、`POST /api/save`、`POST /api/prefs` |
| C3 | 静态文件服务（复用原 `serve.ps1` 思路，标准库实现） |

工期：0.5–1 天 · 风险：低（只读先行）

## 阶段 D：GUI 套壳（阶段五）

| 子项 | 内容 |
|---|---|
| D1 | 原前端 `loadState/saveState/saveSilent` 改为调 API |
| D2 | **零依赖**：内置 HTTP + `webbrowser.open` 打开系统浏览器；PyWebView 窗口作为可选 |
| D3 | 资源路径：MathJax / pdf.js / 图片 |

工期：1.5–2.5 天 · 风险：中（bankId ↔ 路径映射、相对路径）

## 阶段 E：打包（阶段六 · Windows）

| 子项 | 内容 |
|---|---|
| E1 | PyInstaller 打包（带 quiz_parser/core/views/services/static）；运行时零第三方依赖 |
| E2 | 绿色版目录结构 + `启动.bat` |
| E3 | 首次运行自检（数据目录、字体） |

工期：1 天 · 风险：中

## 阶段 F：云端数据（阶段四）

| 子项 | 内容 |
|---|---|
| F1 | WebDAV 客户端（PROPFIND/PUT/GET/MKCOL，仅标准库） |
| F2 | 冲突策略：远端更新优先 / 保留两份 |
| F3 | 凭据：环境变量 `QUIZ_CLOUD_PASS` |
| F4 | 上传/下载/校验（SHA-256）+ 失败回滚 |

工期：1–2 天 · 风险：中（冲突策略要先定）

## 阶段 G：安卓（阶段六，**可选 · 未承诺**）

| 子项 | 内容 |
|---|---|
| G1 | 系统 WebView + 本地 HTTP 服务（复用 C/D；仅在确定要做时启动） |
| G2 | 数据目录与导入导出适配（SAF） |
| G3 | 打包 APK（Chaquopy 或 Kivy+WebView 壳） |

工期：3–5 天 · 风险：高（存储权限、后台被杀）

## 里程碑

| 编号 | 定义 |
|---|---|
| M1 | services 抽完，TUI 行为不变（135 项全过） |
| M2 | HTTP 只读接口可访问题库列表 |
| M3 | GUI 能完整做一题（读题→作答→记录） |
| M4 | 打包成 exe，双击即用 |
| M5 | 云端上传/下载跑通 |
| M6（可选） | 安卓可安装使用，仅作预期 |

## 节奏建议

1. 每阶段结束：跑全量回归 + 打 `.bak` 备份
2. A 完成后先用 TUI 真实使用几天，再上 GUI
3. C 先只读，D 再做写操作，降低联调风险
4. B/F 可以与小版本并行（互不依赖）

## 当前优先级

```
A（服务层）→ C（HTTP）→ D（GUI 壳）→ E（打包）→ F（云端）→ G（安卓，可选）
```
B 可随时插入；G 依赖 D。


## 关于安卓的说明

安卓只是**预期**，不承诺。为它预留的只有两点，成本已经包含在主线里：

1. HTTP API 与界面无关（C 阶段天然如此）
2. 数据目录、导入导出路径保持可配置（已有 `core/paths.py` 集中管理）

因此不做安卓不会有任何返工；真要做时，G 阶段才需要新增工作。


## 依赖约定

- 运行期**只用 Python 标准库**：`http.server`、`json`、`webbrowser`、`pathlib`
- 不引入 npm / Electron / pywebview（PyWebView 可作为可选窗口壳）
- MathJax / pdf.js 使用原项目自带的本地静态文件
