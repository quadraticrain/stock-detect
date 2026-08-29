# 美股财报与打新提醒系统

自动追踪美股/港股/A股的财报日历和IPO打新信息，推送至 Bark App。

## 🏗️ 系统架构

```
┌─────────────────┐     ┌───────────────┐     ┌────────────────┐
│  GitHub Actions  │────▶│  Python脚本   │────▶│  MySQL (RDS)   │
│   (定时触发)     │     │  (数据处理)   │     │  (缓存+存储)   │
└─────────────────┘     └───────────────┘     └────────────────┘
                                │
                                ▼
                       ┌────────────────┐
                       │  Bark Push API │──▶ iOS通知
                       └────────────────┘
```

## 📁 文件结构

```
stock-detect/
├── .github/workflows/
│   ├── earnings.yml      # 财报提醒
│   └── ipo.yml           # 打新提醒
├── stock_push/
│   ├── earnings.py       # 财报数据获取 + 推送（MySQL缓存优先->yfinance补查）
│   ├── ipo.py            # IPO打新数据获取
│   ├── layoff.py         # 裁员数据查询工具（供earnings.py调用）
│   ├── layoff_v2.py      # 裁员数据查询工具 v2
│   ├── china.py          # 中国财经要闻
│   └── bark.py           # Bark推送工具 + MySQL日志
├── prompts/
│   └── china_automation_instructions.md
└── scripts/
    ├── check_layoff.py
    └── migrate_layoff.py
```

## 📊 数据库表结构

### 1. earnings_cache - 财报数据缓存表
```sql
CREATE TABLE earnings_cache (
    id INT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
    stock_name VARCHAR(50) NOT NULL COMMENT '股票中文名',
    market VARCHAR(10) NOT NULL COMMENT '市场: US/HK/JP/CN',
    earnings_date DATE COMMENT '财报发布日期',
    expected_eps DECIMAL(10,4) COMMENT '预期EPS',
    eps_yoy_change DECIMAL(6,2) COMMENT 'EPS同比增长%',
    current_price DECIMAL(15,4) COMMENT '当前股价',
    price_currency VARCHAR(5) COMMENT '股价货币: USD/HKD/JPY/CNY',
    has_layoff TINYINT(1) DEFAULT 0 COMMENT '是否有裁员: 0无 1有',
    eps_divergence TINYINT(1) DEFAULT 0 COMMENT 'EPS预期是否分歧: 0否 1是',
    earnings_date_confirmed TINYINT(1) DEFAULT 1 COMMENT '财报日期是否已确认: 1确认 0待确认',
    data_source VARCHAR(100) COMMENT '数据来源',
    cached_at DATETIME NOT NULL COMMENT '缓存写入时间',
    expires_at DATETIME NOT NULL COMMENT '缓存过期时间',
    UNIQUE KEY uk_stock_code_date (stock_code, earnings_date),
    KEY idx_expires (expires_at),
    KEY idx_market (market),
    KEY idx_earnings_date (earnings_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='财报数据缓存表';
```

### 2. layoff_quarterly_data - 季度裁员数据
```sql
CREATE TABLE layoff_quarterly_data (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL COMMENT '股票代码',
    company_name VARCHAR(100) COMMENT '公司名称',
    quarter VARCHAR(10) NOT NULL COMMENT '季度(Q1/Q2/Q3/Q4)',
    year INT NOT NULL COMMENT '年份',
    layoff_count INT COMMENT '裁员人数',
    layoff_percent DECIMAL(5,2) COMMENT '裁员百分比',
    announcement_date DATE COMMENT '公告日期',
    source TEXT COMMENT '数据来源URL',
    note TEXT COMMENT '备注详情',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    confidence VARCHAR(20) DEFAULT 'medium' COMMENT '置信度',
    UNIQUE KEY uk_ticker_quarter_year (ticker, quarter, year),
    KEY idx_year_quarter (year, quarter),
    KEY idx_ticker (ticker)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='季度裁员数据';
```

### 3. buyback_quarterly_data - 季度回购数据
```sql
CREATE TABLE buyback_quarterly_data (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL COMMENT '股票代码',
    company_name VARCHAR(100) COMMENT '公司名称',
    quarter VARCHAR(10) NOT NULL COMMENT '季度(Q1/Q2/Q3/Q4)',
    year INT NOT NULL COMMENT '年份',
    buyback_amount VARCHAR(50) COMMENT '回购金额(含币种)',
    buyback_percent DECIMAL(5,2) COMMENT '回购占流通股比%',
    announcement_date DATE COMMENT '公告日期',
    source TEXT COMMENT '数据来源URL',
    note TEXT COMMENT '备注详情',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    confidence VARCHAR(20) DEFAULT 'medium' COMMENT '置信度',
    UNIQUE KEY uk_ticker_quarter_year (ticker, quarter, year),
    KEY idx_year_quarter (year, quarter),
    KEY idx_ticker (ticker)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='季度回购数据';
```

### 4. push_response_log - 推送响应日志表
```sql
CREATE TABLE push_response_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    task_id INT NOT NULL COMMENT '定时任务ID',
    task_name VARCHAR(50) NOT NULL COMMENT '任务名称',
    push_url VARCHAR(500) NOT NULL COMMENT '推送URL',
    request_body MEDIUMTEXT COMMENT '请求body',
    http_status INT COMMENT 'HTTP状态码',
    response_body MEDIUMTEXT COMMENT '响应内容',
    success TINYINT(1) DEFAULT 0 COMMENT '是否成功: 0否 1是',
    error_message TEXT COMMENT '错误信息',
    retry_count INT DEFAULT 0 COMMENT '重试次数',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '记录时间',
    KEY idx_task_id (task_id),
    KEY idx_success (success),
    KEY idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='推送响应日志表';
```

