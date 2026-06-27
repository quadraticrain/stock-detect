"""Detect tickers first mentioned by an X author within a recent window."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests

from stock_detect.config import BARK_PUSH_URL, NEW_TICKER_LOOKBACK_HOURS
from stock_detect.models import SocialPost, sort_posts_chronological
from stock_detect.post_tickers import resolve_post_tickers
from stock_detect.tweet_cache import TweetCache


@dataclass(frozen=True)
class NewTickerHit:
    author: str
    ticker: str
    post_id: str
    post_url: str
    created_at: datetime


def prior_tickers_by_author(posts: list[SocialPost]) -> dict[str, set[str]]:
    """Aggregate resolved tickers per author from historical posts."""
    out: dict[str, set[str]] = {}
    for post in posts:
        author = post.author.lower()
        tickers = resolve_post_tickers(post)
        if not tickers:
            continue
        out.setdefault(author, set()).update(tickers)
    return out


def detect_new_ticker_hits(
    recent_posts: list[SocialPost],
    historical_posts: list[SocialPost],
) -> list[NewTickerHit]:
    """Return tickers appearing in recent posts but never before for that author."""
    prior = prior_tickers_by_author(historical_posts)
    hits: list[NewTickerHit] = []
    seen: set[tuple[str, str]] = set()

    for post in sort_posts_chronological(recent_posts):
        author = post.author.lower()
        known = prior.setdefault(author, set())
        for ticker in resolve_post_tickers(post):
            key = (author, ticker)
            if ticker in known or key in seen:
                continue
            seen.add(key)
            known.add(ticker)
            hits.append(
                NewTickerHit(
                    author=author,
                    ticker=ticker,
                    post_id=post.id,
                    post_url=post.url,
                    created_at=post.created,
                )
            )
    return hits


def load_new_ticker_hits(
    cache: TweetCache,
    accounts: list[str],
    *,
    lookback_hours: int = NEW_TICKER_LOOKBACK_HOURS,
    now: datetime | None = None,
) -> list[NewTickerHit]:
    """Batch-load recent/historical posts and detect first-time ticker mentions."""
    if not accounts:
        return []
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=lookback_hours)
    historical = cache.list_posts_for_accounts(accounts, created_before=cutoff)
    recent = cache.list_posts_for_accounts(accounts, created_after=cutoff)
    return detect_new_ticker_hits(recent, historical)


def format_bark_title(hit: NewTickerHit) -> str:
    return f"@{hit.author} 新提到 ${hit.ticker}"


def format_bark_body(hit: NewTickerHit) -> str:
    created = hit.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"博主 @{hit.author} 近 24 小时首次提到 ${hit.ticker}",
        f"发帖时间: {created}",
    ]
    if hit.post_url:
        lines.append(f"链接: {hit.post_url}")
    return "\n".join(lines)


def push_bark_alert(
    hit: NewTickerHit,
    *,
    bark_url: str = BARK_PUSH_URL,
    dry_run: bool = False,
    timeout_sec: float = 10.0,
) -> bool:
    """Send one Bark notification for a new ticker hit."""
    payload = {
        "title": format_bark_title(hit),
        "body": format_bark_body(hit),
        "group": "stock-detect",
    }
    if dry_run:
        return True
    resp = requests.post(bark_url, json=payload, timeout=timeout_sec)
    resp.raise_for_status()
    return True


def push_bark_alerts(
    hits: list[NewTickerHit],
    *,
    bark_url: str = BARK_PUSH_URL,
    dry_run: bool = False,
) -> int:
    """Push Bark alerts for all hits. Returns count of successful pushes."""
    sent = 0
    for hit in hits:
        push_bark_alert(hit, bark_url=bark_url, dry_run=dry_run)
        sent += 1
    return sent
