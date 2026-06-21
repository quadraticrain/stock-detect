# Stock Detect

基于论文 [**Democratization of Retail Trading: Can Reddit's WallStreetBets Outperform Investment Bank Analysts?**](https://arxiv.org/abs/2301.00170)（Buz & de Melo, 2023）的方法论，从 Reddit r/wallstreetbets 提取投资信号并评估表现。

该推文 [@aleabitoreddit](https://x.com/aleabitoreddit/status/2065021329275855277) 引用的核心结论：

1. WSB 在识别 S&P 500 高表现股票方面优于绝大多数投行
2. WSB 平均回报可与顶级投行竞争，部分场景下更优
3. 论文结论：WSB 是「可免费获取的有价值投资建议来源」

## 方法论摘要

本工具复现论文中的关键步骤：

| 步骤 | 说明 |
|------|------|
| Flair 过滤 | 保留 DD、Discussion、YOLO 等 proactive 帖子，排除 Meme/Gain/Loss 等 reactive 帖子 |
| Ticker 检测 | 识别 S&P 500 代码；歧义词（如 IT、LOW）和单字符代码需 `$` 前缀 |
| 信号提取 | 统计 buy/call vs sell/put 等关键词，扣除否定短语（don't buy 等） |
| 邻近检测 | 可选：仅在 ticker 20 字符范围内计 buy 词（论文 WSB prox 变体） |
| 日度共识 | 当日 buy 帖数 ≥ sell 帖数 × 1.5 时产生 buy 共识信号 |
| MA 过滤 | 可选：仅在收盘价低于 30/90 日均线时采纳 buy 信号（论文中显著提升回报） |
| 表现评估 | 计算信号后 1 周 / 1 月 / 3 月的准确率与平均涨跌幅 |

## 安装

```bash
cd stock-detect
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 使用

扫描 WSB 最新帖子并提取信号：

```bash
python main.py scan --limit 300
```

启用 MA 过滤评估 + 高表现股检测率：

```bash
python main.py scan --limit 500 --detection
```

使用邻近关键词检测（论文 WSB prox 变体）：

```bash
python main.py scan --proximity
```

查看当前 S&P 500 高表现股（论文 top 15% 标准）：

```bash
python main.py top
```

输出 JSON：

```bash
python main.py scan --json > report.json
```

回测历史区间（论文使用 2018–2022 数据）：

```bash
python main.py scan --after 2021-01-01 --before 2021-06-30 --limit 500
```

## 项目结构

```
stock_detect/
├── config.py           # 论文中的 flair、关键词、阈值常量
├── reddit_fetcher.py   # Reddit 公开 JSON API
├── signal_extractor.py # 核心信号提取逻辑
├── market_data.py      # Yahoo Finance 行情与回测
├── analyzer.py         # 分析流水线
└── cli.py              # 命令行界面
```

## 数据来源

- **Reddit**: Arctic Shift / PullPush 归档 API（Reddit 官方 API 已限制匿名访问）
- **行情**: Yahoo Finance（`yfinance`）
- **S&P 500 成分**: Wikipedia

## 免责声明

本工具仅供学术研究与学习，**不构成投资建议**。论文作者亦强调：

- WSB 信号在 meme 股上波动极大，timing 常不准
- 2021 GameStop  hype 后信号质量有所下降
- 牛市环境下结论更乐观，熊市需额外验证

## 参考

- Buz, T., & de Melo, G. (2023). *Democratization of Retail Trading*. [arXiv:2301.00170](https://arxiv.org/abs/2301.00170)
- 作者开源代码: [tbuz/Reddit_Investment_Signals](https://github.com/tbuz/Reddit_Investment_Signals)
