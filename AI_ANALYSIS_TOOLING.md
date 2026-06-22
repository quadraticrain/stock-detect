# stock-detect AI 舆情分析工具说明

> 本文档说明 stock-detect 项目「每日 AI 舆情分析」定时任务（openclaw-v5）的手动执行工具链。
> 原任务由 OpenClaw 在每天北京时间 13:00 自动触发；本文档对应工具用于本地/WorkBuddy 手动跑一次同样的增量分析流程，方便排障、补跑与验收。

## 一、任务背景

从 MySQL `cache_data` 库的 `stock_detect_x_posts` 表**增量**读取 X/Twitter 推文，做语义级 Signals / Consensus / Top Tickers 分析，写入 4 张 AI 表，并持久化断点供下次续跑。

| 表 | 用途 |
|----|------|
| `stock_detect_ai_runs` | 每次 run 的元数据 + 断点（resume_from / checkpoint） |
| `stock_detect_ai_signals` | 逐帖逐 ticker 的 recommendation(buy/hold/sell/neutral) + reasoning |
| `stock_detect_ai_consensus` | 按 (日期, ticker) 聚合的共识信号 |
| `stock_detect_ai_top_tickers` | 按 run 排名的热门 ticker |

断点机制：启动读上次 `checkpoint_*` → 只处理断点之后且未分析过的 `post_id` → 结束写新 `checkpoint_*`。排序键 `(created_at ASC, post_id ASC)` 保证断点可复现。

**定时账号（与 GitHub Actions `scan-mysql.yml` 一致）**：`aleabitoreddit`, `elonmusk`, `mingchikuo`。

## 二、工具脚本

### 1. `scripts/ai_analysis_helper.py` — MySQL 读写主工具

**用途**：封装 AI 舆情分析任务所有 MySQL 读写操作，避免手写易错的 SQL。只负责读写库，**不做语义分析本身**（语义判断由调用方 AI 完成）。

**连接信息**：host/port/user/database 写死在 `stock_detect/config.py`；密码从仓库 `.env` 的 `MYSQL_PASSWORD` 读取（`load_dotenv(override=True)`，覆盖 shell 中可能过期的同名变量）。

**子命令**：

| 子命令 | 作用 |
|--------|------|
| `sync` | 同步 AI 四表结构（建表、补列、补索引），首次执行前必须先跑 |
| `checkpoint <account>` | 打印某账号最近一次成功 run 的 checkpoint (JSON) |
| `fetch <account> [--limit N]` | 读取断点之后的待分析推文 (JSON)，含 resume_from / remaining_estimate |
| `write-run` | 从 stdin 读一个完整 run 的 JSON，按 run_id 幂等写入四表（先 DELETE 本 run 旧行再 INSERT） |
| `verify <account>` | 检查某账号是否存在同一 post_id 被多个 run 重复分析 |

**典型流程**：
```bash
.venv/bin/python scripts/ai_analysis_helper.py sync
.venv/bin/python scripts/ai_analysis_helper.py checkpoint aleabitoreddit
.venv/bin/python scripts/ai_analysis_helper.py fetch aleabitoreddit --limit 400 > batch.json
# AI 读 batch.json 做语义分析，组装成 run.json
.venv/bin/python scripts/ai_analysis_helper.py write-run < run.json
.venv/bin/python scripts/ai_analysis_helper.py verify aleabitoreddit
```

**write-run 的 stdin JSON 结构**（核心字段）：
```json
{
  "run_id": "YYYYMMDDTHHMMSSZ_ai_{account}",
  "account": "...", "window_start": "...", "window_end": "...",
  "post_count": 400, "model": "glm-5.2", "prompt_version": "openclaw-v4",
  "status": "partial|completed", "summary": "...",
  "resume_from_post_id": "...", "resume_from_created_at": "...",
  "checkpoint_post_id": "...", "checkpoint_post_created_at": "...",
  "signals": [{"post_id","ticker","recommendation","confidence","reasoning","post_text_excerpt","post_created_at","post_score"}],
  "consensus": [{"consensus_date","ticker","consensus_signal","buy_count","sell_count","hold_count","reasoning"}],
  "top_tickers": [{"rank_no","ticker","mention_posts","buy_signals","sell_signals","hold_signals","latest_signal","top_authors","ai_summary"}]
}
```

### 2. `scripts/gen_alea_run.py` / `gen_elon_run.py` — 语义判断承载脚本

**用途**：承载 AI 对各账号本批推文的语义判断结果（recommendation / confidence / reasoning），读取 `ai_analysis_helper.py fetch` 产生的 JSON，输出符合 `write-run` 输入格式的 run JSON。

**判断原则**：
- **aleabitoreddit**：半导体/AI 供应链分析师，推文含大量 $TICKER。逐帖识别 ticker（优先 `tickers` JSON 列，其次正文 `$TICKER`），按作者明确评级（Strong Buy/Buy/Hold/Sell）或语义判断映射 recommendation。
- **elonmusk**：少见显式 $TICKER；SpaceX/xAI/Starlink → SPCX，Tesla 语境 → TSLA，见 openclaw-v5.1。
- **mingchikuo**：见 `prompts/openclaw_daily_ai_analysis.md` v5.5；以正文点名公司或 `$TICKER` 为主，供应链语境评估 AAPL。

