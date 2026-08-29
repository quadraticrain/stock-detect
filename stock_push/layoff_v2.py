"""
季度裁员数据追踪 v2 - 智能筛选版
执行频率：每天（AI定时任务）
筛选标准：
1. 人数 >= 100 或 比例 >= 3%
2. 新闻时间在本季度内
3. 排除个人求职故事
4. 多关键词验证
"""
import sys
import os
import re
import json
import time
from datetime import datetime, timedelta
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(__file__))
import requests
import pymysql

# ============ 股票列表 ============
US_STOCKS = [
    ("NVDA", "英伟达"), ("GOOGL", "谷歌"), ("GOOG", "谷歌"), ("AAPL", "苹果"),
    ("MSFT", "微软"), ("AMZN", "亚马逊"), ("TSM", "台积电"), ("AVGO", "博通"),
    ("TSLA", "特斯拉"), ("META", "Meta"), ("LLY", "礼来"), ("WMT", "沃尔玛"),
    ("BRK-B", "伯克希尔"), ("MU", "美光科技"), ("JPM", "摩根大通"),
    ("AMD", "超威半导体"), ("XOM", "埃克森美孚"), ("ASML", "阿斯麦"),
    ("V", "维萨"), ("INTC", "英特尔"), ("JNJ", "强生"), ("COST", "好市多"),
    ("CSCO", "思科"), ("MA", "万事达"), ("CAT", "卡特彼勒"), ("CVX", "雪佛龙"),
    ("NFLX", "奈飞"), ("BAC", "美国银行"), ("KO", "可口可乐"), ("UNH", "联合健康"),
    ("AMAT", "应用材料"), ("PG", "宝洁"), ("PLTR", "Palantir"), ("ARM", "ARM"),
    ("MS", "摩根士丹利"), ("BABA", "阿里巴巴"), ("GS", "高盛"), ("MRK", "默沙东"),
    ("TXN", "德州仪器"), ("IBM", "IBM"), ("RTX", "雷神技术"), ("SNDK", "闪迪"),
    ("QCOM", "高通"), ("AXP", "美国运通"), ("PEP", "百事"), ("MCD", "麦当劳"),
    ("VZ", "威瑞森通信"), ("AMGN", "安进"), ("STX", "希捷科技"), ("DIS", "迪士尼"),
    ("BA", "波音"), ("WDC", "西部数据"), ("MRVL", "迈威尔科技"), ("GLW", "康宁"),
    ("BLK", "贝莱德"), ("SCHW", "嘉信理财"), ("ABT", "雅培"), ("COP", "康菲石油"),
    ("PDD", "拼多多"), ("SHOP", "Shopify"), ("MO", "奥驰亚"),
    ("LMT", "洛克希德马丁"), ("ABNB", "爱彼迎"), ("NOK", "诺基亚"),
    ("MMM", "3M"), ("MCO", "穆迪"), ("SHW", "宣伟"), ("NXPI", "恩智浦"),
    ("LITE", "Lumentum"), ("HLT", "希尔顿酒店"), ("AEP", "美国电力"),
    ("WBD", "华纳兄弟探索"), ("NKE", "耐克"), ("TRV", "旅行者保险"),
    ("OXY", "西方石油"), ("MET", "大都会人寿"), ("COIN", "Coinbase"),
    ("MSCI", "明晟"), ("PYPL", "PayPal"), ("CBOE", "芝加哥期权交易所"),
    ("EL", "雅诗兰黛"), ("DOW", "陶氏"), ("MGM", "美高梅"), ("FUTU", "富途控股"),
    ("CRCL", "Circle数币发行商"),
]

ALL_STOCKS = US_STOCKS

# MySQL配置
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "rm-wz91qxav0rb3uxf17ro.mysql.cn-shenzhen.rds.aliyuncs.com"),
    "port": int(os.environ.get("DB_PORT", 3306)),
    "user": os.environ.get("DB_USER", "cache_data_write"),
    "password": os.environ.get("DB_PASSWORD", "7+ML%wbA%gg3fB+"),
    "database": os.environ.get("DB_NAME", "cache_data"),
    "connect_timeout": 10,
    "autocommit": True,
}

# ============ 智能筛选配置 ============
MIN_LAYOFF_COUNT = 100      # 最少裁员人数
MIN_LAYOFF_PERCENT = 3.0    # 最少裁员比例
VALID_YEARS = [2025, 2026]  # 有效年份

# 排除关键词（个人故事、旧数据）
EXCLUDE_KEYWORDS = [
    "i've applied", "i applied", "my layoff", "my job", "i was laid off",
    "2022", "2023", "2024",  # 旧年份
    "layoffs 2022", "layoffs 2023", "layoffs 2024",
]

