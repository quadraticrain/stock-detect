# stock-detect 每日 AI 舆情分析（openclaw-v5.5）

> **这是同一个定时任务**——从 MySQL 增量读 X 推文 → 语义分析 → 写入四张 AI 表 → 保存断点。  
> 区别仅在于 **由哪个 AI Agent 执行**：
>
> | 执行方式 | Agent | 适用场景 | 跳转到 |
> |----------|-------|----------|--------|
> | **OpenClaw 定时（生产）** | OpenClaw | 每天北京时间 13:00 自动跑 | [二、OpenClaw 自动执行](#二openclaw-自动执行) |
> | **本地手动** | Cursor / WorkBuddy / 任意 AI + 脚本 | 排障、补跑、验收 | [三、本地手动执行](#三本地手动执行) |
>
> 任务逻辑、断点机制、Ticker 映射、态度分级对两种方式 **完全相同**。  
> 与关键词报告的区别：GolangCalculateServer `/api/stock-detect/report` 使用死板词表；**本任务做自然语言语义分析**。

**版本变更（v5.5）**：定时账号为 3 位：`aleabitoreddit`, `elonmusk`, `mingchikuo`（已移除发帖量过低或长期无更新的账号）。

---

## 一、任务背景（共用）

从 MySQL `cache_data` 库的 `stock_detect_x_posts` 表 **增量** 读取 X/Twitter 推文，做语义级 Signals / Consensus / Top Tickers 分析，写入 4 张 AI 表，并持久化断点供下次续跑。

> **重要原则（v5.6 语义优先）**：本任务是 **AI 语义分析任务**，不要把语义判断下沉成 Python/SQL 关键词规则或机械化脚本。脚本只负责 MySQL 读写、断点、幂等与 JSON 组装；`recommendation`、`confidence`、`reasoning`、Ticker 是否应映射，必须尽量由 AI 直接阅读 `stock_detect_x_posts.text` 原文后判断。代码可以用于分页、格式化、去重、候选检索和写表，但不能替代 AI 对近义词、反讽、上下文、行业语境、公司/产品歧义的理解。

| 表 | 用途 |
|----|------|
| `stock_detect_ai_runs` | 每次 run 的元数据 + 断点（resume_from / checkpoint） |
| `stock_detect_ai_signals` | 逐帖逐 ticker 的 recommendation(buy/hold/sell/neutral) + reasoning |
| `stock_detect_ai_consensus` | 按 (日期, ticker) 聚合的共识信号 |
| `stock_detect_ai_top_tickers` | 按 run 排名的热门 ticker |

**定时账号**（与 GitHub Actions `scan-mysql.yml` 一致）：`aleabitoreddit`, `elonmusk`, `mingchikuo`。

**停止关注账号**：`sunyuchentron` / `justinsuntron` 已从后续抓取和 AI 定时关注范围移除。基于过去 180 天数据，该账号几乎只讨论加密货币，不符合本项目股票-only 范围；MySQL 旧数据保留，不做清理。

### 增量断点规范（两种 Agent 均须遵守）

1. **启动前读断点**：从 `stock_detect_ai_runs` 读取该账号上一次成功结束的 `checkpoint_*`，作为本次 `resume_from_*`。
2. **只处理新数据**：仅处理断点之后的帖；禁止重复分析已在 `stock_detect_ai_signals` 出现过的 `post_id`。
3. **结束时写断点**：正常结束或达单批上限时，写入 `resume_from_*` 与 `checkpoint_*`。
4. **状态字段**：`completed`（已追上最新帖）| `partial`（本批打满仍有剩余）| `failed`（不随意推进断点）。
5. **排序键**：`(created_at ASC, post_id ASC)`，保证断点可复现。
6. **幂等**：同一 `run_id` 先 DELETE 再 INSERT；同一 `post_id` 不跨 run 重复分析。

断点字段：

| 字段 | 说明 |
|------|------|
| resume_from_post_id / resume_from_created_at | 本批起始 |
| checkpoint_post_id / checkpoint_post_created_at | 本批结束（下次从这里继续） |

表结构由 `stock_detect/tweet_cache.py` / `scripts/ai_analysis_helper.py sync` 自动维护。

### 分析账号要点

| 账号 | 类型 | AI 分析要点 |
|------|------|-------------|
| `aleabitoreddit` | 半导体/AI 基础设施投资博主 | 显式 `$TICKER` 为主。**主题篮子**：Neocloud（NBIS/CRWV/IREN/WULF/CIFR…）、InP 光子学（AXTI/LITE/COHR…）、国防无人机（AIRO/OSS/AVAV）、委内瑞拉（GRZ/CVX…）、算力连结（ALAB/CRDO/MRVL/AVGO/TSM…）。篮子内未点名成员也给 neutral context。 |
| `elonmusk` | Tesla/SpaceX/xAI | 少见显式 `$TICKER`。**SpaceX/xAI/Starlink/Grok → SPCX**（2026-06-12 IPO），同时给 TSLA 次要传导。Optimus/Neuralink → TSLA。TSMC → TSM；BTC/DOGE 加密提及 → 对应 crypto ticker。 |
| `mingchikuo` | 苹果供应链分析师 | 聚焦 **AAPL** 及供应链（TSM、QCOM 等）。以正文点名公司或 `$TICKER` 为主；无明确标的不臆造。 |

### Ticker 识别（6 类映射，按强度递减）

- **A 显式 cashtag**：正文 `$TICKER`，直接取用。
- **B 公司名 → ticker**：Nebius→NBIS、Tesla→TSLA、SpaceX/xAI/Starlink→**SPCX** 等。
- **C 未上市实体传导**：Optimus/Neuralink → TSLA（confidence 衰减）。
- **D 行业主题篮子**：Neocloud、InP、国防、委内瑞拉、加密等（见 aleabitoreddit 历史帖）。
- **E 供应链语境**：客户/供应商提及 → neutral context。
- **F 不映射**：泛用词、纯社交、无公司指向的通稿。

### 态度分级（7 级 → recommendation 四值）

| 态度 | recommendation | confidence | 特征 |
|------|---------------|------------|------|
| 最高信念多头 | buy | 0.75–0.9 | Strong Buy、highest conviction、大额持仓+目标价 |
| 战术性买入 | buy | 0.6–0.75 | dip buy、Fire Sale、具体价位 |
| 主题性看好 | buy | 0.55–0.7 | 行业 thesis 看好 |
| 持有/维持 | hold | 0.5–0.6 | Hold、无增减仓 |
| 战术性卖出 | sell | 0.55–0.65 | 获利了结、换仓 |
| 结构性看空 | sell | 0.6–0.7 | huge warning、debt trap |
| 中性/语境 | neutral | 0.35–0.5 | 仅对比/供应商提及 |

**elonmusk 校准**：confidence 整体下调 0.1；里程碑事件才给 TSLA buy 0.55+；纯社交 → neutral 0.4。

**硬性规则**：reasoning 中文；summary 末尾带「仅供参考，非投资建议」；`prompt_version` 固定 `openclaw-v5.5`；时间 UTC。

### 股票-only 边界

本项目关注 **股票/上市公司/可交易股票 ETF**，默认不分析加密货币本身。

- 加密货币、稳定币、链上 token、memecoin、交易所上币、链上治理票据等（如 BTC/ETH/TRX/USDT/USDD/WLFI 等）不要写入 AI signals。
- 若博文提到加密支付、链上基础设施或 Web3 产品，同时明确出现上市公司（如 Mastercard、Google、Coinbase、Robinhood、MicroStrategy 等），只可对对应股票 ticker 写入信号。
- 这类股票信号通常是业务/合作/供应商语境，若没有明确业绩、估值、股价或投资观点，推荐写 `neutral`，并在 reasoning 里说明“已排除加密资产，仅保留股票语境”。
- 不要因为出现 `$TRX`、`Bitcoin`、`stablecoin`、`token` 等加密关键词而映射股票；也不要把加密 token 伪装成股票 ticker 写入。

---

## 二、OpenClaw 自动执行

### 调度配置

| 项 | 值 |
|----|-----|
| 任务名 | `stock-detect-ai-analysis` |
| 执行时间 | 每天 **北京时间 13:00**（建议在 CI 抓取 09:00 之后） |
| 时区 | `Asia/Shanghai` |
| Cron | `0 13 * * *` |
| 环境变量 | `MYSQL_PASSWORD`（必填） |
| 单批上限 | 300–500 帖/账号/次 |

将下方 **系统 Prompt** 与 **用户 Prompt** 复制到 OpenClaw 即可。

### 系统 Prompt（System）

> 复制到 OpenClaw 时，请使用下方完整块（已内嵌分析规则，无需再引用其他文件）。

```
你是 stock-detect 项目的 AI 舆情分析师。你连接 MySQL，按**增量断点**读取 X 推文，做语义级 Signals / Consensus / Top Tickers 分析，写入 4 张 AI 表，并在结束时**必须**保存 checkpoint 供下次定时任务续跑。

## 增量断点（核心，不可省略）

### 启动：读取上次断点

```sql
SELECT run_id, checkpoint_post_id, checkpoint_post_created_at, status
FROM stock_detect_ai_runs
WHERE account = :account
  AND status IN ('completed', 'partial')
  AND checkpoint_post_id IS NOT NULL
ORDER BY analyzed_at DESC
LIMIT 1;
```

- 若无历史行 → 全量首次：`resume_from_*` 置 NULL
- 若有 → 本批 `resume_from_post_id` = 上次的 `checkpoint_post_id`

### 选取本批待处理推文

```sql
SELECT post_id, author, text, created_at, score, url, tickers, source
FROM stock_detect_x_posts
WHERE author = :account
  AND source <> 'ci_marker'
  AND post_id NOT LIKE '###CI_SCAN_%'
  AND (
    :resume_from_created_at IS NULL
    OR created_at > :resume_from_created_at
    OR (created_at = :resume_from_created_at AND post_id > :resume_from_post_id)
  )
  AND post_id NOT IN (
    SELECT DISTINCT post_id FROM stock_detect_ai_signals WHERE account = :account
  )
ORDER BY created_at ASC, post_id ASC
LIMIT :batch_limit;
```

`batch_limit` 默认 400。

### 结束：写入断点（stock_detect_ai_runs 必填）

| 字段 | 说明 |
|------|------|
| resume_from_post_id | 本批起始帖 ID |
| resume_from_created_at | 本批起始时间 |
| checkpoint_post_id | 本批最后成功分析的帖 ID |
| checkpoint_post_created_at | 上述 created_at |
| status | completed 或 partial |
| post_count | 本批实际分析帖数 |

**禁止**只写 summary 不写 checkpoint。

### Consensus / Top Tickers

- 本批只 INSERT 新帖的 signals
- Consensus、Top Tickers 按账号全窗口重算后写入本次 run_id

## Ticker 识别（6 类映射）

A 显式 $TICKER；B 公司名→ticker（SpaceX/xAI/Starlink→SPCX，Tesla→TSLA）；C 未上市实体传导（Optimus→TSLA）；D 行业主题篮子（Neocloud/InP/国防/委内瑞拉/加密）；E 供应链语境；F 不映射（泛用词、纯社交）。

## 态度分级

buy/hold/sell/neutral 四值；confidence 0.35–0.9。elonmusk confidence 整体下调 0.1；SpaceX 提及→SPCX 主信号 + TSLA 次信号。reasoning 中文；summary 末尾「仅供参考，非投资建议」。prompt_version: openclaw-v5.5

## 执行步骤（每账号）

1. 读 checkpoint → 定 resume_from
2. SELECT 本批新帖（LIMIT batch_limit）
3. 生成 run_id：`YYYYMMDDTHHMMSSZ_ai_{account}`
4. 逐帖分析 → INSERT signals
5. 全窗口聚合 → INSERT consensus + top_tickers
6. INSERT ai_runs（含 checkpoint 四字段 + status）
7. 输出 JSON 摘要
```

### 用户 Prompt（User，每次定时触发）

```
执行 stock-detect 每日 AI 舆情分析（openclaw-v5.5，增量断点续跑）。

- 账号列表：aleabitoreddit, elonmusk, mingchikuo
- mode：incremental（默认）
- batch_limit：400
- 当前 UTC：{{NOW_UTC}}
- prompt_version：openclaw-v5.5

对每个账号依次：
1) 读 stock_detect_ai_runs 最新 checkpoint
2) 只 SELECT 断点之后、且未在 ai_signals 出现过的 post_id
3) 分析并写入四表
4) 必须写入 resume_from_* 与 checkpoint_*

完成后返回各账号 run_id、status、checkpoint、remaining_estimate、summary。
```

### SQL 示例与验证

```sql
-- 读断点
SELECT checkpoint_post_id, checkpoint_post_created_at, status
FROM stock_detect_ai_runs
WHERE account = 'elonmusk' AND checkpoint_post_id IS NOT NULL
ORDER BY analyzed_at DESC LIMIT 1;

-- 确认无重复分析
SELECT post_id, COUNT(DISTINCT run_id) AS runs
FROM stock_detect_ai_signals
WHERE account = 'elonmusk'
GROUP BY post_id
HAVING runs > 1
LIMIT 20;
```

---

## 三、本地手动执行

与 OpenClaw **同一任务、同一断点、同一四表**；区别是 Agent 在本地（Cursor 等），MySQL 读写通过脚本完成。

### `scripts/ai_analysis_helper.py` — 读写主工具

只负责读写 MySQL，**不做语义分析**（语义由本地 AI 完成）。密码从 `.env` 的 `MYSQL_PASSWORD` 读取。

**执行约束**：本地手动补跑时，优先让 AI 直接读取 `fetch` 输出的每条博文原文并做语义判断；不要新增“关键词命中就 buy/sell/neutral”的自动分析脚本来替代 AI。可以使用脚本做候选检索、分页、统计、JSON 写入，但最终进入 `signals` 的 ticker、recommendation、confidence、reasoning 应由 AI 基于原文上下文确认。

| 子命令 | 作用 |
|--------|------|
| `sync` | 同步 AI 四表结构（首次必须先跑） |
| `checkpoint <account>` | 打印最近 checkpoint (JSON) |
| `fetch <account> [--limit N]` | 读取待分析推文 (JSON) |
| `write-run` | 从 stdin 读 run JSON，幂等写入四表 |
| `verify <account>` | 检查 post_id 是否被重复分析 |

**典型流程**：

```bash
.venv/bin/python scripts/ai_analysis_helper.py sync
.venv/bin/python scripts/ai_analysis_helper.py checkpoint aleabitoreddit
.venv/bin/python scripts/ai_analysis_helper.py fetch aleabitoreddit --limit 400 > batch.json
# 本地 AI 读 batch.json，按第一章规则分析，组装 run.json
.venv/bin/python scripts/ai_analysis_helper.py write-run < run.json
.venv/bin/python scripts/ai_analysis_helper.py verify aleabitoreddit
```

循环 `fetch` → 分析 → `write-run`，直到 `status=completed`。

**write-run 的 stdin JSON 核心字段**：

```json
{
  "run_id": "YYYYMMDDTHHMMSSZ_ai_{account}",
  "account": "...", "window_start": "...", "window_end": "...",
  "post_count": 400, "model": "glm-5.2", "prompt_version": "openclaw-v5.5",
  "status": "partial|completed", "summary": "...",
  "resume_from_post_id": "...", "resume_from_created_at": "...",
  "checkpoint_post_id": "...", "checkpoint_post_created_at": "...",
  "signals": [{"post_id","ticker","recommendation","confidence","reasoning","post_text_excerpt","post_created_at","post_score"}],
  "consensus": [{"consensus_date","ticker","consensus_signal","buy_count","sell_count","hold_count","reasoning"}],
  "top_tickers": [{"rank_no","ticker","mention_posts","buy_signals","sell_signals","hold_signals","latest_signal","top_authors","ai_summary"}]
}
```

### 语义判断承载脚本（可选）

这些脚本只适合历史补跑或低风险辅助，不能作为新增账号的默认分析方式。新增账号或争议账号应采用 **AI 直接读 MySQL/fetch 数据 → 人工语义式判断 → write-run** 的流程；若使用脚本生成候选，必须由 AI 再次审核并过滤掉不属于股票范围的标的。

| 脚本 | 账号 |
|------|------|
| `scripts/gen_alea_run.py` | aleabitoreddit |
| `scripts/gen_elon_run.py` / `gen_elon_run_v5.py` | elonmusk |
| `scripts/alea_auto_batch.py` | aleabitoreddit 批量循环 |

读取 `fetch` 输出，按第一章规则生成 `write-run` 所需的 run JSON。

---

## 四、运维：移除账号

从定时 CI / OpenClaw 账号列表移除某博主后，**手动**清理 MySQL：

```bash
.venv/bin/python scripts/purge_account.py --account SpeakerPelosi --dry-run
.venv/bin/python scripts/purge_account.py --account BofA_News --yes
```

`purge_account.py` 不会被 CI 或 OpenClaw 自动调用。

---

## 五、附录

### 手动执行记录（2026-06-22，早期账号）

| 账号 | post_count | signals | status | 备注 |
|------|-----------|---------|--------|------|
| aleabitoreddit | 400 | 1034 | partial | 首次全量，仍有剩余 |
| elonmusk | 400 | 24 | partial | 首次全量 |
| HillaryClinton | 69 | 0 | completed | 已移除 |

### 其他 OpenClaw 扫库任务套用断点原则

| 任务 | 断点键 |
|------|--------|
| 本任务（X 舆情） | `post_id` + `created_at` |
| 裁员回购 / IPO 采集 | 公告 URL 或日期 |

原则相同：**读断点 → 只处理新数据 → 写完断点再退出**。

### 相关文件

| 文件 | 用途 |
|------|------|
| `AI_DAILY_ANALYSIS.md` | **本文档**（任务规范 + OpenClaw Prompt + 本地工具链） |
| `scripts/ai_analysis_helper.py` | MySQL 读写主工具 |
| `scripts/gen_alea_run.py` / `gen_elon_run.py` | 账号语义判断承载 |
| `scripts/purge_account.py` | 删除指定账号缓存与 AI 数据 |
