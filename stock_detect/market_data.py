"""S&P 500 ticker list for optional --sp500-only filtering."""

from __future__ import annotations

from functools import lru_cache
from io import StringIO

import pandas as pd
import requests

from stock_detect.config import USER_AGENT


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
