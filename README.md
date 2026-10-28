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

```
python quiz.py                 # 终端界面
python quiz.py --web           # 网页界面（127.0.0.1:随机端口，自动开浏览器）
python quiz.py --web --lan     # 强制监听 0.0.0.0（局域网可访问）
python quiz.py --web --local   # 强制只监听 127.0.0.1
python quiz.py --dump-json     # 导出题库为 JSON
python quiz.py --version       # 版本号
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
