# stock-detect AI 定时任务说明：`stock-detect-ai-analysis`

> 本文档记录 **AI 舆情分析定时任务**（每周日跑一次）的真实配置，是「谁在什么时候、用什么 Prompt、把什么结果推到哪」的权威说明。
>
> **2026-09-13 起**：本任务已从服务器 OpenClaw cron 迁移到 **Mac mini 的 WorkBuddy 定时任务（Automation）**。旧的服务器 OpenClaw job（ID `7fe436cb-8d7a-42cd-a135-855c115f7310`）应停止/禁用，避免双跑。
>
> 任务**分析规范**（Ticker 映射、态度分级、雪球转发规则、断点字段等）见 [`AI_ANALYSIS.md`](AI_ANALYSIS.md)；本文档只描述**调度与运行时配置**，两者配合阅读。

---

## 一、任务概况

| 项 | 值 |
|----|-----|
| 任务名 | `stock-detect-ai-analysis` |
| 执行方 | WorkBuddy 定时任务（Mac mini），Automation ID `automation-1789234724917` |
| 显示名 | 「stock-detect 每周 AI 舆情分析（周日）」 |
| 状态 | ACTIVE（启用） |
| 会话 | 独立会话（每次触发新建，不复用历史上下文） |
| 可用工具 | 读文件、写文件、执行 shell、联网检索（WorkBuddy 默认能力） |
| 结果投递 | 分析后推 Bark 汇总到手机；任务本身在 WorkBuddy 内产出文字汇报 |
| 使用模型 | WorkBuddy 默认模型 |

## 二、调度时间

| 项 | 值 |
|----|-----|
| 调度表达式 | `FREQ=WEEKLY;BYDAY=SU;BYHOUR=11;BYMINUTE=1` |
| 时区 | 本机本地时区（GMT+8，等同 Asia/Shanghai） |
| 实际含义 | **每周日 11:01（北京时间）运行一次**，覆盖上一周的帖子 |
| 增量窗口 | 通常为近 7 天（因每周只跑一次） |

> 与其它定时任务的时间关系：
>
> | 任务 | 时间（北京） | 类型 |
> |------|--------------|------|
> | X/雪球舆情**抓取** `scan-mysql.yml` | 每周六 17:40 | GitHub Actions |
> | **AI 舆情分析** `stock-detect-ai-analysis` | **每周日 11:01** | **WorkBuddy（Mac mini 本任务）** |
> | 财报提醒 `earnings.yml` | 周一~周五 08:00 | GitHub Actions |
> | IPO 打新 `ipo.yml` | 周一~周五 09:00 | GitHub Actions |
>
> 先由周六 CI 抓取入库，周日读库做语义分析，顺序是先抓后析。
>
> 注：原服务器 OpenClaw cron 为 `30 11 * * 0`（11:30）。迁移到 WorkBuddy 时按「AI 定时任务统一 :01 错峰」的既有约定，对齐为 11:01。

## 三、任务行为（运行时 Prompt）

以下是 WorkBuddy 定时任务每次触发时下发的 Prompt 原文：

````text
请执行 stock-detect 每周 AI 舆情分析定时任务（每周日 11:01 北京时间运行一次，覆盖上一周的帖子）。

运行规范：
1. 先读取最新版任务文档：`/Users/rainlu/Documents/work/stock-detect/AI_ANALYSIS.md`。
2. 严格按文档「二、定时自动执行」中的系统 Prompt 和用户 Prompt 执行，不要使用旧记忆里的版本覆盖文档。
3. 仓库路径：`/Users/rainlu/Documents/work/stock-detect`，运行前 `cd /Users/rainlu/Documents/work/stock-detect`。
4. 环境变量文件：`/Users/rainlu/Documents/work/stock-detect/.env`；Python 脚本会从项目根 `.env` 读取 `MYSQL_PASSWORD`。
5. Python 虚拟环境：`/Users/rainlu/Documents/work/stock-detect/.venv`；执行 Python 命令时优先使用 `.venv/bin/python`。
6. 当前 UTC 请用实际运行时刻替换文档中的 `{{NOW_UTC}}`。
7. 账号、batch_limit、prompt_version、Ticker 规则、股票-only 边界等全部以 `AI_ANALYSIS.md` 最新内容为准。
8. 本任务每周一次，增量窗口通常覆盖近 7 天帖子；若单批上限不足以跑完，请按文档断点续跑规则处理，并在汇报中说明 remaining_estimate。
9. 完成后返回每个账号的 run_id、status、checkpoint、remaining_estimate、summary。汇报标题请使用「stock-detect 每周 AI 舆情分析 — YYYY-MM-DD」。

