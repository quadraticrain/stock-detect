"""
美股/日股/港股/A股 财报日历提醒
架构: MySQL缓存优先 → yfinance补查 → 写入缓存 → 过滤推送
"""
import sys
import os
import warnings
import time
import json
from datetime import datetime, timedelta

warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(__file__))

import yfinance as yf
import pandas as pd
import pymysql
from bark import push_earnings_json, DB_CONFIG
from layoff import get_layoff_for_ticker, get_buyback_for_ticker, get_current_quarter

# ============ 股票列表 ============
US_STOCKS = [
    ("NVDA", "英伟达"), ("GOOGL", "谷歌"), ("AAPL", "苹果"),
    ("MSFT", "微软"), ("AMZN", "亚马逊"), ("TSM", "台积电"), ("AVGO", "博通"),
    ("TSLA", "特斯拉"), ("META", "Meta"), ("LLY", "礼来"), ("WMT", "沃尔玛"),
    ("BRK-B", "伯克希尔"), ("MU", "美光科技"), ("JPM", "摩根大通"),
    ("AMD", "超威半导体"), ("XOM", "埃克森美孚"), ("ASML", "阿斯麦"),
    ("V", "维萨"), ("INTC", "英特尔"), ("JNJ", "强生"), ("COST", "好市多"),
    ("CSCO", "思科"), ("MA", "万事达"), ("CAT", "卡特彼勒"), ("CVX", "雪佛龙"),
    ("NFLX", "奈飞"), ("BAC", "美国银行"), ("KO", "可口可乐"), ("UNH", "联合健康"),
    ("AMAT", "应用材料"), ("PG", "宝洁"), ("PLTR", "Palantir"), ("ARM", "ARM"),
    ("MS", "摩根士丹利"), ("GS", "高盛"), ("MRK", "默沙东"),
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

JP_STOCKS = [
    ("7203.T", "丰田汽车"), ("8306.T", "三菱UFJ金融"), ("6758.T", "索尼"),
    ("6861.T", "基恩士"), ("6098.T", "瑞可利"), ("8316.T", "三井住友金融"),
    ("4519.T", "中外制药"), ("9984.T", "软银集团"), ("6501.T", "日立"),
    ("4063.T", "信越化学"), ("8058.T", "三菱商事"), ("9434.T", "软银"),
    ("8031.T", "三井物产"), ("8411.T", "瑞穗金融"), ("6702.T", "富士通"),
    ("6146.T", "迪思科"), ("4503.T", "安斯泰来制药"),
]

HK_STOCKS = [
    ("0700.HK", "腾讯控股"), ("0981.HK", "中芯国际"), ("9988.HK", "阿里巴巴"),
    ("1347.HK", "华虹半导体"), ("9999.HK", "网易-S"), ("0388.HK", "香港交易所"),
    ("0005.HK", "汇丰控股"), ("9961.HK", "携程集团-S"), ("6185.HK", "老铺黄金"),
    ("3690.HK", "美团"), ("2382.HK", "舜宇光学科技"), ("9992.HK", "泡泡玛特"),
    ("0002.HK", "中电控股"), ("0012.HK", "恒生银行"), ("1299.HK", "友邦保险"), ("6160.HK", "百济神州"),
    ("0941.HK", "中国移动"), ("1211.HK", "比亚迪股份"), ("9888.HK", "百度集团-SW"),
    ("0992.HK", "联想集团"), ("9618.HK", "京东集团-SW"), ("2899.HK", "紫金黄金国际"),
    ("9626.HK", "哔哩哔哩"), ("1810.HK", "小米集团"), ("2318.HK", "中国平安"),
    ("2015.HK", "理想汽车-W"), ("2888.HK", "渣打集团"), ("2899.HK", "紫金矿业"),
    ("0669.HK", "创科实业"), ("1801.HK", "信达生物"), ("9868.HK", "小鹏集团-W"),
    ("9926.HK", "康方生物"), ("1024.HK", "快手-W"),
    ("2359.HK", "药明康德"), ("0883.HK", "中国海洋石油"), ("0001.HK", "长和"),
    ("0300.HK", "美的集团"), ("1772.HK", "赣锋锂业"), ("1109.HK", "华润置地"),
    ("2388.HK", "中银香港"), ("2020.HK", "安踏体育"), ("2628.HK", "中国人寿"),
    ("2097.HK", "蜜雪集团"), ("3968.HK", "招商银行"), ("0002.HK", "中电控股"),
    ("0358.HK", "江西铜业股份"), ("2269.HK", "药明生物"), ("1378.HK", "中国宏桥"),
    ("3993.HK", "洛阳钼业"), ("2018.HK", "瑞声科技"), ("1088.HK", "中国神华"),
    ("0006.HK", "电能实业"), ("0939.HK", "建设银行"), ("0175.HK", "吉利汽车"),
    ("1336.HK", "新华保险"), ("9633.HK", "农夫山泉"), ("2601.HK", "中国太保"),
    ("0857.HK", "中国石油股份"), ("1113.HK", "长实集团"), ("1398.HK", "工商银行"),
    ("0012.HK", "恒基地产"), ("6690.HK", "海尔智家"), ("0027.HK", "银河娱乐"),
    ("2319.HK", "蒙牛乳业"), ("0285.HK", "比亚迪电子"), ("1171.HK", "兖矿能源"),
    ("1919.HK", "中远海控"), ("1093.HK", "石药集团"), ("9901.HK", "新东方-S"),
    ("2328.HK", "中国财险"), ("3888.HK", "金山软件"), ("1288.HK", "中国银行"),
    ("6030.HK", "中信证券"), ("0066.HK", "港铁公司"), ("0836.HK", "华润电力"),
    ("9660.HK", "地平线机器人"),
    ("2218.HK", "大族数控"), ("2058.HK", "鸣鸣很忙"), ("2600.HK", "中国铝业"),
    ("1898.HK", "中煤能源"), ("0267.HK", "中信股份"), ("1288.HK", "农业银行"),
    ("0914.HK", "海螺水泥"), ("1928.HK", "金沙中国"), ("0788.HK", "中国铁塔"),
    ("0728.HK", "中国电信"), ("0293.HK", "国泰航空"), ("0288.HK", "万洲国际"),
    ("0762.HK", "中国联通"), ("0386.HK", "中国石油化工"), ("0902.HK", "华能国际电力"),
    ("0998.HK", "中信银行"), ("1339.HK", "中国人民保险"), ("1177.HK", "中国生物制药"),
    ("2333.HK", "长城汽车"), ("1876.HK", "百威亚太"), ("0003.HK", "香港中华煤气"),
    ("1816.HK", "中广核电力"), ("1099.HK", "国药控股"), ("3328.HK", "交通银行"),
    ("0868.HK", "信义玻璃"), ("1658.HK", "邮储银行"), ("0135.HK", "昆仑能源"),
    ("0753.HK", "中国国航"), ("0968.HK", "信义光能"), ("9898.HK", "微博-SW"),
    ("2282.HK", "美高梅中国"), ("1186.HK", "中国铁建"), ("0390.HK", "中国中铁"),
    ("1800.HK", "中国交通建设"), ("2238.HK", "广汽集团"), ("1359.HK", "中国信达"),
]

A_STOCKS = [
    ("600900.SS", "长江电力"),
]

ALL_STOCKS = US_STOCKS + JP_STOCKS + HK_STOCKS + A_STOCKS

WEEKDAY_MAP = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}
CURRENCY_MAP = {"US": "$", "JP": "¥", "HK": "HK$", "CN": "¥"}


