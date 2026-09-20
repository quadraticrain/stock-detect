# Stock Detect

**X/Twitter 优先** 的投资信号检测工具。论文方法论来自 [Democratization of Retail Trading](https://arxiv.org/abs/2301.00170)（Buz & de Melo, 2023）；产品定位则对齐 [@aleabitoreddit](https://x.com/aleabitoreddit/status/2065021329275855277) 的观点：

> WSB 能较早发现优质标的，但 timing 常不准；**如今 alpha 更多在 X 上**。

因此本工具 **默认扫描 X/Twitter**，WSB 作为可选补充源。

## 目录

- [定时任务概览](#定时任务概览)
  - [X 数据抓取](#x-数据抓取scan-mysqlyml)
  - [AI 舆情分析（WorkBuddy）](#ai-舆情分析workbuddy)
  - [财报 / IPO 推送（原 stock-push）](#财报--ipo-推送原-stock-push)
- [信号源优先级](#信号源优先级)
- [默认监控账号](#默认监控账号)
  - [停止关注账号](#停止关注账号)
- [安装](#安装)
- [MySQL 博文缓存（推荐）](#mysql-博文缓存推荐)
  - [表结构](#表结构)
  - [本地配置](#本地配置)
  - [GitHub Actions](#github-actions)
- [X 官方 API 开通与配置（推荐）](#x-官方-api-开通与配置推荐)
- [使用](#使用)
- [方法论](#方法论)
- [项目结构](#项目结构)
- [CI 扫描（MySQL）](#ci-扫描mysql)
- [运行耗时](#运行耗时)
- [免责声明](#免责声明)
- [参考](#参考)

## 定时任务概览

本仓库目前有 **3 个 GitHub Actions workflow** + **2 个 WorkBuddy 定时任务**，彼此独立、互不影响：

| Workflow / 任务 | 调度（北京时间） | 作用 |
|-----------------|------------------|------|
| `scan-mysql.yml` | **每周六 17:40** | 抓 X 推文入 MySQL |
| `earnings.yml` | 周一~周五 08:00 | 财报日历 → JSON → Bark 分发 |
| `ipo.yml` | 周一~周五 09:00 | A 股打新 / 可转债 / 港股 IPO → Bark |
| WorkBuddy 雪球抓取 | **每周日 09:01** | 本地抓雪球推文入 MySQL（cookie 过期自动从 Chrome 刷新） |
| WorkBuddy AI 分析 | **每周日 11:01** | 读库做语义分析，写 AI 结果表；完成后推 Bark 汇总 |

> GitHub Actions 的 `schedule` **不保证准时**，实际常延迟数小时；上表为 cron 配置的计划时间。

### X 数据抓取（`scan-mysql.yml`）

Workflow 文件：`.github/workflows/scan-mysql.yml`

| 项 | 值 |
|----|-----|
| 定时 | **每周六 北京时间 17:40**（cron `40 9 * * 6`，UTC） |
| 超时 | `timeout-minutes: 90` |
| 默认账号 | `aleabitoreddit`, `mingchikuo` |
| 默认窗口 | **63 天**（X API 可读范围；更早历史需 Guest 回填） |
| 写入 | MySQL `stock_detect_x_posts`、`stock_detect_x_fetch_state` |
| 所需 Secret | `MYSQL_PASSWORD`、`X_BEARER_TOKEN` |
| 失败通知 | 任一步骤失败时推 Bark（`stock-detect` 分组），提示 X API 额度/token 问题 |

> 雪球账号抓取已迁移到本地（见下节「雪球抓取（本地）」），不再经 GitHub Actions，`XUEQIU_COOKIE` Secret 已废弃。

### X API 错误处理（重要）

`stock_detect/x_api_client.py` 对 X API 的非 200 响应分三类处理，**不再静默当成“这页没数据”**：

| 状态码 | 行为 |
|--------|------|
| `401` / `402` / `403` | 抛 `XApiFatalError`，`scripts/scan_mysql.py` 以 **exit code 2** 退出，CI 变红 + Bark 告警 |
| `429` / `5xx` | 按 `Retry-After` / `x-rate-limit-reset` 退避重试，最多 3 次；耗尽后计入 `pages_skipped` |
| 其它非 200 | stderr 输出 `[x-api] HTTP <code> ...` warning 并计入 `pages_skipped` |

`Scan OK` 行会同时输出 `pages_skipped=N`；N>0 时额外打一条 `WARNING: ... coverage may be incomplete`。

常见故障：

- **`402 credits depleted`** —— X 开发者账户 credit 余额耗尽（注意这与 `/2/usage/tweets` 的月度 post cap 无关，post cap 可能还剩很多）。充值后手动重跑 workflow，建议放大 `window_days` 补回空窗期。
  自查：`curl -H "Authorization: Bearer $X_BEARER_TOKEN" https://api.twitter.com/2/users/by/username/aleabitoreddit`
- **`401 Unauthorized`** —— `X_BEARER_TOKEN` 失效或被注销，轮换 GitHub Secret。

> workflow 的 `SCHEDULED_ACCOUNTS` 仍包含 `justinsuntron`，但该账号已列入 `config.py` 的 `DISABLED_X_ACCOUNTS`，抓取入口会自动跳过，实际生效账号为 `aleabitoreddit`、`mingchikuo` 两个 X 账号。

**手动触发**（Actions → *X/雪球舆情抓取* → Run workflow，或命令行）：

```bash
# 日常增量 / 单账号 63 天
gh workflow run scan-mysql.yml \
  --repo quadraticrain/stock-detect \
  -f accounts=aleabitoreddit

# 新账号或历史回填：180 天（CI 会自动放大 max_posts / max_pages，并先 Guest 回填 63 天以前）
gh workflow run scan-mysql.yml \
  --repo quadraticrain/stock-detect \
  -f accounts=mingchikuo \
  -f window_days=180
```

多账号依次拉取（等上一个 run 完成再触发下一个，避免 workflow 互相取消）：

```bash
./scripts/sequential_fetch_180d.sh mingchikuo aleabitoreddit
```

查看进度：`gh run list --repo quadraticrain/stock-detect --workflow=scan-mysql.yml --limit 3`

### 雪球抓取（本地）

雪球账号（段永平 `1247347556`、但斌 `1102105103`）的推文抓取已从 GitHub Actions 迁移到本机（WorkBuddy 定时任务，每周日 09:01），入口脚本：

```bash
./scripts/local_xueqiu_fetch.py
```

脚本流程：读 `.env` 里的 `XUEQIU_COOKIE` → 探测是否过期 → 过期则从本机 Chrome 读取新 cookie 并写回 `.env` → 抓帖入库。cookie 刷新失败（例如 Chrome 未登录雪球）时会推 Bark 告警。

Chrome cookie 解密需要浏览器的 "Safe Storage" 密钥，解析顺序为：环境变量 `CHROME_SAFE_STORAGE_PASSWORD` → 状态文件 `.workbuddy/state/chrome_safe_storage` → 本机钥匙串（`security find-generic-password -w -s "Chrome Safe Storage"`）。若担心自动化环境无法弹出钥匙串授权框，可一次性把密钥写入状态文件：

```bash
mkdir -p .workbuddy/state
security find-generic-password -w -s "Chrome Safe Storage" > .workbuddy/state/chrome_safe_storage
```

手动刷新 `.env` 里的 `XUEQIU_COOKIE`：

```bash
./scripts/sync_xueqiu_cookie_secret.py
```

脚本只读取浏览器 cookie，不保存雪球账号密码。

### AI 舆情分析（WorkBuddy）

| 项 | 值 |
|----|-----|
| 任务名 | `stock-detect-ai-analysis`（WorkBuddy 定时任务） |
| 调度 | 每周日 **北京时间 11:01**（WorkBuddy 任务；X 抓取每周六 17:40、雪球本地抓取每周日 09:01 先行） |
| 输入 | MySQL `stock_detect_x_posts`（**增量断点**续跑，不重复分析已处理帖） |
| 输出 | `stock_detect_ai_runs`、`stock_detect_ai_signals`、`stock_detect_ai_consensus`、`stock_detect_ai_top_tickers` |
| 额外步骤 | 分析完成后运行 `stock_detect_bark_summary.py` 推一条 Bark 汇总（按提及帖数挑重点股票） |
| 与关键词报告的区别 | GolangCalculateServer 报告用固定词表；**AI 任务做自然语言语义分析**（buy/hold/sell/neutral、共识、热门 ticker） |

- 任务的**调度与运行时配置**（cron、投递、超时、Bark 步骤原文）见 [`AI_TASK.md`](AI_TASK.md)。
- 任务的**分析规范**（Ticker 映射、态度分级、雪球转发、断点字段）见 [`AI_ANALYSIS.md`](AI_ANALYSIS.md)。
- WorkBuddy 与本地手动为 **同一 AI 任务**（仅 Agent 不同），本地手动流程见 `AI_ANALYSIS.md` 第三章（含 `scripts/ai_analysis_helper.py`）。

### 财报 / IPO 推送（原 stock-push）

合并自 [stock-push](https://github.com/quadraticrain/stock-push)（旧仓库待归档删除）；代码在 `stock_push/`，表结构与推送格式详见 [`stock_push/README.md`](stock_push/README.md)。

| Workflow | 定时（UTC cron） | 计划北京 | 超时 | 说明 |
|----------|------------------|----------|------|------|
| `earnings.yml` | `0 0 * * 1-5` | 08:00 | 40 分钟 | 美股/港股/日股/A 股财报 → JSON → Bark 分发 |
| `ipo.yml` | `0 1 * * 1-5` | 09:00 | 20 分钟 | A 股打新 / 可转债 / 港股 IPO → Bark |

所需 Secrets（已从旧仓库迁入本仓库）：

| Secret | 值 / 说明 |
|--------|-----------|
| `DB_HOST` | `rm-wz91qxav0rb3uxf17ro.mysql.cn-shenzhen.rds.aliyuncs.com` |
| `DB_PORT` | `3306` |
| `DB_USER` | `cache_data_write` |
| `DB_PASSWORD` | 与 `MYSQL_PASSWORD` **同一个密码**（同库同账号） |
| `DB_NAME` | `cache_data` |
| `BARK_URL` | Bark 推送地址，**末尾带斜杠** |
| `EARNINGS_PUSH_API` | 可选，默认 `https://quadraticequation.top/api/earnings/bark-forward` |

> ⚠️ `DB_PASSWORD` 与上文的 `MYSQL_PASSWORD` 是**同一个数据库密码的两份拷贝**（历史遗留：两个仓库各自命名）。**轮换密码时必须两个 Secret 一起改**，否则会出现一半 workflow 正常、一半连不上库。

手动触发与本地运行：

```bash
gh workflow run earnings.yml --repo quadraticrain/stock-detect
gh workflow run ipo.yml --repo quadraticrain/stock-detect
python stock_push/earnings.py
python stock_push/ipo.py
```

**运行耗时**：`earnings.py` 要遍历 **209 只标的**（美 83 / 日 17 / 港 112 / A 1），每只先查 MySQL 缓存，未命中则调 yfinance；叠加限流（每只 `sleep(0.5)`，每 20 只额外 `sleep(3)`）。

| 场景 | 典型耗时 |
|------|----------|
| 缓存全 miss（首次运行 / 缓存集体过期） | **~25 分钟**（实测 ~6.7 秒/只） |
| 缓存大部分命中（日常） | ~3–5 分钟 |

缓存 TTL 为 `earnings_date + 7 天`，所以**首次跨仓库运行慢属正常，不是卡死**。判断是否真在干活（job 未结束时 Actions 日志下载不了，会返回 `BlobNotFound`）：

```sql
SELECT COUNT(*), MAX(cached_at) FROM earnings_cache
WHERE cached_at > NOW() - INTERVAL 30 MINUTE;
```

行数持续增长即说明脚本正常推进，且 `DB_*` 四个 Secret 均配置正确。

## 信号源优先级

| 优先级 | 来源 | 说明 |
|--------|------|------|
| 1 | **X 官方 API（OAuth）** | 推荐；配置 `X_BEARER_TOKEN` 后使用 API v2，含回复帖，数据完整 |
| 2 | Guest GraphQL + syndication | 未配置 OAuth 时的回退方案，可能缺失近期回复 |
| 3 | WSB | `--source wsb`；Reddit 归档 API |
| 合并 | X + WSB | `--source both` |

## 默认监控账号

- `@aleabitoreddit`（可通过 `--accounts` 扩展）

### 停止关注账号

- `@elonmusk`：不再纳入每日股票-only 定时关注；历史缓存与 AI 结果保留，不做清理。
- `@sunyuchentron` / `@justinsuntron`：180 天历史数据表明几乎只讨论加密货币，不符合本项目股票-only 关注范围。后续抓取入口会自动跳过该账号；MySQL 中已有历史缓存与 AI 结果保留，不做清理。

X 模式下默认解析 **所有 `$CASHTAG`**（含 AXTI、SOI 等非 S&P 500 标的），更贴合半导体/光子学 supply-chain 研究场景。若需严格复现论文 S&P 500 范围，加 `--sp500-only`。

## 安装

```bash
git clone https://github.com/quadraticrain/stock-detect.git
cd stock-detect
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 填入 MYSQL_PASSWORD（见下文 MySQL 缓存）
```

## MySQL 博文缓存（推荐）

为降低 X API 重复拉取成本，工具将已抓取的推文写入 **阿里云 RDS MySQL**（`cache_data` 库）。同一 `post_id` 只存一条（`INSERT IGNORE`），后续扫描优先读库，并对 X API 使用 **`since_id` 增量拉取**（只请求新推文）。

| 配置项 | 位置 |
|--------|------|
| Host / Port / Database / User | `stock_detect/config.py`（已内置） |
| **密码** | 环境变量 `MYSQL_PASSWORD`（**唯一 GitHub Secret**） |

### 表结构

- `stock_detect_x_posts` — 推文正文、时间、tickers、URL 等（主键 `post_id`）
- `stock_detect_x_fetch_state` — 每账号 `user_id`、`last_tweet_id`、上次抓取时间，以及 CI 扫描标记（`last_ci_marker` 等）

每次 CI 扫描结束都会写入标记，供下游 Web/API 识别「本次无新增」：

| `last_ci_marker` | 含义 |
|------------------|------|
| `###NO_NEW###` | 本次扫描未写入新推文 |
| `***NEW:{n}***` | 本次扫描新写入 `n` 条推文 |

同时在 `stock_detect_x_posts` 保留一条 `post_id` 以 `###CI_SCAN_` 开头的哨兵行（分析时会自动排除）。

首次启动会自动同步表结构（建表、补列、补索引），无需手动维护 DDL。表定义在 `stock_detect/tweet_cache.py` 的 `_TABLES` 中维护。

### 本地配置

```bash
# .env
MYSQL_PASSWORD=你的数据库密码
```

### GitHub Actions

在 **Settings → Secrets and variables → Actions** 添加：

| Secret | 说明 | 使用方 |
|--------|------|--------|
| `MYSQL_PASSWORD` | MySQL 写账号密码 | `scan-mysql.yml` |
| `X_BEARER_TOKEN` | X 官方 API Bearer Token（读推文必需，**勿写入代码**） | `scan-mysql.yml` |
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` | 同一个 `cache_data` 库的连接信息 | `earnings.yml` / `ipo.yml` |
| `BARK_URL` | Bark 推送地址 | `ipo.yml` |
| `EARNINGS_PUSH_API` | 财报 JSON 分发 API（可选） | `earnings.yml` |

> 共 **9 个 Secret**。`MYSQL_PASSWORD` 与 `DB_PASSWORD` 指向同一个密码，详见上文财报/IPO 章节的轮换提醒。雪球 `XUEQIU_COOKIE` 已废弃（改用本地 `.env`，由 `scripts/local_xueqiu_fetch.py` 自动刷新）。

报告 JSON 的 `fetch_stats` 会包含 `cache_posts`（窗口内缓存条数）与 `api_posts_new`（本次新写入条数）。`streams_used` 含 `MySQLCache`。

未配置 `MYSQL_PASSWORD` 时，行为与旧版相同（直接调 X API / Guest，无持久化）。

## X 官方 API 开通与配置（推荐）

未配置 OAuth 时，工具会回退到 Guest GraphQL / syndication，**可能抓不到近期回复帖**（如 `@aleabitoreddit` 的 `$SIVE` 推文）。生产环境请使用 X 官方 API。

### 1. 注册开发者账号

1. 打开 [developer.x.com](https://developer.x.com/) 并用 X 账号登录  
2. 完成开发者协议与应用用途说明（选择 *Making a bot* 或 *Exploring the API* 等研究用途即可）

### 2. 创建 Project 与 App

1. 进入 **Developer Portal → Projects & Apps → Create Project**  
2. 填写项目名称与用途描述  
3. 创建 App（或使用默认 App），记下 **App 名称**

### 3. 设置 App 权限

1. 打开 App → **Settings → User authentication settings**（若使用 OAuth 1.0a）  
2. **App permissions** 设为 **Read**（只读即可）  
3. **Type of App** 选 *Web App* 或 *Automated App / Bot*  
4. Callback URL 可填 `https://127.0.0.1/callback`（本工具只需读公开时间线，Bearer 模式可不启用 User authentication）

### 4. 获取凭证（二选一）

#### 方案 A：Bearer Token（最推荐，v2 读推文用这个）

1. Development App → **Keys and tokens**  
2. 在 **Authentication Tokens** 区域点击 **Generate**，复制 **Bearer Token**  
3. 写入 `.env`（可选，覆盖 `config.py` 默认值）：

```bash
X_BEARER_TOKEN=你的BearerToken
```

`X_CLIENT_ID` / `X_CLIENT_SECRET` 已写在 `stock_detect/config.py`；本地或 CI 可通过环境变量覆盖。

#### 方案 B：OAuth 2.0 Client ID + Secret（已支持自动换 Token）

1. 同一页面的 **OAuth 2.0 Client ID** 和 **Client Secret**  
2. 写入 `.env`（可选，默认已在 `config.py`）：

```bash
X_CLIENT_ID=你的ClientID
X_CLIENT_SECRET=你的ClientSecret
```

程序会自动向 `oauth2/token` 换取 Access Token。  
**注意**：目前 Client ID/Secret 换到的 Token 对部分 v2 读接口可能返回 403；若遇到此情况，请同时使用方案 A 的 **Bearer Token**（`X_BEARER_TOKEN` 优先级更高）。

#### 方案 C：OAuth 1.0a User Context

1. **Keys and tokens** 中复制 **API Key**、**API Key Secret**  
2. 生成 **Access Token** 与 **Access Token Secret**（需 Read 权限）  
3. 写入环境变量：

```bash
export X_API_KEY="..."
export X_API_SECRET="..."
export X_ACCESS_TOKEN="..."
export X_ACCESS_TOKEN_SECRET="..."
```

### 5. 本地验证

```bash
source .env   # 或 export 上述变量
python main.py scan --accounts aleabitoreddit
```

报告 JSON / 终端输出中应出现 `"streams_used": ["XApiV2"]` 与 `"x_auth_mode": "oauth2_bearer"`。

### 6. GitHub Actions CI

CI 只需配置 **`MYSQL_PASSWORD`** 与 **`X_BEARER_TOKEN`**（见上文）。`scan-mysql.yml` 只做 **X/雪球抓取 + 信号扫描**，不含 Yahoo 回测；财报/IPO 推送是另外两个 workflow，需要 `DB_*` 系列 Secret。

### 7. 配额与套餐

- X API 按 [官方定价](https://developer.x.com/en/docs/twitter-api/getting-started/about-twitter-api) 计费；Free 档读取配额有限，Basic 档更适合每日定时扫描  
- 启用 MySQL 缓存后，日常 CI 通常只需 **数页增量** Read 请求（首次全量除外）
- 若返回 `401`/`403`，检查 Token 是否过期、App 是否为 Read 权限、套餐配额是否用尽

## 使用

扫描 X（默认）：

```bash
python main.py scan
```

指定多个 X 账号：

```bash
python main.py scan --accounts aleabitoreddit,other_analyst
```

X + WSB 合并：

```bash
python main.py scan --source both --limit 400
```

仅 WSB（论文原始数据源）：

```bash
python main.py scan --source wsb --limit 300
```

限制为 S&P 500 ticker：

```bash
python main.py scan --sp500-only
```

历史区间：

```bash
python main.py scan --after 2025-01-01 --before 2025-06-01
```

## 方法论

| 步骤 | X 模式 | WSB 模式 |
|------|--------|----------|
| 过滤 | 所有含文本推文 | Proactive flair（DD/Discussion 等） |
| Ticker | `$CASHTAG` + entities.symbols | S&P 500 + `$` 前缀规则 |
| 信号 | buy/call vs sell/put 关键词 | 同左 |
| 共识 | 日度 buy ≥ sell × 1.5 | 同左 |

## 项目结构

```
stock_detect/             # X/雪球抓取与信号分析
├── tweet_cache.py       # MySQL 博文缓存与去重
├── x_api_client.py      # X 官方 API v2（OAuth Bearer / OAuth1）
├── twitter_fetcher.py   # X 时间线（OAuth 优先，Guest 回退）
├── reddit_fetcher.py    # WSB 归档
├── signal_extractor.py  # 统一信号提取
├── analyzer.py          # X-first 分析流水线
├── market_data.py       # S&P 500 ticker 列表（--sp500-only）
├── config.py            # 账号名单 / MySQL 连接 / 停用账号
└── cli.py

stock_push/               # 财报 / IPO / Bark 推送（合并自 stock-push）
├── earnings.py          # 财报日历（MySQL 缓存优先 → yfinance 补查）
├── ipo.py               # A 股打新 / 可转债 / 港股 IPO
├── layoff.py            # 裁员数据查询
├── layoff_v2.py         # 裁员数据查询 v2
├── china.py             # 中国财经要闻（stdin 入参，无定时任务）
└── bark.py              # Bark 推送 + MySQL 日志

.github/workflows/
├── scan-mysql.yml       # 周六 17:40 抓 X/雪球
├── earnings.yml         # 工作日 08:00 财报
└── ipo.yml              # 工作日 09:00 IPO
```

## CI 扫描（MySQL）

详见上文 **[定时任务概览 → X 数据抓取](#定时任务概览)**。CI 每周六 **北京时间 17:40** 自动拉取 X 时间线写入 MySQL；也可 `gh workflow run scan-mysql.yml` 手动触发。报告页面已迁移至 [GolangCalculateServer](https://github.com/quadraticrain/GolangCalculateServer) 的 `web/public/stock-detect/`，由后端 API 从 MySQL 实时生成。

本地仅分析缓存（不拉取）：

```bash
python scripts/analyze_mysql_report.py --accounts aleabitoreddit
```

## 运行耗时

### X 抓取 / 分析（`main.py scan`）

| 模式 | 典型耗时 |
|------|----------|
| X 默认扫描 | **~1 分钟**（含 MySQL + 官方 API） |
| X + WSB 合并 | ~30–60 秒 |
| `--sp500-only` | ~1 分钟 |

### 各 workflow 超时配置

| Workflow | `timeout-minutes` | 依据 |
|----------|-------------------|------|
| `scan-mysql.yml` | 90 | 含 Guest 回填 + 多账号多页拉取 |
| `earnings.yml` | 40 | 缓存全 miss 时实测 ~25 分钟 |
| `ipo.yml` | 20 | 数据量小，通常 1–2 分钟 |

三个 workflow 均已显式设置 `timeout-minutes`，避免上游 API 挂住时按 GitHub 默认的 **360 分钟** 白烧 runner 时长。

## 免责声明

仅供研究学习，**不构成投资建议**。

## 参考

- [arXiv:2301.00170](https://arxiv.org/abs/2301.00170) — WSB vs 投行
- [@aleabitoreddit on X](https://x.com/aleabitoreddit) — AI/Semi supply chain 分析
