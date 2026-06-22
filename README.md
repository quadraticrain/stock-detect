# Stock Detect

**X/Twitter 优先** 的投资信号检测工具。论文方法论来自 [Democratization of Retail Trading](https://arxiv.org/abs/2301.00170)（Buz & de Melo, 2023）；产品定位则对齐 [@aleabitoreddit](https://x.com/aleabitoreddit/status/2065021329275855277) 的观点：

> WSB 能较早发现优质标的，但 timing 常不准；**如今 alpha 更多在 X 上**。

因此本工具 **默认扫描 X/Twitter**，WSB 作为可选补充源。

## 信号源优先级

| 优先级 | 来源 | 说明 |
|--------|------|------|
| 1 | **X 官方 API（OAuth）** | 推荐；配置 `X_BEARER_TOKEN` 后使用 API v2，含回复帖，数据完整 |
| 2 | Guest GraphQL + syndication | 未配置 OAuth 时的回退方案，可能缺失近期回复 |
| 3 | WSB | `--source wsb`；Reddit 归档 API |
| 合并 | X + WSB | `--source both` |

## 默认监控账号

- `@aleabitoreddit`（可通过 `--accounts` 扩展）

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

在 **Settings → Secrets → Actions** 添加：

| Secret | 说明 |
|--------|------|
| `MYSQL_PASSWORD` | MySQL 写账号密码 |
| `X_BEARER_TOKEN` | X 官方 API Bearer Token（读推文必需，**勿写入代码**） |

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

CI 只需配置 **`MYSQL_PASSWORD`** 与 **`X_BEARER_TOKEN`**（见上文）。定时任务只做 **X 抓取 + 信号扫描**，不含 Yahoo 回测。

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
stock_detect/
├── tweet_cache.py       # MySQL 博文缓存与去重
├── x_api_client.py      # X 官方 API v2（OAuth Bearer / OAuth1）
├── twitter_fetcher.py   # X 时间线（OAuth 优先，Guest 回退）
├── reddit_fetcher.py    # WSB 归档
├── signal_extractor.py  # 统一信号提取
├── analyzer.py          # X-first 分析流水线
├── market_data.py       # S&P 500 ticker 列表（--sp500-only）
└── cli.py
```

## CI 扫描（MySQL）

CI 每天 **北京时间 09:00** 自动拉取 X 时间线写入 MySQL；也可在 Actions 里 **手动触发**（`workflow_dispatch`）。报告页面已迁移至 [GolangCalculateServer](https://github.com/quadraticrain/GolangCalculateServer) 的 `web/public/stock-detect/`，由后端 API 从 MySQL 实时生成。

本地仅分析缓存（不拉取）：

```bash
python scripts/analyze_mysql_report.py --accounts aleabitoreddit
```

## 运行耗时

| 模式 | 典型耗时 |
|------|----------|
| X 默认扫描 | **~1 分钟**（含 MySQL + 官方 API） |
| X + WSB 合并 | ~30–60 秒 |
| `--sp500-only` | ~1 分钟 |

单次完整运行远低于 30 分钟，适合 GitHub Actions 定时触发（workflow 已配置 `timeout-minutes: 30`）。

## 免责声明

仅供研究学习，**不构成投资建议**。

## 参考

- [arXiv:2301.00170](https://arxiv.org/abs/2301.00170) — WSB vs 投行
- [@aleabitoreddit on X](https://x.com/aleabitoreddit) — AI/Semi supply chain 分析
