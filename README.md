# Shiroha Quiz（Python 重构版 · 零依赖）

Shiroha Quiz 是一个轻量、开源的刷题工具，支持自导入题库、练习、考试。

本仓库是原 [Shiroha Quiz](https://github.com/reiqr/shiroha-quiz) 的 **Python 重构版**，主要供作者个人自用。重构过程大量使用 AI 辅助完成，作者不是专业开发者，功能以"自己够用"为准，不保证完整复刻上游，也不承诺长期维护。

> [!IMPORTANT]
> - 本仓库**不是**上游官方版本，也**不包含、不参与、不维护 Android 原生版**。
> - 需要 Android 原生版请前往上游：[reiqr/shiroha-quiz](https://github.com/reiqr/shiroha-quiz/releases/latest)。
> - 主要供个人使用，Issue / PR 可能不会处理，请自行备份数据。

---

## 这是什么

- 用 Python 重写的刷题工具，**零第三方依赖**，只用 Python 标准库。
- 有 **TUI（终端）** 和 **GUI（本地网页）** 两个版本，功能共用同一套后端。
- 按个人习惯做的，功能不一定和上游一样全。
- 非官方，不代表上游项目。
- 重构用了 AI 辅助，功能对不对请自己先小范围试。

> 重要题库请定期备份。不建议直接用于高风险正式考试。

---

## 怎么用

### 第一步：装 Python

去 [python.org](https://www.python.org/downloads/) 下载安装。

- 建议 Python **3.10 或更新版本**（作者使用的是 3.14，其他版本未逐一测试）。
- Windows 安装时**一定要勾选** `Add Python to PATH`。

> 本项目**零依赖**，装好 Python 就能跑，不需要 `pip install`，不需要虚拟环境。

### 第二步：下载本项目

点页面右上角 `Code` → `Download ZIP`，解压到一个文件夹。

### 第三步：双击启动

- **想用终端界面（TUI）**：双击 `Start-Quiz.bat`
- **想用图形界面（GUI）**：双击 `Start-Quiz-GUI.bat`

GUI 版会启动一个本地网页服务器，浏览器会自动打开；没自动打开的话，看窗口里提示的地址手动访问。

---

## TUI 和 GUI 怎么选

| | TUI（终端） | GUI（本地网页） |
| --- | --- | --- |
| 启动 | `Start-Quiz.bat` | `Start-Quiz-GUI.bat` |
| 界面 | 终端菜单 | 浏览器网页 |
| 适合 | 快速刷题、习惯键盘操作 | 整理题库、看 PDF 题、需要公式渲染 |
| PDF 支持 | 无 | 有（前端 PDF.js） |
| 公式渲染 | 无 | 有（MathJax） |
| 夜间模式 | 按实际实现 | 有（`night.css`） |

> 两个版本共用同一套数据目录（`quiz_parser.data/`）和题库目录（`banks/`），可以随时切换。

---

## 功能概览

> 只保留实际能用的；没测过的别写。

- **题库导入**：CSV、Excel、TXT、JSON 等，支持"题目文件 + 答案文件"双文件导入。
- **解析能力**：题号/题干/选项/答案/解析/题型/分区识别，多空填空，集中答案区。
- **练习与考试**：随机练习、顺序练习、考试、错题、学习记录。
- **间隔复习**：内置 SRS 间隔复习（`core/srs.py`）。
- **备份**：本地自动备份（`backups/`），带清理脚本（`tools/prune_backups.py`）。
- **云同步**：WebDAV 云备份与恢复（`core/webdav.py`、`core/cloudsync.py`）。
- **插件**：`plugins/` 目录可放自定义插件。
- **GUI 额外**：PDF 解析、数学公式渲染、夜间模式、看板娘。

题库导入基本流程：

```text
上传 / 粘贴 → 自动解析 → 识别预览 → 人工核对 → 导入