**reasoning 为中文**，引用原文关键词；summary 末尾均带「仅供参考，非投资建议」。

## 三、手动执行记录（2026-06-22）

| 账号 | post_count | signals | consensus | top_tickers | status | checkpoint |
|------|-----------|---------|-----------|-------------|--------|------------|
| aleabitoreddit | 400 | 1034 | 726 | 50 | partial | 2010412174657905008 |
| elonmusk | 400 | 24 | 19 | 1 | partial | 2046846861105897857 |
| HillaryClinton | 69 | 0 | 0 | 0 | completed | 2067959995841282142 |

> **注**：历史账号 `HillaryClinton` / `SpeakerPelosi` 已从定时列表移除；下表 Hillary 行为早期手动跑批记录。

- 三账号均为**全量首次分析**（无历史 checkpoint，resume_from=NULL）。
- aleabitoreddit / elonmusk 因单批 400 上限打满，status=partial，仍有未处理帖；HillaryClinton 当时仅 69 帖已全部处理，status=completed。
- 验证结果：三账号 duplicate_signal_posts 均为 0，无重复分析。

## 四、核心主题发现（aleabitoreddit）

1. **Neocloud**（NBIS/CRWV/IREN/WULF/CIFR）：多次 Strong Buy/Buy 评级，NBIS 为最高信念多头，1 年目标价 225→450。
2. **InP 光子学瓶颈**（AXTI）：反复强调为 AI 建设单点失效垄断，CEO 称占 InP 供应链 40%，中国出口管制核打击日本竞争对手后成垄断。
3. **VLN 定价错误**：纽约/多伦多 ticker 碰撞致算法误用 -8200 万 capex 数据做空，建模公允价 ~7 美元（现 2.5）。
4. **委内瑞拉政权更迭国家建设**（GRZ/CVX/AVAV/ASHM）：美国接管委内瑞拉 17T+ 石油储备，2026 淘金热。
5. **国防无人机**（AIRO/OSS/AVAV）：1.5T 国防支出顺风，无人机蜂群/幽灵舰队。

## 五、后续定时任务设置建议

OpenClaw 定时配置（详见 `prompts/openclaw_daily_ai_analysis.md`）：

| 项 | 值 |
|----|-----|
| 任务名 | `stock-detect-ai-analysis` |
| 执行时间 | 每天北京时间 13:00（CI 扫描 09:00 之后） |
| 时区 | Asia/Shanghai |
| Cron | `0 13 * * *` |
| 环境变量 | `MYSQL_PASSWORD`（必填） |
| 单批上限 | 400 帖/账号/次 |

定时任务会自动读断点续跑。`mingchikuo` 首次接入后从 MySQL 缓存最早帖开始增量分析。

## 六、移除账号的 MySQL 清理

从定时 CI / OpenClaw 账号列表移除某博主后，应同步清理 MySQL，避免残留推文与 `fetch_state` 干扰统计。

**工具**：`scripts/purge_account.py`（删除 `stock_detect_x_posts`、`stock_detect_x_fetch_state`、该账号全部 `stock_detect_ai_*` 行）

```bash
# 预览将删除的行数
.venv/bin/python scripts/purge_account.py --account SpeakerPelosi --dry-run

# 确认后执行（会要求输入账号名，或加 --yes 跳过确认）
.venv/bin/python scripts/purge_account.py --account BofA_News --yes
```

**本项目已移除的账号**（2026-06-22，均已手动 purge）：

| 账号 | 移除原因 |
|------|----------|
| `HillaryClinton` | 换为佩洛西，后佩洛西亦移除 |
| `SpeakerPelosi` | 换为机构账号列表 |
| `BofA_News` | 180 天仅 1 帖 |
| `SEMIglobal` | 180 天仅 1 帖 |
| `Gartner_inc` | 近一年无新帖 |

清理后可用 SQL 验证：

```sql
SELECT author, COUNT(*) FROM stock_detect_x_posts
WHERE LOWER(author) IN ('hillaryclinton','speakerpelosi','bofa_news','semiglobal','gartner_inc')
GROUP BY author;
-- 应无结果
```

## 七、文件清单

| 文件 | 用途 |
|------|------|
| `scripts/ai_analysis_helper.py` | MySQL 读写主工具（sync/checkpoint/fetch/write-run/verify） |
| `scripts/gen_alea_run.py` | aleabitoreddit 语义判断承载脚本 |
| `scripts/gen_elon_run.py` | elonmusk 语义判断承载脚本 |
| `scripts/purge_account.py` | 从 MySQL 删除指定账号的推文缓存与 AI 分析数据 |
| `scripts/sequential_fetch_180d.sh` | 依次触发 workflow_dispatch 180 天抓取（每账号等上一个完成） |
| `scripts/resume_fetch_chain.sh` | 从指定 run 或账号列表续跑 180 天抓取 |
| `AI_ANALYSIS_TOOLING.md` | 本文档 |
| `prompts/openclaw_daily_ai_analysis.md` | OpenClaw 定时任务 prompt 规范（既有） |