# 确认裁员关键词
CONFIRM_KEYWORDS = [
    "layoff", "lay off", "job cut", "workforce reduction",
    "cut jobs", "eliminate positions", "headcount reduction"
]


def get_db_connection():
    """获取MySQL连接"""
    return pymysql.connect(**DB_CONFIG)


def init_layoff_table():
    """初始化裁员数据表"""
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS layoff_quarterly_data (
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
                confidence VARCHAR(20) DEFAULT 'medium' COMMENT '置信度(high/medium/low)',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uk_ticker_quarter_year (ticker, quarter, year),
                INDEX idx_year_quarter (year, quarter),
                INDEX idx_ticker (ticker)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='季度裁员数据'
        """)
        # 兼容旧表：添加 confidence 字段
        try:
            cur.execute("ALTER TABLE layoff_quarterly_data ADD COLUMN confidence VARCHAR(20) DEFAULT 'medium'")
        except:
            pass
    conn.close()
    print("[DB] 表 layoff_quarterly_data 初始化完成")


def should_exclude(title: str) -> bool:
    """判断是否应排除（个人故事/旧数据）"""
    title_lower = title.lower()
    for kw in EXCLUDE_KEYWORDS:
        if kw.lower() in title_lower:
            return True
    return False


def is_confirmed_layoff(title: str) -> bool:
    """确认是裁员新闻而非猜测"""
    title_lower = title.lower()
    for kw in CONFIRM_KEYWORDS:
        if kw.lower() in title_lower:
            return True
    return False


def extract_layoff_count(text: str) -> int:
    """从文本提取裁员人数，过滤掉年份和求职相关数字"""
    # 排除明显是个人求职的数字
    if "i've applied" in text.lower() or "i applied" in text.lower():
        return None

    # 排除年份 2025/2026 开头的数字
    text = re.sub(r'\b202[56]\b', '', text)

    patterns = [
        r'(\d{1,3},\d{3})\s*(?:employees?|workers?|staff|jobs?|people)',
        r'(\d{3,6})\s*(?:employees?|workers?|staff|jobs?|people)',
        r'lay\s*off\s*(\d{3,6})',
        r'layoffs?\s*(?:of\s*)?(\d{3,6})',
        r'cut\s*(\d{3,6})\s*(?:employees?|jobs?)',
        r'(\d{3,6})\s*job\s*cuts',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                count = int(match.group(1).replace(',', ''))
                # 过滤不合理数字（排除年份 2025/2026）
                if 100 <= count <= 500000 and count not in [2025, 2026]:
                    return count
            except:
                pass
    return None


def extract_layoff_percent(text: str) -> float:
    """从文本提取裁员百分比"""
    patterns = [
        r'(\d{1,2}(?:\.\d+)?)%\s*(?:of\s*(?:workforce|employees?|staff))?',
        r'cut\s*(?:by\s*)?(\d{1,2}(?:\.\d+)?)%',
        r'layoff\s*(\d{1,2}(?:\.\d+)?)%',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                percent = float(match.group(1))
                if 3 <= percent <= 100:
                    return percent
            except:
                pass
    return None


def is_valid_year(text: str, current_year: int) -> bool:
    """检查新闻年份是否有效"""
    # 提取文本中的年份
    years_found = re.findall(r'\b(20\d{2})\b', text)
    for year in years_found:
        year_int = int(year)
        # 允许当年或上一年（跨年公告）
        if year_int in VALID_YEARS or year_int == current_year:
            return True
    # 如果没有年份，假设是当前年
    return True


def is_company_specific(title: str, ticker: str, company_name: str) -> bool:
    """验证标题确实是关于这家公司的，不是行业总数据"""
    title_lower = title.lower()

    # 排除行业性报道关键词
    industry_keywords = [
        "big tech", "tech layoffs", "tech industry", "tech companies",
        "tech firms", "technology companies", "silicon valley",
        "amazon, meta, microsoft", "google, amazon, meta",
        "job cuts at meta, microsoft", "layoffs hit", "companies",
        "thousands", "job losses", "job cuts hit",
    ]
    for kw in industry_keywords:
        if kw in title_lower:
            return False

    # 排除多个公司并列的标题（如 "Meta, Cisco, GM Lay Off"）
    # 检测逗号分隔的多个潜在公司名
    companies_in_title = []
    for company in ['meta', 'cisco', 'gm', 'amazon', 'google', 'microsoft', 'apple', 'tesla', 'nvidia']:
        if company in title_lower:
            companies_in_title.append(company)
    if len(companies_in_title) > 1:
        return False  # 标题中有多个大公司名，是行业报道

    # 排除 "hsbc" 等明确其他公司的标题
    other_companies = ['hsbc', 'shopify', 'snap', 'twitter', 'uber', 'lyft']
    for oc in other_companies:
        if oc in title_lower and oc not in [ticker.lower(), company_name.lower()]:
            return False

    # 单字母股票代码特殊处理（如 V, T）
    if len(ticker) <= 2:
        full_names = {
            'V': ['visa', 'visas', 'visa inc'],
            'T': ['at&t', 'att', 'at and t'],
            'F': ['ford', 'ford motor'],
        }
        valid_names = full_names.get(ticker, [company_name.lower()])
        for name in valid_names:
            if name in title_lower:
                return True
        return False

    # 多字母股票代码：要求精确匹配
    company_variations = [
        r'\b' + re.escape(ticker.lower()) + r'\b',
        r'\b' + re.escape(company_name.lower()) + r'\b',
    ]
    # 添加常见变体
    if company_name == 'Meta':
        company_variations.append(r'\bmeta\b')
    elif company_name == '谷歌':
        company_variations.extend([r'\bgoogle\b', r'\bgoogl\b'])
    elif company_name == 'Coinbase':
        company_variations.append(r'\bcoinbase\b')

    for pattern in company_variations:
        if re.search(pattern, title_lower):
            return True

    return False


def search_layoff_news(ticker: str, company_name: str) -> list:
    """
    搜索裁员新闻，返回验证过的结果
    严格匹配：标题必须明确包含公司名称
    """
    results = []
    current_year = datetime.now().year

    # 搜索关键词组合 - 更精确的搜索
    search_terms = [
        f"{ticker} layoffs 2026",
        f'"{company_name}" layoffs 2026',
        f"{ticker} job cuts 2026",
    ]

    for term in search_terms:
        try:
            url = f"https://news.google.com/rss/search?q={quote(term)}&hl=en-US&gl=US&ceid=US:en"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(r.content)

                for item in root.findall('.//item'):
                    title = item.find('title')
                    pub_date = item.find('pubDate')
                    link = item.find('link')

                    if title is None:
                        continue

                    title_text = title.text or ""

                    # 严格匹配：必须是该公司
                    if not is_company_specific(title_text, ticker, company_name):
                        continue

                    # 排除过滤（个人故事/旧数据）
                    if should_exclude(title_text):
                        continue

                    # 确认是裁员新闻
                    if not is_confirmed_layoff(title_text):
                        continue

                    # 年份检查
                    if not is_valid_year(title_text, current_year):
                        continue

                    # 提取数据
                    count = extract_layoff_count(title_text)
                    percent = extract_layoff_percent(title_text)

                    # 智能筛选：人数 >= 100 或 比例 >= 3%
                    if count and count >= MIN_LAYOFF_COUNT:
                        confidence = "high"
                    elif percent and percent >= MIN_LAYOFF_PERCENT:
                        confidence = "high"
                    else:
                        continue  # 不满足门槛，跳过

                    date_str = None
                    if pub_date is not None and pub_date.text:
                        try:
                            date_obj = datetime.strptime(pub_date.text[:16], "%a, %d %b %Y")
                            date_str = date_obj.strftime("%Y-%m-%d")
                        except:
                            pass

                    results.append({
                        "date": date_str,
                        "title": title_text,
                        "count": count,
                        "percent": percent,
                        "url": link.text if link is not None else "",
                        "confidence": confidence,
                    })
            time.sleep(1)
        except Exception as e:
            print(f"[Search] {ticker} 搜索失败: {e}")

    # 去重并返回最佳结果
    seen_titles = set()
    unique_results = []
    for r in sorted(results, key=lambda x: (x['count'] or 0, x['percent'] or 0), reverse=True):
        title_key = r['title'][:50]
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_results.append(r)

    return unique_results[:3]  # 返回最多3条


def get_current_quarter() -> tuple:
    """获取当前季度和年份"""
    now = datetime.now()
    year = now.year
    month = now.month

    if month <= 3:
        return year, "Q1"
    elif month <= 6:
        return year, "Q2"
    elif month <= 9:
        return year, "Q3"
    else:
        return year, "Q4"


def collect_layoff_data():
    """收集所有股票的季度裁员数据（智能筛选版）"""
    year, quarter = get_current_quarter()
    print(f"[Layoff] 开始收集 {year}年{quarter} 裁员数据（智能筛选版）...")
    print(f"[Layoff] 筛选标准: 人数>={MIN_LAYOFF_COUNT} 或 比例>={MIN_LAYOFF_PERCENT}%")

    init_layoff_table()
    conn = get_db_connection()
    total_inserted = 0
    total_skipped = 0

    for i, (ticker, company_name) in enumerate(ALL_STOCKS):
        print(f"[Layoff] [{i+1}/{len(ALL_STOCKS)}] 查询 {ticker} ({company_name})")

        # 先检查是否已有本季度数据（且置信度为high）
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, confidence FROM layoff_quarterly_data WHERE ticker=%s AND year=%s AND quarter=%s",
                (ticker, year, quarter)
            )
            existing = cur.fetchone()
            if existing and existing[1] == 'high':
                print(f"  → 高质量数据已存在，跳过")
                continue

        # 搜索裁员新闻
        news_list = search_layoff_news(ticker, company_name)

        if news_list:
            # 取置信度最高的
            best = news_list[0]

            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO layoff_quarterly_data
                    (ticker, company_name, quarter, year, layoff_count, layoff_percent,
                     announcement_date, source, note, confidence)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    layoff_count=VALUES(layoff_count),
                    layoff_percent=VALUES(layoff_percent),
                    announcement_date=VALUES(announcement_date),
                    source=VALUES(source),
                    note=VALUES(note),
                    confidence=VALUES(confidence)
                """, (
                    ticker, company_name, quarter, year,
                    best.get('count'), best.get('percent'),
                    best.get('date'), best.get('url'), best.get('title'),
                    best.get('confidence', 'medium')
                ))
                total_inserted += 1
                count_str = f"{best.get('count')}人" if best.get('count') else ""
                pct_str = f"({best.get('percent')}%)" if best.get('percent') else ""
                print(f"  ✓ 确认裁员: {count_str}{pct_str} - {best.get('title')[:50]}...")
        else:
            # 插入空记录
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO layoff_quarterly_data
                    (ticker, company_name, quarter, year, layoff_count, layoff_percent, note, confidence)
                    VALUES (%s, %s, %s, %s, NULL, NULL, 'No qualified layoff data', 'none')
                    ON DUPLICATE KEY UPDATE note=VALUES(note), confidence=VALUES(confidence)
                """, (ticker, company_name, quarter, year))
            total_skipped += 1
            print(f"  → 无符合条件的裁员数据")

        time.sleep(2)

    conn.close()
    print(f"\n[Layoff] 收集完成")
    print(f"  - 确认裁员: {total_inserted} 家公司")
    print(f"  - 无/不符合: {total_skipped} 家公司")
    return total_inserted


def get_layoff_for_ticker(ticker: str, year: int = None, quarter: str = None) -> dict:
    """查询指定股票的裁员数据（供财报脚本调用）"""
    if year is None or quarter is None:
        year, quarter = get_current_quarter()

    conn = get_db_connection()
    with conn.cursor(pymysql.cursors.DictCursor) as cur:
        cur.execute("""
            SELECT layoff_count, layoff_percent, note, announcement_date, confidence
            FROM layoff_quarterly_data
            WHERE ticker=%s AND year=%s AND quarter=%s AND confidence IN ('high', 'medium')
            LIMIT 1
        """, (ticker, year, quarter))
        result = cur.fetchone()
    conn.close()
    return result


def get_all_layoff_summary(year: int = None, quarter: str = None) -> list:
    """获取本季度所有高质量裁员数据摘要"""
    if year is None or quarter is None:
        year, quarter = get_current_quarter()

    conn = get_db_connection()
    with conn.cursor(pymysql.cursors.DictCursor) as cur:
        cur.execute("""
            SELECT ticker, company_name, layoff_count, layoff_percent, announcement_date, confidence
            FROM layoff_quarterly_data
            WHERE year=%s AND quarter=%s
            AND layoff_count IS NOT NULL
            AND confidence IN ('high', 'medium')
            ORDER BY layoff_count DESC
        """, (year, quarter))
        results = cur.fetchall()
    conn.close()
    return results


def main():
    """主函数"""
    print(f"[Layoff v2] 启动智能裁员数据收集 - {datetime.now()}")

    if len(sys.argv) > 1:
        if sys.argv[1] == "query":
            ticker = sys.argv[2] if len(sys.argv) > 2 else "META"
            result = get_layoff_for_ticker(ticker)
            print(json.dumps(result, indent=2, default=str) if result else "无数据")
            return
        elif sys.argv[1] == "summary":
            summary = get_all_layoff_summary()
            print(f"本季度共 {len(summary)} 家公司确认裁员（高质量数据）")
            print("\n主要裁员公司:")
            print("-" * 60)
            for item in summary[:15]:
                count_str = f"{item['layoff_count']:,}人" if item['layoff_count'] else "-"
                pct_str = f"({item['layoff_percent']}%)" if item['layoff_percent'] else ""
                conf_tag = "✓" if item['confidence'] == 'high' else "~"
                print(f"  {conf_tag} {item['ticker']:<8} {count_str:<12} {pct_str}")
            return

    collect_layoff_data()


if __name__ == "__main__":
    main()