def detect_market(ticker: str) -> str:
    """根据ticker判断市场"""
    if ticker.endswith(".T"):
        return "JP"
    elif ticker.endswith(".HK"):
        return "HK"
    elif ticker.endswith(".SS") or ticker.endswith(".SZ"):
        return "CN"
    else:
        return "US"


def _format_layoff(layoff_data: dict) -> str:
    """格式化裁员数据显示"""
    if not layoff_data:
        return "—"
    count = layoff_data.get('layoff_count')
    percent = layoff_data.get('layoff_percent')
    if count and percent:
        return f"{count}人({percent}%)"
    elif count:
        return f"{count}人"
    elif percent:
        return f"{percent}%"
    else:
        return "—"


def _format_buyback(buyback_data: dict) -> str:
    """格式化回购数据显示"""
    if not buyback_data:
        return "—"
    amount = buyback_data.get('buyback_amount')
    percent = buyback_data.get('buyback_percent')
    if amount and percent:
        return f"{amount}({percent}%)"
    elif amount:
        return f"{amount}"
    elif percent:
        return f"占市值{percent}%"
    else:
        return "—"


def _get_db_conn():
    """获取MySQL连接"""
    return pymysql.connect(**DB_CONFIG)


def query_earnings_cache(ticker: str) -> dict:
    """
    从MySQL缓存查询财报数据
    返回: dict or None
    """
    conn = _get_db_conn()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("""
                SELECT stock_code, stock_name, market, earnings_date,
                       expected_eps, eps_yoy_change, current_price, price_currency,
                       has_layoff, earnings_date_confirmed, data_source,
                       cached_at, expires_at
                FROM earnings_cache
                WHERE stock_code = %s AND expires_at > NOW()
                ORDER BY earnings_date DESC
                LIMIT 1
            """, (ticker,))
            return cur.fetchone()
    except Exception as e:
        print(f"[Cache] 查询 {ticker} 缓存失败: {e}")
        return None
    finally:
        conn.close()


