"""
IPO打新提醒 - A股新股申购 + 可转债 + 港股IPO
数据源: akshare (东方财富/巨潮资讯) + itiger (老虎证券/港股IPO)
"""
import sys
import os
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(__file__))

import akshare as ak
import pandas as pd
from bark import push_ipo

# ============ 常量 ============
WEEKDAY_MAP = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}
MARKET_EMOJI = {
    "沪主板": "沪主", "深主板": "深主", "科创板": "科创",
    "创业板": "创业", "北交所": "北交",
}
BOARD_MAP = {
    "非科创板": "创业板",  # 深市非科创板=创业板
    "科创板": "科创",
}


def get_a_share_ipo(days: int = 3) -> list:
    """
    获取未来N天A股新股申购
    返回: [{"date": "2026-06-01", "weekday": "周日", "stocks": [...]}]
    """
    try:
        df = ak.stock_xgsglb_em()
    except Exception as e:
        print(f"[IPO] 获取A股IPO数据失败: {e}")
        return []

    today = datetime.now().date()
    end_date = today + timedelta(days=days)

    # 筛选未来N天内申购的股票
    df['申购日期'] = pd.to_datetime(df['申购日期'], errors='coerce')
    df = df.dropna(subset=['申购日期'])
    df['申购日期_dt'] = df['申购日期'].dt.date

    mask = (df['申购日期_dt'] >= today) & (df['申购日期_dt'] <= end_date)
    upcoming = df[mask].copy()

    if upcoming.empty:
        return []

    # 按日期分组
    result = []
    for date_val, group in upcoming.groupby('申购日期_dt'):
        stocks = []
        for _, row in group.iterrows():
            exchange = str(row.get('交易所', ''))
            board = str(row.get('板块', ''))
            # 确定市场标签（先检查非科创板，再检查科创板，避免"非科创板"误匹配）
            market_label = "其他"
            if '北交' in exchange or '北交' in board:
                market_label = "北交"
            elif '非科创' in board:
                market_label = "创业"  # 深市非科创板=创业板
            elif '科创' in board:
                market_label = "科创"
            elif '创业' in board:
                market_label = "创业"
            elif '上海' in exchange:
                market_label = "沪主"
            elif '深圳' in exchange:
                market_label = "深主"

            code = str(row.get('股票代码', ''))
            name = str(row.get('股票简称', ''))
            price = row.get('发行价格', None)
            limit = row.get('申购上限', None)
            subscribe_code = str(row.get('申购代码', ''))
            pe = row.get('发行市盈率', None)

            price_str = f"¥{price:.2f}" if pd.notna(price) and price else "待定"
            limit_str = f"{int(limit)}股" if pd.notna(limit) and limit else "--"
            pe_str = f"PE {pe:.1f}" if pd.notna(pe) and pe else ""

            stocks.append({
                "name": name,
                "code": code,
                "subscribe_code": subscribe_code,
                "market": market_label,
                "price": price_str,
                "limit": limit_str,
                "pe": pe_str,
            })

        weekday = WEEKDAY_MAP.get(date_val.weekday(), "?")
        result.append({
            "date": date_val.strftime("%m/%d"),
            "weekday": weekday,
            "stocks": stocks,
        })

    result.sort(key=lambda x: x["date"])
    return result


def get_convertible_bonds(days: int = 3) -> list:
    """
    获取未来N天可转债申购
    返回: [{"date": "2026-06-01", "weekday": "周日", "bonds": [...]}]
    """
    try:
        df = ak.bond_zh_cov()
    except Exception as e:
        print(f"[CB] 获取可转债数据失败: {e}")
        return []

    today = datetime.now().date()
    end_date = today + timedelta(days=days)

    df['申购日期_dt'] = pd.to_datetime(df['申购日期'], errors='coerce').dt.date
    df = df.dropna(subset=['申购日期_dt'])

    mask = (df['申购日期_dt'] >= today) & (df['申购日期_dt'] <= end_date)
    upcoming = df[mask].copy()

    if upcoming.empty:
        return []

    result = []
    for date_val, group in upcoming.groupby('申购日期_dt'):
        bonds = []
        for _, row in group.iterrows():
            code = str(row.get('债券代码', ''))
            name = str(row.get('债券简称', ''))
            subscribe_code = str(row.get('申购代码', ''))
            conv_price = row.get('转股价', None)
            rating = str(row.get('信用评级', ''))
            stock_name = str(row.get('正股简称', ''))

            conv_str = f"¥{conv_price:.2f}" if pd.notna(conv_price) and conv_price else "待定"
            rating_str = rating if rating and rating != 'nan' else "--"

            bonds.append({
                "name": name,
                "code": code,
                "subscribe_code": subscribe_code,
                "conv_price": conv_str,
                "rating": rating_str,
                "stock_name": stock_name,
            })

        weekday = WEEKDAY_MAP.get(date_val.weekday(), "?")
        result.append({
            "date": date_val.strftime("%m/%d"),
            "weekday": weekday,
            "bonds": bonds,
        })

    result.sort(key=lambda x: x["date"])
    return result


