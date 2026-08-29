"""
季度裁员数据追踪 - 从新闻源收集并写入MySQL
执行频率：每季度一次（或每周在财报季）
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
import yfinance as yf

# ============ 股票列表（与 earnings.py 保持一致） ============
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uk_ticker_quarter_year (ticker, quarter, year),
                INDEX idx_year_quarter (year, quarter),
                INDEX idx_ticker (ticker)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='季度裁员数据'
        """)
        # 修复已存在表的字段类型
        try:
            cur.execute("ALTER TABLE layoff_quarterly_data MODIFY COLUMN source TEXT")
        except:
            pass
    conn.close()
    print("[DB] 表 layoff_quarterly_data 初始化完成")


def search_layoff_news(ticker: str, company_name: str) -> list:
    """
    从 Google News RSS 搜索裁员新闻
    返回: [{date, title, source, url, count, percent}, ...]
    """
    results = []

    # 搜索关键词组合
    search_terms = [
        f"{ticker} layoff",
        f"{company_name} layoff",
        f"{ticker} job cut",
        f"{company_name} job cut",
    ]

    for term in search_terms:
        try:
            url = f"https://news.google.com/rss/search?q={quote(term)}&hl=en-US&gl=US&ceid=US:en"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(r.content)

                # 解析 RSS
                for item in root.findall('.//item'):
                    title = item.find('title')
                    pub_date = item.find('pubDate')
                    link = item.find('link')

                    if title is not None:
                        title_text = title.text or ""
                        # 提取裁员人数
                        count = extract_layoff_count(title_text)
                        percent = extract_layoff_percent(title_text)

                        if count or percent:
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
                            })
            time.sleep(1)
        except Exception as e:
            print(f"[Search] {ticker} 搜索失败: {e}")

    return results


def extract_layoff_count(text: str) -> int:
    """从标题提取裁员人数"""
    patterns = [
        r'(\d+(?:,\d+)*)\s*(?:employees?|workers?|staff|jobs?|people)',
        r'lay\s*off\s*(\d+(?:,\d+)*)',
        r'layoffs?\s*(?:of\s*)?(\d+(?:,\d+)*)',
        r'cut\s*(\d+(?:,\d+)*)\s*(?:employees?|jobs?)',
        r'(\d+(?:,\d+)*)\s*job\s*cuts',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1).replace(',', ''))
            except:
                pass
    return None


def extract_layoff_percent(text: str) -> float:
    """从标题提取裁员百分比"""
    patterns = [
        r'(\d+(?:\.\d+)?)%\s*(?:of\s*(?:workforce|employees?|staff))?',
        r'cut\s*(?:by\s*)?(\d+(?:\.\d+)?)%',
        r'layoff\s*(\d+(?:\.\d+)?)%',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                percent = float(match.group(1))
                if 0 < percent <= 100:
                    return percent
            except:
                pass
    return None


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
    """收集所有股票的季度裁员数据"""
    year, quarter = get_current_quarter()
    print(f"[Layoff] 开始收集 {year}年{quarter} 裁员数据...")

    init_layoff_table()
    conn = get_db_connection()
    total_inserted = 0

    for i, (ticker, company_name) in enumerate(ALL_STOCKS):
        print(f"[Layoff] [{i+1}/{len(ALL_STOCKS)}] 查询 {ticker} ({company_name})")

        # 先检查是否已有本季度数据
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM layoff_quarterly_data WHERE ticker=%s AND year=%s AND quarter=%s",
                (ticker, year, quarter)
            )
            if cur.fetchone():
                print(f"  → 本季度数据已存在，跳过")
                continue

        # 搜索裁员新闻
        news_list = search_layoff_news(ticker, company_name)

        if news_list:
            # 取最新的一条
            latest = news_list[0]

            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO layoff_quarterly_data
                    (ticker, company_name, quarter, year, layoff_count, layoff_percent,
                     announcement_date, source, note)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    layoff_count=VALUES(layoff_count),
                    layoff_percent=VALUES(layoff_percent),
                    announcement_date=VALUES(announcement_date),
                    source=VALUES(source),
                    note=VALUES(note)
                """, (
                    ticker, company_name, quarter, year,
                    latest.get('count'), latest.get('percent'),
                    latest.get('date'), latest.get('url'), latest.get('title')
                ))
                total_inserted += 1
                print(f"  ✓ 找到裁员数据: {latest.get('title')[:60]}...")
        else:
            # 插入空记录，表示已查询但无数据
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO layoff_quarterly_data
                    (ticker, company_name, quarter, year, layoff_count, layoff_percent, note)
                    VALUES (%s, %s, %s, %s, NULL, NULL, 'No layoff data found')
                    ON DUPLICATE KEY UPDATE note=VALUES(note)
                """, (ticker, company_name, quarter, year))

        time.sleep(2)  # 避免请求过快

    conn.close()
    print(f"[Layoff] 数据收集完成，新增/更新 {total_inserted} 条记录")
    return total_inserted