def save_to_earnings_cache(ticker: str, name: str, market: str,
                           earnings_date, eps_est, eps_actual, yoy_str,
                           price, currency, has_layoff, data_source="yfinance"):
    """
    写入财报数据到MySQL缓存
    过期时间: 财报日期后7天
    """
    if earnings_date is None:
        return

    # 计算过期时间
    if isinstance(earnings_date, str):
        from datetime import datetime as _dt
        earnings_date = _dt.strptime(earnings_date, "%Y-%m-%d").date()
    expires_at = earnings_date + timedelta(days=7)

    # 解析yoy
    yoy_val = None
    if yoy_str:
        import re
        m = re.search(r'([+-]?\d+)', yoy_str)
        if m:
            yoy_val = float(m.group(1))

    # eps: 优先actual，其次estimate；NaN→None避免MySQL DECIMAL报错
    def _safe_float(val):
        if val is None:
            return None
        try:
            if pd.isna(val):
                return None
            f = float(val)
            return f if pd.notna(f) else None
        except (ValueError, TypeError):
            return None

    eps_val = _safe_float(eps_actual) or _safe_float(eps_est)
    price = _safe_float(price)
    yoy_val = _safe_float(yoy_val) if yoy_val else None

    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO earnings_cache
                (stock_code, stock_name, market, earnings_date,
                 expected_eps, eps_yoy_change, current_price, price_currency,
                 has_layoff, earnings_date_confirmed, data_source,
                 cached_at, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s)
                ON DUPLICATE KEY UPDATE
                expected_eps=VALUES(expected_eps),
                eps_yoy_change=VALUES(eps_yoy_change),
                current_price=VALUES(current_price),
                price_currency=VALUES(price_currency),
                has_layoff=VALUES(has_layoff),
                data_source=VALUES(data_source),
                cached_at=NOW(),
                expires_at=VALUES(expires_at)
            """, (
                ticker, name, market, earnings_date,
                eps_val, yoy_val, price, currency,
                1 if has_layoff else 0,
                1 if eps_actual and pd.notna(eps_actual) else 0,
                data_source, expires_at
            ))
    except Exception as e:
        print(f"[Cache] 写入 {ticker} 缓存失败: {e}")
    finally:
        conn.close()


def _calc_eps_yoy(stock, eps_current, earnings_date) -> float:
    """
    从earnings_history计算EPS同比增长率（v2：更稳健的日期匹配 + 合理性校验）
    eps_current: 当前季度预期或实际EPS
    earnings_date: 财报日期
    返回: 同比增长率(%) or None
    """
    if not eps_current or (isinstance(eps_current, float) and pd.isna(eps_current)):
        return None
    try:
        eps_current = float(eps_current)
    except (ValueError, TypeError):
        return None

    try:
        hist = stock.earnings_history
        if hist is None or hist.empty:
            return None

        target_date = earnings_date.replace(year=earnings_date.year - 1) if hasattr(earnings_date, 'replace') else None
        if target_date is None:
            return None

        # v2: 收集所有符合条件的candidates（而非取第一条），选日期最接近的
        candidates = []
        for idx in hist.index:
            if hasattr(idx, 'date'):
                d = idx.date()
            else:
                d = pd.to_datetime(idx).date()

            delta = abs((d - target_date).days)
            # 第一轮：±60天窗口（比原来更宽，避免漏掉不同公告节奏的公司）
            if delta < 60:
                val = hist.loc[idx].get('epsActual')
                if val is not None and pd.notna(val):
                    try:
                        candidates.append((delta, float(val), d))
                    except (ValueError, TypeError):
                        continue

        if candidates:
            # 取日期最接近target_date的那条
            candidates.sort(key=lambda x: x[0])
            _, old_eps, matched_date = candidates[0]

            if old_eps != 0:
                yoy = (eps_current - old_eps) / abs(old_eps) * 100

                # v2: 合理性校验 — 极端值标记为None（后续由AI审核任务兜底修正）
                if abs(yoy) > 800:
                    print(f"[YoY warn] {stock.ticker}: yoy={yoy:.1f}% "
                          f"(eps_current={eps_current}, old_eps={old_eps}, "
                          f"matched_date={matched_date}) → 极端值，标记None等AI审核")
                    return None
                # 如果当前EPS和去年同期EPS的比值超过10倍，也标记
                if eps_current > 0 and old_eps > 0:
                    ratio = max(eps_current, old_eps) / min(eps_current, old_eps)
                    if ratio > 10:
                        print(f"[YoY warn] {stock.ticker}: eps ratio={ratio:.1f}x "
                              f"(eps_current={eps_current}, old_eps={old_eps}) "
                              f"→ 疑似数据异常，标记None等AI审核")
                        return None

                return round(yoy, 1)

    except Exception as e:
        print(f"[YoY err] {stock.ticker}: {e}")
    return None


def _query_yfinance(ticker: str, name: str, market: str, cutoff_date) -> dict:
    """
    从yfinance查询单只股票的财报数据
    返回: dict or None
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}

        # 获取当前股价
        price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose')
        currency = info.get('currency', 'USD')
        price_str = None
        if price and pd.notna(price):
            if currency == 'JPY':
                price_str = f"¥{price:.0f}"
            elif currency == 'HKD' or market == 'HK':
                price_str = f"HK${price:.2f}"
            else:
                price_str = f"${price:.2f}"

        # 方法1: earnings_dates
        ed_df = stock.earnings_dates
        if ed_df is not None and not ed_df.empty:
            for date_val in ed_df.index[:4]:
                if hasattr(date_val, 'date'):
                    ed = date_val.date()
                elif isinstance(date_val, str):
                    ed = pd.to_datetime(date_val).date()
                else:
                    continue

                if ed >= cutoff_date:
                    row = ed_df.loc[date_val]
                    eps_est = None
                    eps_actual = None
                    if isinstance(row, pd.Series):
                        eps_est = row.get('epsEstimate') or row.get('EPS Estimate')
                        eps_actual = row.get('epsActual') or row.get('EPS Actual')

                    # 计算EPS同比增长
                    eps_for_yoy = eps_actual if (eps_actual and pd.notna(eps_actual)) else eps_est
                    yoy_pct = _calc_eps_yoy(stock, eps_for_yoy, ed)
                    yoy_str = f"(同比{yoy_pct:+.0f}%)" if yoy_pct is not None else ""

                    # 裁员数据
                    year, quarter = get_current_quarter()
                    layoff_data = get_layoff_for_ticker(ticker, year, quarter)
                    layoff_str = _format_layoff(layoff_data)

                    # 回购数据
                    buyback_data = get_buyback_for_ticker(ticker, year, quarter)
                    buyback_str = _format_buyback(buyback_data)

                    result = {
                        "ticker": ticker,
                        "name": name,
                        "market": market,
                        "date": ed,
                        "date_str": ed.strftime("%m/%d"),
                        "weekday": WEEKDAY_MAP.get(ed.weekday(), "?"),
                        "eps_est": eps_est,
                        "eps_actual": eps_actual,
                        "yoy_pct": yoy_pct,
                        "yoy_str": yoy_str,
                        "price_str": price_str,
                        "layoff": layoff_str,
                        "buyback": buyback_str,
                        "price": price,
                        "currency": currency,
                    }

                    # 写入缓存
                    save_to_earnings_cache(
                        ticker, name, market, ed,
                        eps_est, eps_actual, yoy_str,
                        price, currency,
                        layoff_str != "—",
                    )

                    return result

        # 方法2: calendar备用
        cal = stock.calendar
        earnings_date = None
        if isinstance(cal, dict):
            ed_val = cal.get("Earnings Date")
            if ed_val is not None:
                if isinstance(ed_val, (list, tuple)) and len(ed_val) > 0:
                    earnings_date = ed_val[0]
                elif not isinstance(ed_val, (list, tuple)):
                    earnings_date = ed_val
        elif isinstance(cal, pd.DataFrame) and not cal.empty:
            if "Earnings Date" in cal.index:
                earnings_date = cal.loc["Earnings Date"].values[0]

        if earnings_date is not None:
            if hasattr(earnings_date, 'date'):
                ed = earnings_date.date()
            elif isinstance(earnings_date, str):
                ed = pd.to_datetime(earnings_date).date()
            else:
                ed = None

            if ed and ed >= cutoff_date:
                # 计算EPS同比增长（calendar方式无EPS数据，尝试从earnings_history推算）
                yoy_pct = None
                try:
                    yoy_pct = _calc_eps_yoy(stock, None, ed)
                except Exception:
                    pass
                yoy_str = f"(同比{yoy_pct:+.0f}%)" if yoy_pct is not None else ""

                # 裁员数据
                year, quarter = get_current_quarter()
                layoff_data = get_layoff_for_ticker(ticker, year, quarter)
                layoff_str = _format_layoff(layoff_data)

                # 回购数据
                buyback_data = get_buyback_for_ticker(ticker, year, quarter)
                buyback_str = _format_buyback(buyback_data)

                result = {
                    "ticker": ticker,
                    "name": name,
                    "market": market,
                    "date": ed,
                    "date_str": ed.strftime("%m/%d"),
                    "weekday": WEEKDAY_MAP.get(ed.weekday(), "?"),
                    "eps_est": None,
                    "eps_actual": None,
                    "yoy_pct": yoy_pct,
                    "yoy_str": yoy_str,
                    "price_str": price_str,
                    "layoff": layoff_str,
                    "buyback": buyback_str,
                    "price": price,
                    "currency": currency,
                }

                # 写入缓存
                save_to_earnings_cache(
                    ticker, name, market, ed,
                    None, None, yoy_str,
                    price, currency,
                    layoff_str != "—",
                )

                return result

    except Exception as e:
        print(f"[YF] {ticker} 查询异常: {e}")

    return None


