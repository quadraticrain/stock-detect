# Stock Detect

**X/Twitter 优先** 的投资信号检测工具。论文方法论来自 [Democratization of Retail Trading](https://arxiv.org/abs/2301.00170)（Buz & de Melo, 2023）；产品定位则对齐 [@aleabitoreddit](https://x.com/aleabitoreddit/status/2065021329275855277) 的观点：

> WSB 能较早发现优质标的，但 timing 常不准；**如今 alpha 更多在 X 上**。

因此本工具 **默认扫描 X/Twitter**，WSB 作为可选补充源。

## 信号源优先级

| 优先级 | 来源 | 说明 |
|--------|------|------|
| 1 | **X/Twitter** | 默认；通过 syndication 嵌入抓取公开时间线，无需 API Key |
| 2 | WSB | `--source wsb`；Reddit 归档 API |
| 合并 | 两者 | `--source both` |

## 默认监控账号

- `@aleabitoreddit`（可通过 `--accounts` 扩展）

X 模式下默认解析 **所有 `$CASHTAG`**（含 AXTI、SOI 等非 S&P 500 标的），更贴合半导体/光子学 supply-chain 研究场景。若需严格复现论文 S&P 500 范围，加 `--sp500-only`。

## 安装

```bash
git clone https://github.com/quadraticrain/stock-detect.git
cd stock-detect
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

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
├── twitter_fetcher.py   # X 时间线（syndication 嵌入）
├── reddit_fetcher.py    # WSB 归档
├── signal_extractor.py  # 统一信号提取
├── analyzer.py          # X-first 分析流水线
├── market_data.py       # Yahoo Finance 回测
└── cli.py
```

## GitHub Pages 报告

CI 每 6 小时（或 push 到 main 时）自动运行扫描，结果发布到 **`gh-pages` 分支**：

**https://quadraticrain.github.io/stock-detect/**

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
