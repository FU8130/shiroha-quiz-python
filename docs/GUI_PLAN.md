# GUI 套壳准备（阶段五）

> 状态：轻量准备已完成，正式开工定在周日
> 原则：复用原项目前端（`shiroha-quiz-main/apps/web`），只替换存储层；运行期零依赖

## 已就绪

| 项 | 位置 | 说明 |
|---|---|---|
| 纯业务函数 | `services/banks.py` | `list_banks()` / `state_summary()` / `dump()`，不打印、不读键盘 |
| 取数入口 | `python quiz.py --dump-json` | 输出 JSON，可直接给前端或脚本 |
| 版本入口 | `python quiz.py --version` | 便于打包/诊断 |
| 数据契约 | 本文第 3 节 | 前端字段 ↔ state.json 映射 |

## 1. 目标形态

```
quiz.py --web
  → 内置 http.server（静态 + /api/*）
  → webbrowser.open("http://127.0.0.1:<port>/")
  → 原前端 app.js 只替换 loadState/saveState/saveSilent 三个函数
```

零依赖：`http.server` / `json` / `webbrowser`。

## 2. 接口（第一版）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/banks` | 题库列表（key/name/count/size/mtime） |
| GET | `/api/state` | 首页需要的状态（active_bank、错题/收藏数、进度） |
| GET | `/api/bank/<key>` | 题目数组（后续做，需要解析器） |
| POST | `/api/answer` | 提交答案（后续） |
| POST | `/api/prefs` | 保存练习偏好（后续） |

第一版只做前两个 GET，先跑通静态资源 + JSON。

## 3. 数据契约

| 前端字段 | 当前来源 | 备注 |
|---|---|---|
| `bank.id` | `state.banks` 的 key（相对路径） | 前端用字符串 id，直接用相对路径即可 |
| `bank.name` | 文件名去扩展名 | |
| `bank.questions` | 解析器（未接入） | 第一阶段可先空数组 |
| `wrongEntries[].id` | 题目 id（uuid） | 与 TUI 一致 |
| `wrongBook` / `favorites` | `state.banks[key].wrong` / `.favorites` | 每库一份 |
| `records` | `quiz_parser.data/history.json` | |
| `prefs` | `state.prefs` | 练习/考试记忆默认值 |

## 4. 周日工作顺序

1. `http.server` + 静态目录（复制 `apps/web` 到 `web/`）
2. `/api/banks`、`/api/state`（复用 `services/banks.py`，几乎不用新代码）
3. 前端 `loadState` 改 fetch（先只读页面能显示题库）
4. 再考虑 `/api/bank/<key>`（接解析器）与写入接口
5. 打包（PyInstaller）另算

## 5. 风险

- `app.js` 667 KB 单文件，改存储层要精确定位三个函数
- 题库 id 用相对路径，改名后前端记录会断（TUI 侧已有内容哈希认领，GUI 需要同样逻辑）
- MathJax / pdf.js 是本地静态资源，注意相对路径
- 端口占用 → 用 0 让系统分配，再打开对应 URL