def get_earnings_for_week() -> list:
    """
    获取财报数据（MySQL优先 + yfinance补查）
    过滤：过去72小时 + 未来14天（避免推送内容过长）
    """
    now = datetime.now()
    cutoff_date = (now - timedelta(hours=72)).date()
    end_date = (now + timedelta(days=14)).date()

    print(f"[Earnings] 查询范围: {cutoff_date} (过去72小时) ~ {end_date} (未来14天)")
    print(f"[Earnings] 当前时间: {now.strftime('%Y-%m-%d %H:%M')}")

    earnings_list = []
    total = len(ALL_STOCKS)
    cached_count = 0
    network_count = 0

    for i, (ticker, name) in enumerate(ALL_STOCKS):
        market = detect_market(ticker)

        # 1. 先查MySQL缓存
        cached = query_earnings_cache(ticker)

        if cached and cached.get('earnings_date'):
            ed = cached['earnings_date']
            if isinstance(ed, str):
                ed = datetime.strptime(ed, "%Y-%m-%d").date()

            if cutoff_date <= ed <= end_date:
                # 从缓存恢复数据
                eps_val = cached.get('expected_eps')
                yoy_val = cached.get('eps_yoy_change')
                price_val = cached.get('current_price')
                currency = cached.get('price_currency', 'USD')

                # 格式化价格
                price_str = None
                if price_val and pd.notna(price_val):
                    if currency == 'JPY' or market == 'JP':
                        price_str = f"¥{float(price_val):.0f}"
                    elif currency == 'HKD' or market == 'HK':
                        price_str = f"HK${float(price_val):.2f}"
                    else:
                        price_str = f"${float(price_val):.2f}"

                # 缓存中yoy为空 → 自动从yfinance补算并回填
                yoy_pct = float(yoy_val) if (yoy_val and pd.notna(yoy_val)) else None
                if yoy_pct is None and eps_val:
                    try:
                        stock = yf.Ticker(ticker)
                        yoy_pct = _calc_eps_yoy(stock, float(eps_val), ed)
                        if yoy_pct is not None:
                            # 回填到MySQL缓存
                            try:
                                conn2 = _get_db_conn()
                                with conn2.cursor() as cur2:
                                    cur2.execute("""
                                        UPDATE earnings_cache SET eps_yoy_change = %s
                                        WHERE stock_code = %s AND earnings_date = %s
                                    """, (yoy_pct, ticker, ed))
                                conn2.close()
                                print(f"[YoY] 自动补算 {ticker}: {yoy_pct:+.1f}%")
                            except Exception:
                                pass
                    except Exception:
                        pass

                yoy_str = f"(同比{yoy_pct:+.0f}%)" if yoy_pct is not None else ""

                # 裁员
                layoff_str = "—"
                if cached.get('has_layoff'):
                    year, quarter = get_current_quarter()
                    layoff_data = get_layoff_for_ticker(ticker, year, quarter)
                    layoff_str = _format_layoff(layoff_data)

                # 回购
                year, quarter = get_current_quarter()
                buyback_data = get_buyback_for_ticker(ticker, year, quarter)
                buyback_str = _format_buyback(buyback_data)

                earnings_list.append({
                    "ticker": ticker,
                    "name": name,
                    "market": market,
                    "date": ed,
                    "date_str": ed.strftime("%m/%d"),
                    "weekday": WEEKDAY_MAP.get(ed.weekday(), "?"),
                    "eps_est": eps_val,
                    "eps_actual": None if not cached.get('earnings_date_confirmed') else eps_val,
                    "yoy_pct": yoy_pct,
                    "yoy_str": yoy_str,
                    "price_str": price_str,
                    "layoff": layoff_str,
                    "buyback": buyback_str,
                })
                cached_count += 1
                continue

        # 2. 缓存未命中，网络查询
        result = _query_yfinance(ticker, name, market, cutoff_date)
        if result and result.get('date') and result['date'] <= end_date:
            earnings_list.append(result)
            network_count += 1

        # 限流
        if (i + 1) % 20 == 0:
            print(f"[Earnings] 进度: {i+1}/{total} (缓存:{cached_count} 网络:{network_count})")
            time.sleep(3)
        else:
            time.sleep(0.5)

    # 去重 + 排序
    seen = set()
    unique_list = []
    for e in earnings_list:
        key = e["ticker"]
        if key not in seen:
            seen.add(key)
            unique_list.append(e)

    unique_list.sort(key=lambda x: x["date"])

    print(f"\n[Earnings] 查询完成: 缓存命中 {cached_count} / 网络查询 {network_count} / 总计 {len(unique_list)}")
    return unique_list