def get_hk_stock_name(symbol: str) -> str:
    """通过东方财富API查询港股中文名（备用，itiger API已自带中文名）"""
    import requests as req
    import time as _time

    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

    try:
        url = f"https://push2his.eastmoney.com/api/qt/stock/get?secid=116.{symbol}&fields=f57,f58"
        r = req.get(url, headers=headers, timeout=5)
        data = r.json()
        if data.get("data") and data["data"].get("f58"):
            _time.sleep(0.3)
            return data["data"]["f58"]
    except Exception:
        pass

    return f"港股{symbol}"


def _parse_ts(ts) -> "date | None":
    """将毫秒时间戳转为date"""
    from datetime import date as date_cls
    if not ts:
        return None
    return datetime.fromtimestamp(ts / 1000).date()


def get_hk_ipo(days: int = 7) -> list:
    """
    获取港股近期IPO信息
    数据源: itiger.com API (老虎证券)
    返回: [{"date": "06/02", "weekday": "周一", "stocks": [...]}]
    """
    import requests as req

    today = datetime.now().date()
    end_date = today + timedelta(days=days)

    try:
        r = req.get(
            "https://hktrade.skytigris.com/ipos/general/unlist",
            params={"lang": "zh_CN", "limit": 50, "market": "HK", "start": 0},
            timeout=15,
        )
        data = r.json()

        if data.get("status") != "ok":
            print(f"[HK] itiger API错误: {data.get('msg', '')}")
            return []

        items = data.get("data", [])
        if not items:
            return []

        result_by_date = {}
        for item in items:
            list_dt = _parse_ts(item.get("listDate"))
            open_dt = _parse_ts(item.get("openingDate"))
            close_dt = _parse_ts(item.get("closingDate"))

            if not list_dt:
                continue

            # 包含条件：上市日在N天内，或当前正处于申购期
            in_list_range = today <= list_dt <= end_date
            in_sub_period = (open_dt and close_dt and open_dt <= today <= close_dt)

            if not (in_list_range or in_sub_period):
                continue

            # 价格区间
            min_p = item.get("minPrice")
            max_p = item.get("maxPrice")
            if min_p and max_p:
                price_str = f"${max_p:.2f}" if min_p == max_p else f"${min_p:.2f}-${max_p:.2f}"
            else:
                price_str = "待定"

            # 申购期
            sub_period = ""
            if open_dt and close_dt:
                sub_period = f"{open_dt.strftime('%m/%d')}-{close_dt.strftime('%m/%d')}"

            # 超额认购倍数
            sub_ratio = item.get("subscribedRatio")
            sub_ratio_str = f"{sub_ratio:.0f}x" if sub_ratio else ""

            # 申购状态标记
            sub_status = ""
            if in_sub_period and close_dt >= today:
                days_left = (close_dt - today).days
                sub_status = f"🔥申购中(剩{days_left}天)" if days_left > 0 else "🔥今日截止"
            elif open_dt and open_dt > today:
                days_to = (open_dt - today).days
                sub_status = f"📅{days_to}天后开放申购"

            stock_info = {
                "name": item.get("companyName", ""),
                "code": item.get("symbol", ""),
                "price": price_str,
                "sub_period": sub_period,
                "sub_ratio": sub_ratio_str,
                "sub_status": sub_status,
                "min_qty": f"{item.get('minQty', '')}股" if item.get("minQty") else "",
            }

            if list_dt not in result_by_date:
                result_by_date[list_dt] = []
            result_by_date[list_dt].append(stock_info)

        # 转换为统一格式
        result = []
        for date_val, stocks in result_by_date.items():
            weekday = WEEKDAY_MAP.get(date_val.weekday(), "?")
            result.append({
                "date": date_val.strftime("%m/%d"),
                "weekday": weekday,
                "stocks": stocks,
            })

        result.sort(key=lambda x: x["date"])
        return result

    except Exception as e:
        print(f"[HK] 获取港股IPO失败: {e}")
        return []


