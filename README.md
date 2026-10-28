# Shiroha Quiz（Python 部分重构版）

Shiroha Quiz 是一个轻量、开源的本地刷题工具，支持自导入题库、练习、考试、错题复习与云备份。

本仓库是原 [Shiroha Quiz](https://github.com/reiqr/shiroha-quiz) 的 **Python 部分重构版**，主要供作者个人自用。重构部分大量使用 AI 辅助完成，作者不是专业开发者，功能以“自己够用”为准，不保证完整复刻上游，也不承诺长期维护。

> [!WARNING]

> [!IMPORTANT]
> - 本仓库**不是**上游官方版本。
> - 主要供个人使用，Issue / PR 可能不会处理，请自行备份数据。

---

## 这是什么

- 用 Python 部分重写的刷题工具，**运行期零第三方依赖**，只用标准库。
- 有 **TUI（终端菜单）** 和 **GUI（本地网页）** 两个入口，共用同一套后端和数据。
- 便携设计：**整个文件夹拷走就能换电脑**，题库与状态全部用相对路径。
- 非官方，不代表上游项目。部分重构用了 AI 辅助，功能对不对请先小范围试。

> 重要题库请定期备份。不建议直接用于高风险正式考试。

---

## 和上游的关系

| 项 | 说明 |
| --- | --- |
| 上游项目 | [reiqr/shiroha-quiz](https://github.com/reiqr/shiroha-quiz) |
| 本仓库 | 上游的 Python 部分重构版，个人自用 |
| 前端来源 | GUI 复用上游 Web 版前端，仅替换存储层 |
| 许可证 | 继续采用 GPL-3.0 |

---

## 怎么用


1. **装 Python**：去 [python.org](https://www.python.org/downloads/) 下载安装。Windows 安装时**一定要勾选** `Add Python to PATH`。建议 Python 3.12 或更新（作者在 3.14 上开发）。
2. **下载本项目**：右上角 `Code` → `Download ZIP`，解压到一个文件夹。
3. **双击启动**，二选一：
   - 终端界面：双击 `Start-Quiz.bat`或者启动`quiz.py`
   - 网页界面：双击 `Start-Quiz-GUI.bat`（会自动打开浏览器）

**零依赖**：装好 Python 就能跑，不用 `pip install`，不用虚拟环境，不用 Node.js。MathJax、PDF.js 等前端资源已随包离线携带。

---

## TUI 和 GUI 怎么选

| | TUI（终端） | GUI（本地网页） |
| --- | --- | --- |
| 启动 | `Start-Quiz.bat 或者 quiz.py` | `Start-Quiz-GUI.bat` |
| 界面 | 终端菜单，键盘操作 | 浏览器网页 |
| 适合 | 专注刷题、单键操作 | 整理题库、公式渲染、夜间模式 |
| 公式渲染 | 无 | 有（MathJax，离线） |
| 夜间模式 | — | 默认夜间，侧栏可切日间 |
| 记忆设置 | 有 | 有（存 `state.json`） |

> 两端共用 `banks/` 和 `quiz_parser.data/`，随时可以切换，数据互通。

---

## 功能概览（有些功能GUI版本上暂时没有，因为还没有大改GUI）

**题库导入**
- 格式：文本、CSV / TSV、JSON，以及“题目文件 + 答案文件”双文件导入。
- 解析：题号、题干、选项、答案、解析、题型、分类 / 章节；脏引号、多行单元格可处理。
- 导入后可预览、按状态筛选、查找替换、批量删除、重新校验。

**练习与考试**
- 练习：来源（全部 / 错题 / 收藏）、题型、分类、自选题号、题量、顺序 / 随机、续做进度。
- 考试：题量 + 限时、答题卡、交卷确认、未答提醒、成绩明细、错题重练。
- 交互：进度条、答题卡、标记、跳过、单键命令、颜色提示。

**间隔复习**
- 基于 FSRS-6 调度，四档评分，今日到期、单卡重置 / 暂停、30 天预测。
- 学习步长、每日上限、Leech 暂停、撤销上一题。

**题库管理**
- 合并去重、重命名、删除、导出（JSON / CSV / TXT）、题目编辑写回源文件。
- 错题、收藏、错题次数**按题库隔离**；改名或搬目录后靠内容哈希自动认领。

**备份与云同步**
- 本地导出 zip 备份、从备份恢复（合并 / 覆盖），恢复前自动备份。
- WebDAV 云同步：上传 / 下载 / 远程列表 / 恢复；增量同步只传变化文件。
- 自动同步可选（默认关闭，不静默上传）；密码可选 DPAPI 加密或明文便携保存。


---

## 数据与备份

| 位置 | 内容 |
| --- | --- |
| `banks/` | 题库文件 |
| `quiz_parser.data/` | 运行状态、缓存、日志、云同步缓存 |
| `quiz_parser.data/state.json` | 错题、收藏、进度、偏好（v2，带自动迁移） |
| `quiz_parser.data/cloud.secret` | WebDAV 密码 |
| `config.json` | 统一配置 |
| `backups/` | 自动备份（改动前快照） |

建议：

- 导入题库后先导出一份备份。
- 换电脑、重装系统前先备份 `banks/` 和 `quiz_parser.data/`。
- 旧备份清理默认**送回收站**，只有超大文件才直删，误删可还原。
- `.portable-root` 记录上次所在盘符，换盘时只提示、不阻止启动。

---

## 目录说明

```text
quiz_py/
├── Start-Quiz.bat          # TUI 启动
├── Start-Quiz-GUI.bat      # GUI 启动
├── quiz.py                 # 主入口（含 --version / --dump-json / --web）
├── config.json             # 统一配置
├── core/                   # 状态、路径、UI、WebDAV、SRS、安全写入
├── views/                  # TUI 各页面
├── services/               # 纯业务函数（TUI / GUI 共用）
├── gui/                    # 本地 HTTP 服务 + 前端静态资源
├── quiz_parser/            # 题库解析器（26 模块）
├── plugins/                # 菜单插件（register(app, menu)）
├── tools/                  # 备份 / 清理 / 7zr.exe
├── banks/                  # 题库
├── backups/                # 自动备份
└── quiz_parser.data/       # 运行状态、缓存、日志
```

---

## 当前状态

- 版本：**v0.10.x**
- TUI 功能已与上游 Web 版基本对齐；GUI 正在补齐 SRS、搜索、统计等页面。

> 具体变更见 `docs/CHANGELOG.md`，设计备忘见 `docs/NOTES.md`、`docs/ROADMAP.md`。

---

## 维护说明

本项目主要供作者个人使用，公开只为留档和换设备方便：

- 不保证功能完整，也不保证和上游兼容。
- 不保证处理 Issue / PR。
- 不保证数据格式稳定。
- 使用前请自行备份，出问题请先看备份。

---

## 致谢与许可证

基于 / 参考原项目 [reiqr/shiroha-quiz](https://github.com/reiqr/shiroha-quiz) 部分重构。

感谢原项目作者及贡献者：

- [@jiesou](https://github.com/jiesou)
- [@anupamme](https://github.com/anupamme)

以及原项目其他贡献者。本仓库仅维护 Python 部分重构实现。

作为衍生部分重构作品，本项目继续采用 `GPL-3.0` 许可证；原项目版权归原作者及贡献者所有。
