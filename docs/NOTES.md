# quiz_py 备忘

## 已完成

- 解析：文本 / CSV / TSV / JSON / 双文件（题目+答案），脏引号与多行单元格可处理
- 练习：来源（全部/错题/收藏）、题型、分类/章节、自选题号、题量、顺序/随机、续做进度
- 考试：题量+限时、答题卡、交卷确认、未答提醒、成绩明细、错题重练
- 交互：进度条、答题卡、标记、跳过、单键命令（`/F` `/M` `/B` `/S` `/Q`）、颜色、自动下一题
- 题库：合并去重、重命名、删除、导出（JSON/CSV/TXT）、**编辑题目**（写回源文件）
- 数据：错题/收藏/错题次数**按题库隔离**；练习/考试历史含逐题明细
- 备份：导出 zip（题库+状态+历史）、从备份恢复（合并/覆盖，恢复前自动备份）
- 便携：题库标识与状态全部用**相对路径**；搬目录/换盘、删缓存重解析后错题仍能按题号恢复

## 未来可能要做：云端同步

> 当前故意不做。等要加时的设计备忘，避免重新踩坑。

### 最小可行范围

1. 远端存放：一个 zip（= 现有备份格式）或「按题库分文件 + 一个 state.json」
2. 操作：上传 / 下载 / 列表 / 恢复
3. 触发：手动即可，先不做自动后台同步

### 已经就绪的部分

- 备份包已经包含 `banks/` + `quiz_parser.data/state.json` + `history.json`
- 状态里带 `version`，可继续做迁移
- 题库键已是相对路径（`banks/A.csv`），可直接当云端路径用，与设备无关
- JSON 导入/导出可跨版本迁移题库
- `_restore_backup()` 已有「合并/覆盖 + 恢复前自动备份」流程，可复用

### 需要新写的部分

- WebDAV 客户端：`PROPFIND` 列目录、`PUT` 上传、`GET` 下载、`MKCOL` 建目录
  - 建议只用标准库（`urllib.request` + `xml.etree`）以避免引入依赖
  - 需要处理 401 / 403 / 507（空间不足）/ 超时
- 凭据：放环境变量或本地加密文件，**绝不写进题库或备份包**
- 完整性：上传/下载都算 SHA-256 + 字节数，下载后校验通过才替换本地
- 冲突策略（必须先定）：
  - 简单版：远端更新时间更晚才覆盖，否则提示「云端较旧」
  - 稳妥版：冲突时两份都保留（本地改名 `.conflict-时间戳`），由用户选择
- 失败回滚：下载到临时目录 → 校验 → 原子替换；失败保持原状
- 隐私：备份包含全部题目与错题记录，上传前提示用户确认

### 工作量估计

- 只做「手动上传/下载 + 校验」：约 250 行 + 测试，1 个依赖都不需要
- 再加冲突合并、增量同步、后台自动：复杂度翻倍，建议先不做

## 测试脚本

| 文件 | 覆盖 |
|---|---|
| `_quiz_selftest.py` | 主流程（导入/练习/考试/题库管理/备份/搜索） |
| `_keytest.py` | 单键命令与答题卡 |
| `_newfeat_test.py` | 自选题号、交卷确认、成绩明细、导出、历史明细 |
| `_stats_test.py` | 导出格式、错题次数、历史逐题 |
| `_cat_edit_test.py` | 分类筛选、题目编辑器 |
| `_pmove_probe.py` | 便携搬迁（复制目录后状态是否还在） |

（均在 `F:\PortableApp\DSH-Desktop\workspace\` 下，运行时会在临时副本里跑，不动真实题库。）
## 云端功能已预留的位置

- 入口：`备份与恢复` 菜单第 3 项 → `_cloud_placeholder()`
- 配置：`cloud.json`（模板 `cloud.example.json`），读取函数 `_load_cloud_config()`
- 约定：密码只走环境变量 `QUIZ_CLOUD_PASS`，不写进配置、题库、备份包
- 未实现：WebDAV 客户端、上传/下载、冲突处理；补后端时只改 `_cloud_placeholder`

## 代码结构（分阶段拆分后）

```
quiz.py            入口 + ShirohaQuiz 组合（约 8 KB）
core/
  ui.py            颜色/清屏/KeyReader/ask/退出
  paths.py         路径常量 + 便携路径换算
  state.py         状态持久化（错题/收藏/进度/记录）
  menu.py          菜单注册表
views/
  practice.py      练习/错题/收藏/搜索
  exam.py          考试
  banks.py         题库/导入/编辑/导出
  records.py       历史记录
  dashboard.py     统计与建议
  backup.py        备份/恢复/清数据/云入口
plugins/
  example.py       示例插件（register(app, menu)）
quiz_parser/       解析器（26 模块）
```

新增功能两种方式：
1. 改 `views/<模块>.py` + 在 `_build_menu()` 加一行；
2. 放一个 `plugins/xxx.py`，实现 `register(app, menu)`，无需改主程序。

## 云端同步（WebDAV）

- 配置：`cloud.json`（`url` / `user` / `remote_dir`），密码走环境变量 `QUIZ_CLOUD_PASS`
- 上传：内存打包为 `tar.xz`（LZMA preset 9 + EXTREME），适合有流量额度的网盘
- 下载：兼容 `.tar.xz` 与旧 `.zip`，恢复时覆盖题库与 `state.json`


## 自动同步（省流量）

- 触发：练习结束 / 考试结束 / 退出程序；启动时可选拉取
- 缓存：`quiz_parser.data/cloud_sync.json`（记录 sha256 与上次同步时间）
- 无变化时零请求；10 分钟节流；退出强制同步
- 开关：备份菜单 → 云端同步 → 7


## 便携迁移

- 密码文件 `quiz_parser.data/cloud.secret` 用 Windows DPAPI 加密，**绑定当前用户**；换设备会显示“本机解不开”
- 处理：新设备「云端同步 → 9 设置密码」重新输入一次即可
- 其余文件（`cloud.json`、`cloud_sync.json`、`cloud_sync.log`、题库）都是相对路径，可整目录拷走