def format_output(earnings: list) -> str:
    """格式化财报输出（完整字段版；仅本地调试用，线上改走 JSON 分发）"""
    if not earnings:
        return "近72小时及未来无重要财报发布\n\n📌 提醒\n• 下次更新将继续追踪"

    lines = []
    current_date = None

    for e in earnings:
        date_key = f"{e['weekday']} {e['date_str']}"
        if date_key != current_date:
            # 空行分隔：Bark 按 Markdown 渲染，单个换行会被当成 soft break 吞掉
            lines.append(f"🔸 {date_key} 🔸")
            lines.append("")
            current_date = date_key

        market_tag = {"US": "🇺🇸", "JP": "🇯🇵", "HK": "🇭🇰", "CN": "🇨🇳"}.get(e["market"], "")

        # 详细数据（与公司名同一行输出，见下方）
        parts = []

        # EPS信息（优先显示实际vs预期）
        eps_actual = e.get("eps_actual")
        eps_est = e.get("eps_est")
        yoy_pct = e.get("yoy_pct")
        if eps_actual is not None and pd.notna(eps_actual):
            eps_str = f"实际${float(eps_actual):.2f}"
            if eps_est is not None and pd.notna(eps_est):
                eps_str += f" vs 预期${float(eps_est):.2f}"
            parts.append(eps_str)
        elif eps_est is not None and pd.notna(eps_est):
            parts.append(f"预期EPS ${float(eps_est):.2f}")

        # 增长百分比
        if yoy_pct is not None:
            arrow = "🔺" if yoy_pct > 0 else ("🔻" if yoy_pct < 0 else "➡️")
            parts.append(f"{arrow}同比{yoy_pct:+.0f}%")

        # 股价
        if e.get("price_str"):
            parts.append(f"💰{str(e['price_str']).strip()}")

        # 裁员 / 回购：无数据时不占位，财报季公司多时否则易触发 Bark 413
        layoff = e.get("layoff", "—")
        if layoff and layoff != "—":
            parts.append(f"👥 裁员: {layoff}")
        buyback = e.get("buyback", "—")
        if buyback and buyback != "—":
            parts.append(f"🏦 回购: {buyback}")

        # 单行输出：多行 + 前导空格缩进会被 Bark/通知渲染吞掉换行而合并成一行
        head = f"• {e['name']} ({e['ticker']}) {market_tag}".rstrip()
        if parts:
            lines.append(f"{head} — {' ｜ '.join(parts)}")
        else:
            lines.append(f"{head} — 财报日")
        # 每条后补空行，避免同日多只股票被 Markdown soft break 合并成一行
        lines.append("")

    lines.append("📌 提醒")
    lines.append("")
    lines.append(f"• 近72小时及未来14天共{len(earnings)}家公司发布财报")
    lines.append("")
    lines.append("数据来源：MySQL缓存 + Yahoo Finance")

    return "\n".join(lines)