def format_output(ipo_data: list, cb_data: list, hk_data: list) -> str:
    """
    格式化输出为用户友好的推送文本
    """
    lines = []

    # 合并所有日期
    all_dates = set()
    for item in ipo_data:
        all_dates.add((item["date"], item["weekday"]))
    for item in cb_data:
        all_dates.add((item["date"], item["weekday"]))
    for item in hk_data:
        all_dates.add((item["date"], item["weekday"]))

    sorted_dates = sorted(all_dates, key=lambda x: x[0])

    if not sorted_dates:
        return "近3天无打新标的\n\n📌 提醒\n• 当前暂无新股或可转债申购安排\n• 下次更新将继续追踪"

    for date_str, weekday in sorted_dates:
        lines.append(f"🔸 {weekday} {date_str} 🔸")

        # A股新股
        ipo_stocks = []
        for item in ipo_data:
            if item["date"] == date_str:
                ipo_stocks = item["stocks"]
                break

        if ipo_stocks:
            lines.append("")
            lines.append("▣ 新股申购")
            for i, s in enumerate(ipo_stocks):
                is_last = (i == len(ipo_stocks) - 1)
                prefix = "└" if is_last else "├"
                lines.append(f"  ├ {s['name']} ({s['code']}) · {s['market']}")
                detail = f"  {prefix} 📋 发行价：{s['price']}｜申购上限：{s['limit']}"
                if s['pe']:
                    detail += f"｜{s['pe']}"
                lines.append(detail)

        # 可转债
        cb_bonds = []
        for item in cb_data:
            if item["date"] == date_str:
                cb_bonds = item["bonds"]
                break

        if cb_bonds:
            lines.append("")
            lines.append("▣ 可转债申购")
            for b in cb_bonds:
                lines.append(f"  ├ {b['name']} ({b['code']})")
                lines.append(
                    f"  └ 📋 转股价：{b['conv_price']}｜信用评级：{b['rating']}｜正股：{b['stock_name']}")

        # 港股IPO
        hk_stocks = []
        for item in hk_data:
            if item["date"] == date_str:
                hk_stocks = item.get("stocks", [])
                break

        if hk_stocks:
            lines.append("")
            lines.append("▣ 🇭🇰港股上市")
            for i, s in enumerate(hk_stocks):
                is_last = (i == len(hk_stocks) - 1)
                prefix = "└" if is_last else "├"
                name_line = f"  ├ {s['name']} ({s['code']})"
                if s.get('sub_status'):
                    name_line += f" {s['sub_status']}"
                lines.append(name_line)
                detail_parts = [f"💰{s['price']}"]
                if s.get('sub_period'):
                    detail_parts.append(f"📅{s['sub_period']}")
                if s.get('sub_ratio'):
                    detail_parts.append(f"🔥{s['sub_ratio']}")
                if s.get('min_qty'):
                    detail_parts.append(f"最少{s['min_qty']}")
                lines.append(f"  {prefix} {'｜'.join(detail_parts)}")

        lines.append("")

    # 提醒
    lines.append("📌 提醒")
    total_ipo = sum(len(item["stocks"]) for item in ipo_data)
    total_cb = sum(len(item["bonds"]) for item in cb_data)
    total_hk = sum(len(item.get("stocks", [])) for item in hk_data)
    if total_ipo + total_cb + total_hk == 0:
        lines.append("• 近期暂无打新标的")
    else:
        if total_ipo > 0:
            lines.append(f"• 共{total_ipo}只A股新股申购")
        if total_cb > 0:
            lines.append(f"• 共{total_cb}只可转债申购")
        if total_hk > 0:
            lines.append(f"• 共{total_hk}只港股IPO")

    lines.append("数据来源：东方财富 / 巨潮资讯 / 老虎证券")

    return "\n".join(lines)


def main():
    """主函数: 获取数据 → 格式化 → 推送"""
    print(f"[IPO] 开始获取打新数据 - {datetime.now()}")

    # 获取A股IPO + 可转债 + 港股IPO
    ipo_data = get_a_share_ipo(days=3)
    cb_data = get_convertible_bonds(days=3)
    hk_data = get_hk_ipo(days=7)

    print(f"[IPO] A股新股: {sum(len(i['stocks']) for i in ipo_data)}只")
    print(f"[CB] 可转债: {sum(len(i['bonds']) for i in cb_data)}只")
    print(f"[HK] 港股IPO: {sum(len(i.get('stocks', [])) for i in hk_data)}只")

    # 格式化输出
    body = format_output(ipo_data, cb_data, hk_data)
    print(f"\n--- 推送内容 ---\n{body}\n--- END ---")

    # 推送到Bark
    result = push_ipo(body)
    return result


if __name__ == "__main__":
    main()
