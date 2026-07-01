"""Resolve tickers from X API entities (stored JSON) and cashtags in text."""

from __future__ import annotations

import json
import re

from stock_detect.models import SocialPost

_CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})\b")


def tickers_from_text(text: str) -> list[str]:
    return sorted(set(_CASHTAG_RE.findall(text.upper())))


def resolve_post_tickers(post: SocialPost) -> list[str]:
    """Merge DB tickers (X API entities at ingest) with $cashtags in text."""
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in post.tickers or []:
        ticker = str(raw).upper().strip()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        ordered.append(ticker)
    if post.source in {"x", "xueqiu"}:
        for ticker in tickers_from_text(post.text):
            if ticker not in seen:
                seen.add(ticker)
                ordered.append(ticker)
    return ordered


def merge_ticker_lists(existing: list[str] | None, new: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in (existing or []) + (new or []):
        ticker = str(raw).upper().strip()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        out.append(ticker)
    return out


def tickers_json(tickers: list[str]) -> str:
    return json.dumps(tickers, ensure_ascii=False)