def _json_float(v):
    """pandas/None → JSON 可用 float 或 None。"""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return float(v)


def build_earnings_payload(earnings: list) -> dict:
    """组装交给 Go 后端分发的财报 JSON。"""
    items = []
    for e in earnings:
        ed = e.get("date")
        if hasattr(ed, "isoformat"):
            date_s = ed.isoformat()
        else:
            date_s = str(ed) if ed is not None else ""
        items.append({
            "ticker": e.get("ticker"),
            "name": e.get("name"),
            "market": e.get("market"),
            "date": date_s,
            "date_str": e.get("date_str"),
            "weekday": e.get("weekday"),
            "eps_est": _json_float(e.get("eps_est")),
            "eps_actual": _json_float(e.get("eps_actual")),
            "yoy_pct": _json_float(e.get("yoy_pct")),
            "price_str": e.get("price_str") or "",
            "layoff": e.get("layoff") or "",
            "buyback": e.get("buyback") or "",
        })
    return {
        "title": "📊 美股财报日历·腾讯龙虾",
        "group": "earnings",
        "items": items,
    }


def main():
    """主函数: 获取财报数据 → JSON → 后端分发推送"""
    print(f"[Earnings] 开始获取财报数据 - {datetime.now()}")

    earnings = get_earnings_for_week()
    print(f"[Earnings] 共有{len(earnings)}家公司财报")

    payload = build_earnings_payload(earnings)
    print(f"\n--- 推送 JSON ---\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n--- END ---")

    if not earnings:
        print("[Earnings] 无财报数据，跳过后端分发")
        return {"code": 200, "message": "no earnings"}

    result = push_earnings_json(payload)
    return result


if __name__ == "__main__":
    import sys
    result = main()
    if not result or result.get("code") != 200:
        sys.exit(1)
