# WebDAV 同步改造 · 权威参考：Remotely Save 的同步算法

> 目的：给 Shiroha Quiz 的 WebDAV「增量 / 冲突 / 双向」做设计参考，避免自己拍脑袋翻车。
> 参考时间：2026-10-28。源码镜像在项目外：`F:\workspace\_ref\remotely-save-remotely-save-34db181`（不随项目备份，可随时删）。

---

## 一、为什么选它

| 项 | 值 |
|---|---|
| 插件 | Remotely Save（`manifest.json` → `id: remotely-save`，作者 fyears，版本 0.5.25） |
| 仓库 | `remotely-save/remotely-save`（`master`，提交 `34db181`） |
| 规模 | 8,270 star / 477 fork；2021-10-17 建仓，2024-11-10 最后提交 |
| 分发 | Obsidian 官方社区插件目录收录（`minAppVersion 0.13.21`），有移动端实现 |
| 备份后端 | S3 / Dropbox / OneDrive / **WebDAV** / Webdis（NextCloud、Synology、阿拉斯特、**坚果云**都有专门文档） |
| 与本项目交集 | 同样走 WebDAV、同样面对「坚果云」这类只给弱 WebDAV 的实现 |

选它的理由：它是 Obsidian 生态里 WebDAV 同步的事实标准，且**把算法写成了文档**，不是只丢一堆代码。
同类备选（不适合本项目）：`obsidian-livesync` 走 CouchDB 自建，是另一套模型；`obsidian-git` 走 git，与 WebDAV 无关。

---

## 二、许可边界（重要，决定能抄什么）

`LICENSE` 原文把仓库切成两半：

- `src/`、`tests/`、`docs/`、`assets/` → **Apache-2.0**（可自由借鉴、可引用）
- `pro/` → **PolyForm Strict 1.0.0**（源码可见，但**不能派生使用**）

而同步算法实现在 `pro/src/sync.ts`（2094 行）。所以：

- ✅ 可以引用它的**设计文档**：`docs/sync_algorithm/v3/design.md`（Apache-2.0，下面的决策表就出自这里）
- ✅ 可以引用它文档里提到的上游：**rclone bisync**（MIT）、syncrclone（MIT）、rsinc
- ❌ 不把 `pro/src/sync.ts` 的代码搬进本项目（连改写也要避免）

结论：**按文档里的决策表自己实现**。本文后面所有「判定公式」都是读代码后提炼的事实描述，不是代码复制。

---

## 三、核心数据结构：prevSyncRecord

Remotely Save v3 不再在云端放元数据文件，改为**本地记一份「上次同步成功时的状态」**：

```text
prevSyncRecord = { key, mtimeCli, mtimeSvr, sizeEnc }
```

- `key`：文件相对路径
- `mtimeCli`：上次同步后本机文件的修改时间（毫秒）
- `mtimeSvr`：上次同步后远端文件的修改时间（毫秒）
- `sizeEnc`：上次同步时的文件大小（若开了加密，是加密后大小）

存储位置：本地 IndexedDB，`src/localdb.ts` 里 `upsertPrevSyncRecordByVaultAndProfile` / `getAllPrevSyncRecordsByVaultAndProfile`；只在**同步成功**后写入，失败不写。

**为什么必须存两份时间**：WebDAV 上传后，远端 `getlastmodified` 常常不等于本地 mtime（服务器改写成自己的时间）。只比「远端时间 vs 本地时间」会永远判成"双方都改过"。所以要分别记住两侧上次的落点，才能判断"这一侧自上次以来变没变"。

---

## 四、判定逻辑（读 `pro/src/sync.ts:776-987` 提炼）

对每个 key，先取三方：`local`、`remote`、`prevSync`（可能 undefined）。

### 4.1 双方都存在

