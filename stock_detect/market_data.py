"""Fetch S&P 500 tickers and price history via Yahoo Finance."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import lru_cache

from io import StringIO

import pandas as pd
import requests
import yfinance as yf

from stock_detect.config import EVAL_WINDOWS, MA_WINDOWS, USER_AGENT


@lru_cache(maxsize=1)
def fetch_sp500_tickers() -> set[str]:
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(3):
        try:
            html = requests.get(url, headers=headers, timeout=30).text
            tables = pd.read_html(StringIO(html))
            tickers = tables[0]["Symbol"].astype(str).str.replace(".", "-", regex=False).tolist()
            return set(tickers)
        except Exception:
            if attempt == 2:
                break
    return _fallback_sp500_tickers()


def _fallback_sp500_tickers() -> set[str]:
    """Common S&P 500 tickers used when Wikipedia is unavailable."""
    return {
        "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "GOOG", "META", "BRK-B", "UNH", "JNJ",
        "XOM", "JPM", "V", "PG", "MA", "HD", "CVX", "MRK", "ABBV", "PEP", "KO", "COST",
        "AVGO", "WMT", "MCD", "CSCO", "TMO", "ACN", "ABT", "DHR", "LIN", "NEE", "ADBE",
        "CRM", "NKE", "TXN", "PM", "AMD", "ORCL", "INTC", "QCOM", "IBM", "GE", "CAT",
        "GS", "MS", "BAC", "WFC", "C", "BLK", "SCHW", "AXP", "SPGI", "MMC", "CB",
        "TSLA", "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS", "MU", "LRCX", "AMAT", "KLAC",
        "SNPS", "CDNS", "ADI", "MRVL", "ON", "NXPI", "MSCI", "DE", "RTX", "LMT", "BA",
    }


def fetch_price_history(
    ticker: str,
    start: date,
    end: date | None = None,
) -> pd.DataFrame:
    end = end or date.today()
    try:
        data = yf.download(
            ticker,
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            progress=False,
            auto_adjust=True,
        )
    except Exception:
        return pd.DataFrame()
    if data is None or data.empty:
        return pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    if "Close" not in data.columns:
        return pd.DataFrame()
    data = data.dropna(subset=["Close"])
    if data.empty:
        return pd.DataFrame()
    data.index = pd.to_datetime(data.index).tz_localize(None)
    return data


def add_moving_averages(prices: pd.DataFrame) -> pd.DataFrame:
    out = prices.copy()
    close = out["Close"]
    for window in MA_WINDOWS:
        out[f"MA{window}"] = close.rolling(window=window, min_periods=window).mean()
    return out


def price_change_after_signal(
    prices: pd.DataFrame,
    signal_date: date,
    days: int,
) -> float | None:
    if prices.empty:
        return None
    idx = pd.Timestamp(signal_date)
    future = idx + pd.Timedelta(days=days)
    available = prices.index
    if idx not in available:
        later = available[available >= idx]
        if later.empty:
            return None
        idx = later[0]
    future_dates = available[available >= future]
    if future_dates.empty:
        return None
    start_price = float(prices.loc[idx, "Close"])
    end_price = float(prices.loc[future_dates[0], "Close"])
    if start_price == 0:
        return None
    return (end_price - start_price) / start_price * 100


def is_below_ma(prices: pd.DataFrame, signal_date: date, window: int) -> bool | None:
    col = f"MA{window}"
    if col not in prices.columns:
        return None
    idx = pd.Timestamp(signal_date)
    if idx not in prices.index:
        later = prices.index[prices.index >= idx]
        if later.empty:
            return None
        idx = later[0]
    close = float(prices.loc[idx, "Close"])
    ma = prices.loc[idx, col]
    if pd.isna(ma):
        return None
    return close < float(ma)


def evaluate_buy_signals(
    signals: list[tuple[date, str]],
    *,
    ma_filter: int | None = None,
) -> dict:
    """Evaluate accuracy and average return for buy signals."""
    if not signals:
        return {"count": 0, "windows": {}}

    by_ticker: dict[str, list[date]] = {}
    for sig_date, ticker in signals:
        by_ticker.setdefault(ticker, []).append(sig_date)

    min_date = min(d for d, _ in signals) - timedelta(days=max(MA_WINDOWS) + 5)
    max_date = date.today()

    results: dict[str, dict] = {}
    for label, days in EVAL_WINDOWS.items():
        returns: list[float] = []
        wins = 0
        total = 0
        for ticker, dates in by_ticker.items():
            try:
                prices = add_moving_averages(fetch_price_history(ticker, min_date, max_date))
            except Exception:
                continue
            if prices.empty or "Close" not in prices.columns:
                continue
            for sig_date in dates:
                if ma_filter is not None:
                    below = is_below_ma(prices, sig_date, ma_filter)
                    if below is not True:
                        continue
                change = price_change_after_signal(prices, sig_date, days)
                if change is None:
                    continue
                total += 1
                returns.append(change)
                if change > 0:
                    wins += 1
        results[label] = {
            "count": total,
            "accuracy": wins / total if total else None,
            "avg_return_pct": sum(returns) / len(returns) if returns else None,
        }

    return {
        "count": sum(r["count"] for r in results.values()) // max(len(EVAL_WINDOWS), 1),
        "windows": results,
        "ma_filter": ma_filter,
    }


def top_performers(
    tickers: set[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    percentile: float = 0.15,
) -> pd.DataFrame:
    """Identify top-performing S&P 500 stocks (paper section 4.2)."""
    tickers = tickers or fetch_sp500_tickers()
    start = start or date.today() - timedelta(days=365 * 4)
    end = end or date.today()

    rows = []
    for ticker in sorted(tickers):
        try:
            prices = fetch_price_history(ticker, start, end)
        except Exception:
            continue
        if len(prices) < 90:
            continue
        close = prices["Close"]
        total_growth = float(close.iloc[-1] / close.iloc[0])
        three_month = close.pct_change(periods=63).dropna()
        median_3m = float(three_month.median() * 100) if not three_month.empty else 0.0
        rows.append(
            {
                "ticker": ticker,
                "total_growth_pct": (total_growth - 1) * 100,
                "median_3m_pct": median_3m,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    growth_cutoff = df["total_growth_pct"].quantile(1 - percentile)
    median_cutoff = df["median_3m_pct"].quantile(1 - percentile)
    df["top_growth"] = df["total_growth_pct"] >= growth_cutoff
    df["top_median_3m"] = df["median_3m_pct"] >= median_cutoff
    df["top_performer"] = df["top_growth"] | df["top_median_3m"]
    return df.sort_values("total_growth_pct", ascending=False)