10. **分析完成后推送 Bark 汇总（必做）**：四个账号全部分析完、断点写好之后，执行一次汇总推送脚本：

```bash
cd /Users/rainlu/Documents/work/stock-detect && .venv/bin/python scripts/stock_detect_bark_summary.py
```

- 该脚本自己读 MySQL，取每个定时账号最近 14 天内的最新 run，按「提及帖数」挑重点股票，组装一条汇总消息推到 Bark。重点是**被提及次数多的股票**，不是新增股票。
- 只需运行这一条命令，不要自己拼 Bark 请求、不要用 curl 手动推送。
- 如果脚本输出「最近 N 天内没有 AI run」或「本次没有任何 ticker 数据」，说明本周确实无内容，属正常，不要重试也不要报错。
- 脚本失败（非零退出）时，在汇报里注明 Bark 推送失败及原因，但不影响 AI 分析本身的成功判定。
- 汇报中附上脚本打印的推送内容那一行，方便核对。
````

### 行为拆解

1. **读规范**：以 `AI_ANALYSIS.md` 为唯一分析规范（Prompt 里不重复规则原文，避免规则漂移）。
2. **增量分析**：对 4 个定时账号（`aleabitoreddit`、`mingchikuo`、`xueqiu:1247347556`、`xueqiu:1102105103`）按断点增量分析，写入 4 张 AI 表。
3. **写断点**：必须写 `resume_from_*` 与 `checkpoint_*`，保证下次可续跑。
4. **Bark 汇总推送**：分析完成后运行一次 `stock_detect_bark_summary.py`，按「提及帖数」挑重点股票推 Bark。
5. **WorkBuddy 汇报**：回传每个账号的 `run_id / status / checkpoint / remaining_estimate / summary`，标题为「stock-detect 每周 AI 舆情分析 — YYYY-MM-DD」。

固定运行环境：仓库 `/Users/rainlu/Documents/work/stock-detect`，虚拟环境 `.venv`，密码从 `.env` 的 `MYSQL_PASSWORD` 读取。

## 四、Bark 汇总脚本

| 项 | 值 |
|----|-----|
| 路径 | `scripts/stock_detect_bark_summary.py`（**已纳入本仓库**，从服务器迁移而来，路径/中文名来源改为 Mac mini 本地） |
| 触发 | 本任务第 10 步，四账号分析完成后固定执行一次 |
| 数据来源 | 自行读 MySQL，取每个定时账号**最近 14 天内**的最新 run |
| 选股逻辑 | 按「**提及帖数**」挑重点股票（不是新增股票） |
| 中文名 | 实时解析 `GolangCalculateServer` 的 `search.go` / `stock_detect_chinese_names.go`（与 stock-detect 同级目录） |
| 推送断点 | `.workbuddy/state/stock_detect_bark_state.json`，按 run_id 去重，避免重复推送 |
| 输出 | 组装一条汇总消息，推送到 Bark（`stock-detect` 分组） |
| 空数据 | 输出「最近 N 天内没有 AI run / 本次没有任何 ticker 数据」属正常，不重试、不报错 |
| 失败处理 | 非零退出时在汇报中注明失败及原因，**不影响** AI 分析的成功判定 |

## 五、运维与排查

- **任务配置**：WorkBuddy「自动化」列表里名为「stock-detect 每周 AI 舆情分析（周日）」，可在其中查看/修改调度与 Prompt。
- **手动补跑**：`AI_ANALYSIS.md` 第三章「三、本地手动执行」（同一任务、同一断点、同一四表，只是 Agent 换成交互式会话）。
- **Bark 汇总单独重跑**：`.venv/bin/python scripts/stock_detect_bark_summary.py --force`（忽略断点重推）或 `--dry-run`（只打印不推送）。
- **改调度/改 Prompt**：在 WorkBuddy 自动化里编辑即可，改完确认下次触发时间正确。

## 六、变更记录

| 日期 | 变更 |
|------|------|
| 2026-09-13 | 从服务器 OpenClaw cron（`7fe436cb...`，周日 11:30）迁移到 Mac mini WorkBuddy 定时任务（周日 11:01）；Bark 汇总脚本纳入本仓库 `scripts/stock_detect_bark_summary.py`，路径、中文名来源、断点位置改为 Mac mini 本地。 |
