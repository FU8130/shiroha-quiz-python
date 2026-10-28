# Shiroha Quiz 终端版（Python 重写）

把原来网页版的刷题体验搬进终端，同时保留一个可以自己启动的本地网页版。
题库、进度、错题、收藏、复习记录全部存在项目目录里，不写注册表、不写用户目录，
整个文件夹拷到 U 盘上换台电脑接着用。

## 两个界面

- **终端界面（TUI）**：主力。`Start-Quiz.bat` 或 `python quiz.py`。
- **网页界面（GUI）**：本机浏览器打开，手机同一局域网也能打开。
  `python quiz.py --web`（默认只开在 127.0.0.1，局域网开关见下）。

两端共用同一份数据（`config/config.json`、`quiz_parser.data/`、`banks/`），
在一端刷的题，另一端立刻能看到。

## 快速开始

1. 装 Python 3.10+（或直接用目录里自带的 `python\python.exe`）。
2. 双击 `Start-Quiz.bat`。
3. 主菜单选「练习 / 考试 / 题库管理 / 记录 / 备份与恢复 / 间隔复习」。

零第三方依赖：只用标准库。`tools/7zr.exe` 是可选的（压缩 `.7z` 时才用到），
删掉不影响使用。

## 常用命令

<<<<<<< HEAD
```
python quiz.py                 # 终端界面
python quiz.py --web           # 网页界面（127.0.0.1:随机端口，自动开浏览器）
python quiz.py --web --lan     # 强制监听 0.0.0.0（局域网可访问）
python quiz.py --web --local   # 强制只监听 127.0.0.1
python quiz.py --dump-json     # 导出题库为 JSON
python quiz.py --version       # 版本号
=======
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
>>>>>>> branch 'main' of https://github.com/FU8130/shiroha-quiz-python.git
```

网页版想收口令：`python quiz.py --web --lan --token 你的口令`。
不带 `--token` 时局域网访问不需要口令（自己家网络可以这样用）。

## 目录结构

```
quiz.py                  入口（菜单、答题判定、命令行参数）
core/                    配置、状态、UI、云同步、间隔复习（FSRS）
views/                   练习、考试、题库、记录、看板、备份与恢复
gui/                     网页版服务端 + 前端静态文件
services/                题库列表、状态摘要等只读服务
quiz_parser/             题库解析（原仓库的解析器，基本未改）
plugins/                 菜单插件接口（PLUGIN_API = 1）
tests/                   自测脚本
tools/                   备份工具、可选的 7zr.exe
config/                  配置与密码（见下）
banks/                   题库 CSV
quiz_parser.data/        进度、历史、账号数据、同步日志
backups/                 本地备份、导出的云端副本
docs/                    设计、待办、变更记录、外网访问说明
```

## 数据放在哪

- `config/config.json` — 全部配置（界面、云端地址、同步策略、压缩档位…）
- `config/cloud.secret` — 云端密码（`plain:` 明文 / `dpapi:` 本机加密）
- `config/bank_counts.json` — 题库答题计数（只记相对路径）
- `config/cloud_sync.json` — 增量同步的「上次同步快照」
- `quiz_parser.data/` — 进度、历史、账号、`cloud_sync.log`
- `banks/` — 题库
- `backups/` — 本地备份、`cloud-deleted/`（云端删掉后在本地留的副本）

老版本散在根目录的 `config.json`、`cloud.json`、`ui.json`、`cloud.secret`、
`bank_counts.json` 会在启动时自动搬进 `config/`，原件留 `.bak.old`。

## 云端备份与同步

设置页（TUI：备份与恢复 → 云端；GUI：设置 → 云端备份）填 WebDAV 地址、
账号、密码、远端目录，连接测试通过后可用：

- **整体备份**：`shiroha-web-<内容哈希前12位>.json[.gz]`，内容寻址，同名即同一份，不会重复上传。
- **增量同步**：`manifest.json` + 每题库/进度一个 `.xz` 文件，只传变了的；
  本地删掉的会写墓碑（`deleted`），另一台设备不会把它「复活」回来。
- **冲突策略**：远端比本地新时怎么办——每次问（默认选覆盖）/ 直接覆盖 / 跳过本次，
  设置页可改，弹窗里勾「不再提示」也会改到这里。
- **旧格式**：早期 `shiroha-web-backup-日期-时间-哈希.json` 命名的备份仍可列出和恢复，
  但不再生成；设置页有「清理旧格式备份」和「只保留最近 N 份」两个按钮，都要再确认一次。

同步策略存在 `config/config.json` 的 `cloud.sync_*` 几个键里，终端版与网页版共用。

## 间隔复习（FSRS）

主菜单「间隔复习」按 FSRS-6 调度（21 个参数取官方默认值，不训练个人参数）：
每题评 1 重来 / 2 困难 / 3 一般 / 4 容易；新卡每天最多 20 张。
卡片数据存在 `quiz_parser.data/state.json` 的 `srs` 字段。

## 插件

`plugins/` 下放一个模块，实现 `register(app, menu)` 即可往主菜单加一项，
`PLUGIN_API` 版本对不上会被跳过。示例见 `plugins/example.py`。
有意没做「全方位插件化」——理由写在 `docs/TODO.md`。

<<<<<<< HEAD
## 测试

项目内 `tests/` 可直接跑（都不联网、不碰真实数据）：

```
cd tests
python -X utf8 test_lan_token.py    # 局域网口令：10 项，起临时服务器
python -X utf8 extreme_test.py      # 解析器极端输入：3 项
```

开发期的回归套件共 14 组 194 项（解析、状态、输入、统计、云快照、增量同步、
FSRS、配置迁移），跑在临时副本上，云同步用本地假 WebDAV，放在开发工作区里。

## 许可

GPL-3.0-or-later，全文见 `LICENSE`。参考过的开源项目、可选二进制
（`tools/7zr.exe`）的许可见 `NOTICE`。
=======
作为衍生部分重构作品，本项目继续采用 `GPL-3.0` 许可证；原项目版权归原作者及贡献者所有。
>>>>>>> branch 'main' of https://github.com/FU8130/shiroha-quiz-python.git
