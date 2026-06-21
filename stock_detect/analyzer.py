"""High-level analysis pipeline combining Reddit data and market evaluation."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from stock_detect.market_data import (
    evaluate_buy_signals,
    fetch_sp500_tickers,
    top_performers,
)
from stock_detect.reddit_fetcher import RedditFetcher, RedditPost
from stock_detect.signal_extractor import (
    DailyConsensus,
    PostSignal,
    aggregate_daily_consensus,
    extract_post_signals,
)


@dataclass
class TickerSummary:
    ticker: str
    mention_posts: int = 0
    buy_posts: int = 0
    sell_posts: int = 0
    hold_posts: int = 0
    total_score: int = 0
    latest_signal: str = "neutral"
    consensus_days: int = 0


@dataclass
class AnalysisReport:
    fetched_posts: int
    actionable_posts: int
    signals: list[PostSignal] = field(default_factory=list)
    daily_consensus: list[DailyConsensus] = field(default_factory=list)
    ticker_summaries: list[TickerSummary] = field(default_factory=list)
    buy_consensus_signals: list[tuple[date, str]] = field(default_factory=list)
    evaluation: dict | None = None
    evaluation_ma30: dict | None = None
    evaluation_ma90: dict | None = None
    top_performer_detection: dict | None = None


class WSBAnalyzer:
    def __init__(self, subreddit: str = "wallstreetbets"):
        self.fetcher = RedditFetcher(subreddit=subreddit)
        self.tickers = fetch_sp500_tickers()

    def analyze(
        self,
        *,
        limit: int = 500,
        sort: str = "new",
        use_proximity: bool = False,
        evaluate: bool = True,
        lookback_days: int = 120,
        posts: list | None = None,
        after: datetime | None = None,
        before: datetime | None = None,
    ) -> AnalysisReport:
        if posts is None:
            posts = self.fetcher.fetch_posts(
                sort=sort, limit=limit, after=after, before=before
            )
        else:
            limit = len(posts)
        signals: list[PostSignal] = []
        actionable = 0

        for post in posts:
            post_signals = extract_post_signals(
                post.title,
                post.body,
                post.flair,
                post.created,
                post.score,
                self.tickers,
                use_proximity=use_proximity,
            )
            if post_signals:
                actionable += 1
                signals.extend(post_signals)

        daily = aggregate_daily_consensus(signals)
        summaries = self._summarize_tickers(signals, daily)

        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        buy_consensus = [
            (c.date, c.ticker)
            for c in daily
            if c.signal == "buy" and datetime.combine(c.date, datetime.min.time(), tzinfo=timezone.utc) >= cutoff
        ]

        report = AnalysisReport(
            fetched_posts=len(posts),
            actionable_posts=actionable,
            signals=signals,
            daily_consensus=daily,
            ticker_summaries=summaries,
            buy_consensus_signals=buy_consensus,
        )

        if evaluate and buy_consensus:
            report.evaluation = evaluate_buy_signals(buy_consensus)
            report.evaluation_ma30 = evaluate_buy_signals(buy_consensus, ma_filter=30)
            report.evaluation_ma90 = evaluate_buy_signals(buy_consensus, ma_filter=90)

        return report

    def detection_rate(self, recommended_tickers: set[str], years: int = 4) -> dict:
        end = date.today()
        start = end - timedelta(days=365 * years)
        performers = top_performers(self.tickers, start, end)
        top = set(performers.loc[performers["top_performer"], "ticker"].tolist())
        detected = recommended_tickers & top
        return {
            "top_performers": len(top),
            "recommended_unique": len(recommended_tickers),
            "detected_top": len(detected),
            "detection_rate": len(detected) / len(top) if top else 0.0,
            "detected_tickers": sorted(detected),
            "missed_top_sample": sorted(top - detected)[:15],
        }

    def _summarize_tickers(
        self,
        signals: list[PostSignal],
        daily: list[DailyConsensus],
    ) -> list[TickerSummary]:
        by_ticker: dict[str, TickerSummary] = {}
        for sig in signals:
            if sig.ticker not in by_ticker:
                by_ticker[sig.ticker] = TickerSummary(ticker=sig.ticker)
            summary = by_ticker[sig.ticker]
            summary.mention_posts += 1
            summary.total_score += sig.score
            if sig.recommendation == "buy":
                summary.buy_posts += 1
            elif sig.recommendation == "sell":
                summary.sell_posts += 1
            elif sig.recommendation == "hold":
                summary.hold_posts += 1

        latest_consensus: dict[str, str] = {}
        consensus_days: Counter[str] = Counter()
        for day in daily:
            if day.signal != "neutral":
                latest_consensus[day.ticker] = day.signal
                consensus_days[day.ticker] += 1

        for ticker, summary in by_ticker.items():
            summary.latest_signal = latest_consensus.get(ticker, "neutral")
            summary.consensus_days = consensus_days.get(ticker, 0)

        return sorted(
            by_ticker.values(),
            key=lambda x: (x.buy_posts, x.mention_posts, x.total_score),
            reverse=True,
        )