def get_layoff_for_ticker(ticker: str, year: int = None, quarter: str = None) -> dict:
    """
    查询指定股票的裁员数据（供财报脚本调用）
    :return: {layoff_count, layoff_percent, note, announcement_date} or None
    """
    if year is None or quarter is None:
        year, quarter = get_current_quarter()

    conn = get_db_connection()
    with conn.cursor(pymysql.cursors.DictCursor) as cur:
        cur.execute("""
            SELECT layoff_count, layoff_percent, note, announcement_date
            FROM layoff_quarterly_data
            WHERE ticker=%s AND year=%s AND quarter=%s
            LIMIT 1
        """, (ticker, year, quarter))
        result = cur.fetchone()
    conn.close()
    return result


def get_buyback_for_ticker(ticker: str, year: int = None, quarter: str = None) -> dict:
    """
    查询指定股票的回购数据（供财报脚本调用）
    :return: {buyback_amount, buyback_percent, note, announcement_date} or None
    """
    if year is None or quarter is None:
        year, quarter = get_current_quarter()

    conn = get_db_connection()
    with conn.cursor(pymysql.cursors.DictCursor) as cur:
        cur.execute("""
            SELECT buyback_amount, buyback_percent, note, announcement_date
            FROM buyback_quarterly_data
            WHERE ticker=%s AND year=%s AND quarter=%s
            LIMIT 1
        """, (ticker, year, quarter))
        result = cur.fetchone()
    conn.close()
    return result


def get_all_layoff_summary(year: int = None, quarter: str = None) -> list:
    """获取本季度所有裁员数据摘要"""
    if year is None or quarter is None:
        year, quarter = get_current_quarter()

    conn = get_db_connection()
    with conn.cursor(pymysql.cursors.DictCursor) as cur:
        cur.execute("""
            SELECT ticker, company_name, layoff_count, layoff_percent, announcement_date
            FROM layoff_quarterly_data
            WHERE year=%s AND quarter=%s AND layoff_count IS NOT NULL
            ORDER BY layoff_count DESC
        """, (year, quarter))
        results = cur.fetchall()
    conn.close()
    return results


def main():
    """主函数"""
    print(f"[Layoff] 启动裁员数据收集 - {datetime.now()}")

    # 检查命令行参数
    if len(sys.argv) > 1:
        if sys.argv[1] == "query":
            # 查询模式
            ticker = sys.argv[2] if len(sys.argv) > 2 else "META"
            result = get_layoff_for_ticker(ticker)
            print(json.dumps(result, indent=2, default=str) if result else "无数据")
            return
        elif sys.argv[1] == "summary":
            # 摘要模式
            summary = get_all_layoff_summary()
            print(f"本季度共 {len(summary)} 家公司有裁员数据")
            for item in summary[:10]:
                print(f"  {item['ticker']}: {item['layoff_count']}人 ({item['layoff_percent']}%)")
            return

    # 默认：收集数据
    collect_layoff_data()


if __name__ == "__main__":
    main()