```text
# 完全相同
if (local.mtimeCli == remote.mtimeCli || local.mtimeCli == remote.mtimeSvr)
   且 local.sizeEnc == remote.sizeEnc                     → equal（branch 2，什么都不做）

# 否则先算"各自相对上次同步变没变"
localEqualPrevSync  = prevSync.mtimeCli == local.mtimeCli   且 prevSync.sizeEnc == local.sizeEnc
remoteEqualPrevSync = (prevSync.mtimeSvr == remote.mtimeCli 或 prevSync.mtimeSvr == remote.mtimeSvr)
                      且 prevSync.sizeEnc == remote.sizeEnc

只有 local 变  → push（branch 10）
只有 remote 变 → pull（branch 9）
两边都变      → 冲突：keep_newer 比 mtime（16/17）、keep_larger 比 size（18/19）、smart 走合并（301）
两边都没变    → equal（branch 21，属"时间戳把戏"导致的伪不等）
```

**关键点**：`prevSync` 不存在时，`localEqualPrevSync` 恒为 false —— 于是「双方都存在但都无历史」会被判成**双方都新建**，冲突分支 11/12（keep_newer）或 13/14（keep_larger）。

### 4.2 一侧缺失

```text
local 缺 且 remote 有：prevSync 存在 → 本机删了（删远端）；prevSync 不存在 → 远端新建（拉下来）
local 有 且 remote 缺：prevSync 存在 → 远端删了（删本地 / 或 conflict do nothing）；否则是本机新建（推上去）
两侧都缺 且只有 prevSync → 清历史（branch 1）
```

**这是最容易翻车的地方**：没有 prevSync 就分不清「新建」和「被删」，也正是本项目阶段 3 要补的根。

### 4.3 冲突策略（`conflictAction`）

- `keep_newer`：比 mtime，大者胜（默认，也是免费版）
- `keep_larger`：比 size，大者胜
- 免费版**没有** "keep both and rename"（v3 intro 里该条未勾选）；pro 的 `smart_conflict` 才做合并
- 我们的现状（`===autoMode` 时 `config.lastUploadSha===sha` 跳过）只解决"本机没变"，解决不了"远端被别的设备改过"

---

## 五、方向表（`docs/sync_algorithm/v3/design.md`，Apache-2.0，可直接引用）

双向：

| local \ remote | remote 未变 | remote 改过 | remote 已删 | remote 新建 |
|---|---|---|---|---|
| local 未变 | (02/21) 不做 | (09) 拉取 | (07) 删本地 | (??) 冲突 |
| local 改过 | (10) 推送 | (16~20) 冲突 | (08) 推送 | (??) 冲突 |
| local 已删 | (04) 删远端 | (05) 拉取 | (01) 清历史 | (03) 拉取 |
| local 新建 | (??) 冲突 | (??) 冲突 | (06) 推送 | (11~15) 冲突 |

只推（incremental push only，**对应本项目当前的"自动备份"**）：

| local \ remote | remote 未变 | remote 改过 | remote 已删 | remote 新建 |
|---|---|---|---|---|
| local 未变 | (02/21) 不做 | **(26) 冲突推送** | **(32) 冲突推送** | (??) 冲突 |
| local 改过 | (10) 推送 | **(25) 冲突推送** | (08) 推送 | (??) 冲突 |
| local 已删 | **(29) 冲突不做** | **(30) 冲突不做** | (01) 清历史 | **(28) 冲突不做** |
| local 新建 | (??) 冲突 | (??) 冲突 | (06) 推送 | **(23) 冲突推送** |

只拉（incremental pull only）：

| local \ remote | remote 未变 | remote 改过 | remote 已删 | remote 新建 |
|---|---|---|---|---|
| local 未变 | (02/21) 不做 | (09) 拉取 | **(33) 冲突不做** | (??) 冲突 |
| local 改过 | **(27) 冲突拉取** | **(24) 冲突拉取** | **(34) 冲突不做** | (??) 冲突 |
| local 已删 | **(35) 冲突拉取** | (05) 拉取 | (01) 清历史 | (03) 拉取 |
| local 新建 | (??) 冲突 | (??) 冲突 | **(31) 冲突不做** | **(22) 冲突拉取** |