## ⏰ 定时任务配置

### GitHub Actions

| 任务 | 文件 | 频率 | Cron (UTC) | 计划北京 | 预计实际到达 |
|------|------|------|------------|----------|------------|
| 财报提醒 | `earnings.yml` | 周一~周五 | `0 0 * * 1-5` | 08:00 | ~12:00 |
| IPO打新 | `ipo.yml` | 周一~周五 | `0 1 * * 1-5` | 09:00 | ~13:00 |

> ⚠️ GitHub Actions schedule 不保证准时，通常延迟4-5小时，cron已提前设置以抵消延迟

### AI 定时任务

| 任务 | 任务ID | 频率 | 说明 |
|------|--------|------|------|
| 裁员+回购数据 | 72106 | 周一/周三 10:00 | AI采集+分析，写入MySQL，增量推送Bark |

## 🔧 GitHub Secrets 配置

在仓库 Settings > Secrets and variables > Actions 中配置：

| Secret | 说明 |
|--------|------|
| `EARNINGS_PUSH_API` | 财报 JSON 分发 API（可选，默认 `https://quadraticequation.top/api/earnings/bark-forward`） |
| `BARK_URL` | Bark推送URL（IPO / 中国要闻等仍直推） |
| `DB_HOST` | MySQL主机地址 |
| `DB_PORT` | MySQL端口 (默认3306) |
| `DB_USER` | MySQL用户名 |
| `DB_PASSWORD` | MySQL密码 |
| `DB_NAME` | MySQL数据库名 |

## 🚀 手动触发

```bash
# 财报提醒
gh workflow run earnings.yml

# IPO打新
gh workflow run ipo.yml
```

## 📈 数据流

### 财报提醒
```
1. GitHub Actions 定时触发 / 手动触发
2. 遍历股票列表（美股 + 港股 + 日股 + A股）
3. MySQL缓存优先 -> yfinance补查 -> 自动计算EPS同比增长 -> 写入缓存
4. 过滤：过去72小时 + 未来14天
5. 组装 JSON POST 到 GolangCalculateServer `/api/earnings/bark-forward`
6. 后端按用户订阅股票过滤后推 Bark/PushDeer；无订阅则跳过
7. 推送结果写入MySQL日志
```

### 裁员与回购数据
```
1. AI定时任务触发（每周一/三 12:00）
2. AI直接搜索+分析新闻，智能判断是否为真正裁员
3. 验证规则：法律备案 > 行业2倍离职率 > 集中遣散+冻结招聘 > 正常流动
4. 同时查询公司回购计划/执行情况
5. 写入MySQL layoff_quarterly_data / buyback_quarterly_data
6. 增量数据推送Bark
7. 财报推送时从MySQL补充裁员+回购信息
```

## 📈 数据源

| 数据类型 | 数据源 |
|---------|--------|
| 美股/港股财报 | Yahoo Finance (yfinance) + MySQL缓存 |
| EPS同比增长 | yfinance earnings_history + 自动补算 |
| A股IPO | 东方财富 (akshare) |
| 港股IPO | 老虎证券 itiger API (hktrade.skytigris.com) |
| 可转债 | 东方财富 (akshare) |
| 裁员数据 | AI直接采集（非脚本） |

## 📝 推送格式示例

### 财报提醒
```
📊 美股财报日历·腾讯龙虾

🔸 周三 06/03 🔸
  ├ 博通 (AVGO) 🇺🇸
  └ 📈 预期EPS $2.40｜🔺 同比+35%｜💰 $446.77｜👥 裁员: -

📌 提醒
• 近72小时及未来14天共1家公司发布财报
数据来源：MySQL缓存 + Yahoo Finance
```

### 裁员数据
```
2025 Q2 裁员数据摘要
━━━━━━━━━━━━━━━
META: 10000人(13%)
DOW: 4500人(13%)
IBM: 10000人
...
共 15 家公司有裁员数据
```

## 📱 Bark推送配置

- **URL**: `https://api.day.app/{DEVICE_KEY}/`
- **Sound**: `healthnotification`
- **Group**: `earnings` / `ipo` / `china`

## 🛠️ 本地开发

```bash
# 安装依赖
pip install yfinance requests pandas pymysql lxml akshare

# 设置环境变量
export DB_HOST=your-db-host
export DB_USER=your-db-user
export DB_PASSWORD=your-db-password
export BARK_URL=https://api.day.app/YOUR_KEY/

# 测试运行
python stock_push/earnings.py
python stock_push/ipo.py
```

## ⚠️ 注意事项

1. **API限制**: Yahoo Finance 有请求频率限制，GitHub Actions环境IP池正常，本地IP易被限流
2. **数据库连接**: 确保 RDS 允许 GitHub Actions IP 访问
3. **股票代码**: 港股代码需转换为4位格式（如02097.HK -> 2097.HK）
4. **时区**: 所有时间均为 UTC+8
5. **裁员数据**: 由AI定时任务采集，非GitHub Actions脚本执行

## 📊 监控

- 推送日志: 查询 `push_response_log` 表
- 财报缓存: 查询 `earnings_cache` 表
- 裁员数据: 查询 `layoff_quarterly_data` 表
- 回购数据: 查询 `buyback_quarterly_data` 表
- GitHub Actions: 查看 Workflow 运行状态
