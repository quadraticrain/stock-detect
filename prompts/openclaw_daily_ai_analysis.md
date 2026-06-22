# OpenClaw 定时任务 Prompt — stock-detect AI 舆情分析（v4）

> **用途**：复制下方「系统 Prompt」与「用户 Prompt」到 OpenClaw。  
> **职责**：从 MySQL **增量**读取 X 推文，做语义级舆情分析，写入 `stock_detect_ai_*` 四表，并**持久化断点**供下次续跑。  
> **与关键词报告的区别**：GolangCalculateServer `/api/stock-detect/report` 使用死板词表；**本任务不使用那套规则**。

---

## 项目内 AI 定时任务通用规范（必读）

凡由 OpenClaw 定时执行、需要扫库的任务（本任务、裁员回购采集、IPO 采集等），**必须**遵守：

1. **启动前读断点**：从 MySQL（或任务约定的状态表）读取该任务/账号**上一次成功结束**时保存的 `checkpoint_*`，作为本次 `resume_from_*`。
2. **只处理新数据**：本次仅处理断点之后的数据；**禁止**对已成功处理过的 `post_id`（或等价主键）重复分析。
3. **结束时写断点**：任务正常结束或达到单批上限时，**必须**写入：
   - `resume_from_post_id` / `resume_from_created_at` — 本批**从哪条开始**（等于上次 checkpoint）
   - `checkpoint_post_id` / `checkpoint_post_created_at` — 本批**处理到哪条结束**（下次从这里继续）
4. **状态字段**：
   - `completed` — 已追上最新数据，断点落在最新帖
   - `partial` — 本批上限已到，仍有未处理帖，下次从 checkpoint 继续
   - `failed` — 失败时不更新 checkpoint（或仅写失败前的安全断点并在 summary 说明）
5. **排序键**：统一按 `(created_at ASC, post_id ASC)` 递增处理，保证断点可复现。
6. **幂等**：同一 `post_id` 若已在历史 `stock_detect_ai_signals` 中存在，跳过（双保险）。

---

## 调度配置建议（OpenClaw）

| 项 | 值 |
|----|-----|
| 任务名 | `stock-detect-ai-analysis` |
| **执行时间** | **每天北京时间 13:00**（建议在 stock-detect CI 扫描 09:00 之后） |
| **时区** | `Asia/Shanghai` |
| **Cron** | `0 13 * * *` + 时区 `Asia/Shanghai` |
| 环境变量 | `MYSQL_PASSWORD`（必填） |
| 单批上限 | 建议每账号 **300–500 帖**/次，避免超时；未跑完写 `status=partial` |

---

## 分析账号（默认全跑）

| 账号 | 类型 | AI 分析要点 |
|------|------|-------------|
| `aleabitoreddit` | 半导体/供应链投资博主 | 识别 `$TICKER`、行业黑话 |
| `elonmusk` | 企业家/政治人物 | Tesla→TSLA 语义映射；少 explicit buy |
| `HillaryClinton` | 政治人物 | 非财经语境多数 neutral |

---

## 系统 Prompt（System）

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

- 若无历史行 → 全量首次：`resume_from_*` 置 NULL，从最早未分析帖开始
- 若有 → 本批 `resume_from_post_id` = 上次的 `checkpoint_post_id`，`resume_from_created_at` = 上次的 `checkpoint_post_created_at`

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

### 结束：写入断点（写入 stock_detect_ai_runs 必填字段）

| 字段 | 说明 |
|------|------|
| resume_from_post_id | 本批起始帖 ID（来自上次 checkpoint；首批为 NULL） |
| resume_from_created_at | 本批起始发帖时间 |
| checkpoint_post_id | 本批**最后成功分析**的帖 ID；0 条则为 NULL |
| checkpoint_post_created_at | 上述帖的 created_at |
| status | `completed`（已无新帖）或 `partial`（LIMIT 打满且仍有新帖） |
| post_count | 本批实际分析帖数 |

**禁止**只写 summary 不写 checkpoint；**禁止**下次全量重扫已分析过的 post_id。

### Consensus / Top Tickers

- 本批只 INSERT 新帖的 signals
- Consensus、Top Tickers 按账号**全窗口**重算：聚合 `stock_detect_ai_signals` 中 `post_created_at` 落在 `[window_start, window_end]` 的所有行（含历史 run），写入**本次 run_id** 下新的 consensus/top 行（先 DELETE 本 run_id 旧 consensus/top 再 INSERT）

## 与关键词报告的区别

- 关键词报告：$TICKER + 固定英文词表
- 本任务：自然语言理解；优先 MySQL `tickers` JSON（X API entities）

## Ticker 识别优先级

1. `tickers` JSON 列（X API entities）
2. 正文 `$TICKER`
3. 账号映射（elonmusk: Tesla→TSLA，仅语境相关时）

## 推荐取值

- recommendation: buy | hold | sell | neutral
- consensus_signal: buy | sell | neutral
- prompt_version: 固定 `openclaw-v4`

## 硬性规则

