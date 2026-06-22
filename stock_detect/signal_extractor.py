"""Extract buy/hold/sell signals from social post text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

from stock_detect.config import (
    AMBIGUOUS_TICKERS,
    BUY_NEGATIONS,
    BUY_WORDS,
    CONSENSUS_THRESHOLD,
    HOLD_NEGATIONS,
    HOLD_WORDS,
    PROACTIVE_FLAIRS,
    PROXIMITY_CHARS,
    REACTIVE_FLAIRS,
    SELL_NEGATIONS,
    SELL_WORDS,
    SINGLE_CHAR_TICKERS,
)
from stock_detect.models import SocialPost
from stock_detect.post_tickers import resolve_post_tickers


@dataclass
class PostSignal:
    ticker: str
    recommendation: str  # buy | hold | sell | neutral
    buy_score: float
    hold_score: float
    sell_score: float
    source: str
    author: str
    title: str
    created: datetime
    score: int
    use_proximity: bool = False


@dataclass
class DailyConsensus:
    date: date
    ticker: str
    buy_posts: int = 0
    sell_posts: int = 0
    hold_posts: int = 0
    signal: str = "neutral"
    sources: str = ""


def _extract_tickers(
    text: str,
    valid_tickers: set[str] | None,
    *,
    all_cashtags: bool = False,
    known_tickers: list[str] | None = None,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    upper = text.upper()

    if known_tickers:
        for ticker in known_tickers:
            counts[ticker.upper()] = counts.get(ticker.upper(), 0) + 1

    if all_cashtags:
        for match in re.finditer(r"\$([A-Z]{1,5})\b", upper):
            ticker = match.group(1)
            if ticker in AMBIGUOUS_TICKERS and f"${ticker}" not in upper:
                continue
            counts[ticker] = counts.get(ticker, 0) + 1
        return counts

    if not valid_tickers:
        return counts

    for match in re.finditer(r"\$([A-Z]{1,5})\b", upper):
        ticker = match.group(1)
        if ticker in valid_tickers:
            counts[ticker] = counts.get(ticker, 0) + 1

    for ticker in valid_tickers:
        if ticker in AMBIGUOUS_TICKERS or ticker in SINGLE_CHAR_TICKERS:
            continue
        pattern = rf"\b{re.escape(ticker)}\b"
        for _ in re.finditer(pattern, upper):
            counts[ticker] = counts.get(ticker, 0) + 1

    return counts


def _word_score(text: str, words: set[str], negations: set[str]) -> float:
    lower = text.lower()
    score = 0.0
    for phrase in negations:
        score -= lower.count(phrase)
    for word in words:
        score += len(re.findall(rf"\b{re.escape(word)}\b", lower))
    return score


def _proximity_score(text: str, ticker: str, words: set[str]) -> float:
    upper = text.upper()
    score = 0.0
    ticker_pattern = rf"\$?{re.escape(ticker.upper())}\b"
    for match in re.finditer(ticker_pattern, upper):
        start = max(0, match.start() - PROXIMITY_CHARS)
        end = min(len(text), match.end() + PROXIMITY_CHARS)
        window = text[start:end].lower()
        for word in words:
            score += len(re.findall(rf"\b{re.escape(word)}\b", window))
    return score


def classify_flair(flair: str | None) -> str:
    if not flair:
        return "unknown"
    normalized = flair.strip().lower()
    if normalized in PROACTIVE_FLAIRS:
        return "proactive"
    if normalized in REACTIVE_FLAIRS:
        return "reactive"
    return "unknown"


def is_actionable_post(source: str, flair: str | None, body: str) -> bool:
    if source == "x":
        return bool(body and body.strip())
    if classify_flair(flair) == "reactive":
        return False
    if classify_flair(flair) == "proactive":
        return True
    return bool(body and body.strip())


def _recommendation(buy: float, hold: float, sell: float) -> tuple[str, float, float, float]:
    if buy <= 0 and hold <= 0 and sell <= 0:
        return "neutral", buy, hold, sell
    scores = {"buy": buy, "hold": hold, "sell": sell}
    best = max(scores, key=scores.get)
    top = scores[best]
    tied = [k for k, v in scores.items() if v == top and v > 0]
    if len(tied) > 1:
        return "neutral", buy, hold, sell
    return best, buy, hold, sell


def extract_post_signals(
    text: str,
    created: datetime,
    score: int,
    valid_tickers: set[str] | None,
    *,
    source: str = "wsb",
    author: str = "",
    flair: str | None = None,
    known_tickers: list[str] | None = None,
    all_cashtags: bool = False,
    use_proximity: bool = False,
) -> list[PostSignal]:
    if not is_actionable_post(source, flair, text):
        return []

    ticker_counts = _extract_tickers(
        text,
        valid_tickers,
        all_cashtags=all_cashtags,
        known_tickers=known_tickers,
    )
    if not ticker_counts:
        return []

    signals: list[PostSignal] = []
    preview = text.replace("\n", " ")[:120]
    for ticker in ticker_counts:
        if use_proximity:
            buy = _proximity_score(text, ticker, BUY_WORDS)
        else:
            buy = _word_score(text, BUY_WORDS, BUY_NEGATIONS)
        hold = _word_score(text, HOLD_WORDS, HOLD_NEGATIONS)
        sell = _word_score(text, SELL_WORDS, SELL_NEGATIONS)

        rec, b, h, s = _recommendation(buy, hold, sell)
        signals.append(
            PostSignal(
                ticker=ticker,
                recommendation=rec,
                buy_score=b,
                hold_score=h,
                sell_score=s,
                source=source,
                author=author,
                title=preview,
                created=created,
                score=score,
                use_proximity=use_proximity,
            )
        )
    return signals


def extract_social_post_signals(
    post: SocialPost,
    valid_tickers: set[str] | None,
    *,
    all_cashtags: bool = False,
    use_proximity: bool = False,
) -> list[PostSignal]:
    return extract_post_signals(
        post.text,
        post.created,
        post.score,
        valid_tickers,
        source=post.source,
        author=post.author,
        known_tickers=resolve_post_tickers(post) if post.source == "x" else None,
        all_cashtags=all_cashtags or post.source == "x",
        use_proximity=use_proximity,
    )


def aggregate_daily_consensus(signals: Iterable[PostSignal]) -> list[DailyConsensus]:
    buckets: dict[tuple[date, str], DailyConsensus] = {}
    for sig in signals:
        if sig.recommendation == "neutral":
            continue
        key = (sig.created.date(), sig.ticker)
        if key not in buckets:
            buckets[key] = DailyConsensus(date=key[0], ticker=key[1])
        bucket = buckets[key]
        if sig.recommendation == "buy":
            bucket.buy_posts += 1
        elif sig.recommendation == "sell":
            bucket.sell_posts += 1
        else:
            bucket.hold_posts += 1
        sources = {s.strip() for s in bucket.sources.split(",") if s.strip()}
        sources.add(sig.source)
        bucket.sources = ",".join(sorted(sources))

    results: list[DailyConsensus] = []
    for bucket in buckets.values():
        if bucket.buy_posts >= bucket.sell_posts * CONSENSUS_THRESHOLD and bucket.buy_posts > 0:
            bucket.signal = "buy"
        elif bucket.sell_posts >= bucket.buy_posts * CONSENSUS_THRESHOLD and bucket.sell_posts > 0:
            bucket.signal = "sell"
        else:
            bucket.signal = "neutral"
        results.append(bucket)
    return sorted(results, key=lambda x: (x.date, x.ticker))