> 注意"只推"这一列里 **(29)(30)(28)(32) 全是"冲突不做"**：本机删了、远端还在，推送方向**不删远端**，只提示。这正是本项目阶段 3 想要的"绝不覆盖较新副本"的直接依据。

---

## 六、执行流程（`pro/src/sync.ts` 的骨架）

1. `walk()` 三份清单：本地文件、远端文件、prevSync 记录
2. `ensembleMixedEnties()`：合并成 `key → {local, remote, prevSync, decision, decisionBranch, change}`
3. `getSyncPlanInplace()`：按第四节判定，产出 `change === true` 的清单
4. `splitFourStepsOnEntityMappings()`（`sync.ts:1237`）把操作**分四批**，顺序固定：
   1. `onlyMarkSyncedOps` — 只更新 prevSync（本节什么都没动但要对齐时间戳）
   2. `folderCreationOps` — 先建目录
   3. `deletionOps` — 再删除
   4. `uploadDownloads` — 最后传输
5. 每批用 `PQueue` 并发执行；全部成功后统一写 prevSync

**顺序不能乱**：先建目录才能放文件；删除放在传输之前，避免同级重命名时互相踩。

### 保护机制

- `modifyPercentage`：本次要改动的文件数 / 总文件数，超过阈值直接报错中止（`main.ts:269` `getProtectError`，`sync.ts:1780`）——防"误删一大片"
- `skipSizeLargerThan`：大文件跳过（本项目 26.6 MB 的整包就在这个维度上）
- 失败即 `markIsSyncing(false)`，不留中间态

---

## 七、对本项目的映射

| 我们的阶段 | 借鉴点 | 不照搬 |
|---|---|---|
| 阶段 1 内容寻址文件名 | 用它「先比 size/mtime 再传」的思路降级为「先由内容哈希算名，存在就跳」——WebDAV 上 HEAD 比算哈希便宜 | 它的文件名带时间戳，我们改成哈希前置 |
| 阶段 3 冲突防护 | 直接采用「只推」表的 (26)(25)(29)(30)(32)：远端较新就**跳过 + 提示**，后台绝不覆盖 | 不引入 IndexedDB，改用项目内 `quiz_parser.data/sync_state.json` 存 prevSync |
| 阶段 4 双向 | 采用第四节公式 + 四批执行顺序；pull 前先备份本机 | 不做 concurrency 队列（单线程顺序够用） |
| 阶段 5 方案 A 增量 | 把"文件"粒度定为**每个题库 CSV 一个 key**，题库本身就是整体覆盖写，文件级 prevSync 足够 | 不做分块（方案 B） |

### prevSync 落地建议

```json
{
  "version": 1,
  "profile": "jianguoyun-default",
  "records": {
    "banks/01_计算机技能高考完整题库.csv": {
      "mtimeCli": 1793000000000,
      "mtimeSvr": 1793000005000,
      "sha": "b21f8bd8..."
    }
  }
}
```

`sha` 是我们比 Remotely Save 多存的一项：WebDAV 上 mtime 不可靠（坚果云会把时间改成上传时刻），**内容哈希才是最稳的"未变"判据**。判定优先级：`sha 相等 → equal`，其次才看时间。

---

## 八、三条教训（比代码值钱）

1. **"上传成功" ≠ "同步完成"**。必须落盘 prevSync，否则下次仍然判不出"谁改过"。这正是本项目现在"自动同步其实是自动备份"的根因。
2. **没有历史就无法区分"新建"和"删除"**。首次同步必须显式建立基线（用户的题库已存在 → 视为基线，不要触发"删远端"）。
3. **时间戳在 WebDAV 上不可信**。判定顺序应是：内容哈希 → 大小 → 时间；只有前三者都不可用时才用时间兜底。