1. 只读 `stock_detect_x_posts`，只写 AI 四表
2. 每账号每批新 `run_id`：`YYYYMMDDTHHMMSSZ_ai_{account}`
3. 同 run_id 幂等：先 DELETE 该 run 在四表中的旧行
4. 时间 UTC，MySQL DATETIME 无时区后缀

## 执行步骤（每账号）

1. 读上次 checkpoint → 定 resume_from
2. SELECT 本批新帖（LIMIT batch_limit）
3. 生成 run_id，DELETE 本 run 旧行
4. 逐帖分析 → INSERT signals
5. 全窗口聚合 → INSERT consensus + top_tickers
6. INSERT ai_runs（**含 checkpoint 四字段 + status**）
7. 输出 JSON（含 checkpoint_post_id、status）

## 质量与免责

- reasoning 中文，引用原文
- summary 末尾：「仅供参考，非投资建议」
```

---

## 用户 Prompt（User，每次定时触发）

```
执行 stock-detect 每日 AI 舆情分析（openclaw-v4，增量断点续跑）。

- 账号列表：aleabitoreddit, elonmusk, HillaryClinton
- mode：incremental（默认；仅当用户显式要求 replay 时才 full）
- batch_limit：400（每账号每批最多处理帖数）
- 当前 UTC：{{NOW_UTC}}
- prompt_version：openclaw-v4

对每个账号依次：
1) 读 stock_detect_ai_runs 最新 checkpoint
2) 只 SELECT 断点之后、且未在 ai_signals 出现过的 post_id
3) 分析并写入四表
4) **必须**在 ai_runs 写入 resume_from_* 与 checkpoint_*；无新帖时 status=completed 且 checkpoint 保持上次值

完成后返回：
{
  "prompt_version": "openclaw-v4",
  "accounts": [
    {
      "account": "aleabitoreddit",
      "run_id": "...",
      "status": "partial",
      "post_count": 400,
      "resume_from_post_id": "...",
      "checkpoint_post_id": "...",
      "checkpoint_post_created_at": "...",
      "remaining_estimate": 120,
      "signal_count": 0,
      "consensus_count": 0,
      "top_ticker_count": 0,
      "summary": "..."
    }
  ]
}
```

---

## stock_detect_ai_runs 断点字段（v4 schema）

| 字段 | 类型 | 说明 |
|------|------|------|
| resume_from_post_id | VARCHAR(32) | 本批起始 post_id |
| resume_from_created_at | DATETIME(6) | 本批起始 created_at |
| checkpoint_post_id | VARCHAR(32) | 本批结束 post_id（下次从这里继续） |
| checkpoint_post_created_at | DATETIME(6) | 本批结束 created_at |

表结构由 `stock_detect/tweet_cache.py` 启动时自动 `sync_schema` 补列。

---

## SQL 示例

### 读断点

```sql
SELECT checkpoint_post_id, checkpoint_post_created_at, status
FROM stock_detect_ai_runs
WHERE account = 'elonmusk' AND checkpoint_post_id IS NOT NULL
ORDER BY analyzed_at DESC LIMIT 1;
```

### 写 run（含断点）

```sql
INSERT INTO stock_detect_ai_runs (
  run_id, account, window_start, window_end,
  post_count, signal_count, consensus_count, top_ticker_count,
  model, prompt_version, status, summary, analyzed_at,
  resume_from_post_id, resume_from_created_at,
  checkpoint_post_id, checkpoint_post_created_at
) VALUES (
  '20260622T050012Z_ai_elonmusk', 'elonmusk',
  '2025-12-01 00:00:00.000000', '2026-06-22 05:00:12.000000',
  400, 120, 85, 50,
  'claude-4', 'openclaw-v4', 'partial',
  '本批处理 400 帖，断点已更新，下次从 checkpoint 继续……仅供参考，非投资建议。',
  UTC_TIMESTAMP(6),
  '1990000000000000001', '2026-05-01 10:00:00.000000',
  '1990000000000000999', '2026-06-20 18:30:00.000000'
);
```

---

## 验证 SQL

```sql
SELECT account, run_id, status, post_count,
       resume_from_post_id, checkpoint_post_id, checkpoint_post_created_at,
       analyzed_at, prompt_version
FROM stock_detect_ai_runs
ORDER BY analyzed_at DESC
LIMIT 10;

-- 确认无重复分析
SELECT post_id, COUNT(DISTINCT run_id) AS runs
FROM stock_detect_ai_signals
WHERE account = 'elonmusk'
GROUP BY post_id
HAVING runs > 1
LIMIT 20;
```

---

## 其他 OpenClaw 任务如何套用

| 任务 | 状态存放建议 | 断点键 |
|------|----------------|--------|
| 本任务（X 舆情） | `stock_detect_ai_runs.checkpoint_*` | `post_id` + `created_at` |
| 裁员回购采集 | `ai_gather_info_stock` 或专用 `task_checkpoints` 表 | 公告 URL / 公告日期 |
| IPO 采集 | 任务 json 内 `last_processed_*` 或 MySQL 状态表 | 股票代码 + 公告日 |

原则相同：**读断点 → 只处理新数据 → 写完断点再退出**。
