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
cp .env.example .env   # 填入 X API 凭证（见下文）
```

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

#### 方案 A：OAuth 2.0 Bearer Token（推荐，最简单）

1. App → **Keys and tokens**  
2. 在 **Authentication Tokens** 下点击 **Generate** / 复制 **Bearer Token**  
3. 写入环境变量：

```bash
export X_BEARER_TOKEN="你的BearerToken"
```

或在项目根目录 `.env` 中配置（参考 `.env.example`）。

#### 方案 B：OAuth 1.0a User Context

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
python main.py scan --accounts aleabitoreddit --no-eval
```

报告 JSON / 终端输出中应出现 `"streams_used": ["XApiV2"]` 与 `"x_auth_mode": "oauth2_bearer"`。

### 6. GitHub Actions CI

在仓库 **Settings → Secrets and variables → Actions** 中添加：

| Secret 名称 | 说明 |
|-------------|------|
| `X_BEARER_TOKEN` | 方案 A 的 Bearer Token（推荐） |
| 或 `X_API_KEY` / `X_API_SECRET` / `X_ACCESS_TOKEN` / `X_ACCESS_TOKEN_SECRET` | 方案 B 四件套 |

CI workflow 已自动注入上述环境变量；**切勿**把 Token 写进代码或提交到 Git。

### 7. 配额与套餐

- X API 按 [官方定价](https://developer.x.com/en/docs/twitter-api/getting-started/about-twitter-api) 计费；Free 档读取配额有限，Basic 档更适合每日定时扫描  
- 本工具默认 63 天窗口 + 分页，单次扫描某账号通常消耗 **数页到数十次** Read 请求  
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

限制为 S&P 500 + 回测高表现股检测：

```bash
python main.py scan --sp500-only --detection
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
| 增强 | MA30/MA90 过滤回测 | 同左 |

## 项目结构

```
stock_detect/
├── x_api_client.py      # X 官方 API v2（OAuth Bearer / OAuth1）
├── twitter_fetcher.py   # X 时间线（OAuth 优先，Guest 回退）
├── reddit_fetcher.py    # WSB 归档
├── signal_extractor.py  # 统一信号提取
├── analyzer.py          # X-first 分析流水线
├── market_data.py       # Yahoo Finance 回测
└── cli.py
```

## GitHub Pages 报告

CI 每 **24 小时**（UTC 0:00）自动运行扫描，也可在 push 到 main 或手动触发；结果发布到 **`gh-pages` 分支**：

**https://quadraticrain.github.io/stock-detect/**

- 首页：历次 CI 报告列表，可按 **Source / Account** 筛选
- 每次 CI：生成独立页面 `reports/{run_id}.html`
- 顶部导航栏：切换不同 CI 运行结果
- 最新报告快捷入口：`latest.html`

本地生成静态站点：

```bash
python scripts/build_pages.py --output site
```

## 运行耗时

| 模式 | 典型耗时 |
|------|----------|
| X 默认扫描 + 回测 | **~6 秒** |
| X + WSB 合并 | ~30–60 秒 |
| `--sp500-only --detection` | ~2–5 分钟 |

单次完整运行远低于 30 分钟，适合 GitHub Actions 定时触发（workflow 已配置 `timeout-minutes: 30`）。

## 免责声明

仅供研究学习，**不构成投资建议**。

## 参考

- [arXiv:2301.00170](https://arxiv.org/abs/2301.00170) — WSB vs 投行
- [@aleabitoreddit on X](https://x.com/aleabitoreddit) — AI/Semi supply chain 分析
