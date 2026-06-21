"""High-level analysis pipeline for X/Twitter and WSB signals."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from stock_detect.config import DEFAULT_X_ACCOUNTS, MAX_FETCH_POSTS
from stock_detect.fetch_window import FetchStats, FetchWindow, default_fetch_window
from stock_detect.market_data import (
    evaluate_buy_signals,
    fetch_sp500_tickers,
    top_performers,
)
from stock_detect.models import SocialPost
from stock_detect.reddit_fetcher import RedditFetcher, RedditPost
from stock_detect.signal_extractor import (
    DailyConsensus,
    PostSignal,
    aggregate_daily_consensus,
    extract_post_signals,
    extract_social_post_signals,
)
from stock_detect.twitter_fetcher import TwitterFetcher


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
    x_mentions: int = 0
    wsb_mentions: int = 0
    top_authors: str = ""


@dataclass
class AnalysisReport:
    source: str
    fetched_posts: int
    actionable_posts: int
    signals: list[PostSignal] = field(default_factory=list)
    daily_consensus: list[DailyConsensus] = field(default_factory=list)
    ticker_summaries: list[TickerSummary] = field(default_factory=list)
    buy_consensus_signals: list[tuple[date, str]] = field(default_factory=list)
    evaluation: dict | None = None
    evaluation_ma30: dict | None = None
    evaluation_ma90: dict | None = None
    accounts_scanned: list[str] = field(default_factory=list)
    fetch_window: FetchWindow | None = None
    fetch_stats: FetchStats | None = None


def reddit_to_social(post: RedditPost) -> SocialPost:
    text = post.title
    if post.body:
        text = f"{post.title}\n{post.body}" if post.title else post.body
    return SocialPost(
        id=post.id,
        text=text,
        author="wallstreetbets",
        source="wsb",
        created=post.created,
        score=post.score,
        url=post.permalink,
        meta=post.flair or "",
    )


class SignalAnalyzer:
    def __init__(
        self,
        *,
        subreddit: str = "wallstreetbets",
        x_accounts: list[str] | None = None,
    ):
        self.reddit = RedditFetcher(subreddit=subreddit)
        self.twitter = TwitterFetcher()
        self.x_accounts = x_accounts or DEFAULT_X_ACCOUNTS
        self.sp500 = fetch_sp500_tickers()

    def analyze(
        self,
        *,
        source: str = "x",
        limit: int = 500,
        sort: str = "new",
        use_proximity: bool = False,
        evaluate: bool = True,
        lookback_days: int = 120,
        posts: list[SocialPost] | None = None,
        after: datetime | None = None,
        before: datetime | None = None,
        all_cashtags: bool = True,
        sp500_only: bool = False,
    ) -> AnalysisReport:
        fetch_window = default_fetch_window(before=before)
        if after is not None:
            fetch_window = FetchWindow(
                after=after if after.tzinfo else after.replace(tzinfo=timezone.utc),
                before=fetch_window.before,
                window_days=fetch_window.window_days,
            )

        fetch_stats: FetchStats | None = None
        if posts is None:
            posts, fetch_stats = self._fetch(
                source,
                limit=limit,
                sort=sort,
                window=fetch_window,
            )
        else:
            posts = [
                p
                for p in posts
                if fetch_window.contains(p.created)
            ]
            limit = len(posts)

        valid = self.sp500 if sp500_only else None
        use_all = all_cashtags and not sp500_only

        signals: list[PostSignal] = []
        actionable = 0
        accounts = sorted({p.author for p in posts if p.source == "x"})

        for post in posts:
            if post.source == "wsb":
                post_signals = extract_post_signals(
                    post.text,
                    post.created,
                    post.score,
                    valid or self.sp500,
                    source="wsb",
                    author=post.author,
                    flair=post.meta or None,
                    all_cashtags=False,
                    use_proximity=use_proximity,
                )
            else:
                post_signals = extract_social_post_signals(
                    post,
                    valid,
                    all_cashtags=use_all,
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
            if c.signal == "buy"
            and datetime.combine(c.date, datetime.min.time(), tzinfo=timezone.utc) >= cutoff
        ]

        report = AnalysisReport(
            source=source,
            fetched_posts=len(posts),
            actionable_posts=actionable,
            signals=signals,
            daily_consensus=daily,
            ticker_summaries=summaries,
            buy_consensus_signals=buy_consensus,
            accounts_scanned=accounts,
            fetch_window=fetch_window,
            fetch_stats=fetch_stats,
        )

        if evaluate and buy_consensus:
            report.evaluation = evaluate_buy_signals(buy_consensus)
            report.evaluation_ma30 = evaluate_buy_signals(buy_consensus, ma_filter=30)
            report.evaluation_ma90 = evaluate_buy_signals(buy_consensus, ma_filter=90)

        return report

    def _fetch(
        self,
        source: str,
        *,
        limit: int,
        sort: str,
        window: FetchWindow,
    ) -> tuple[list[SocialPost], FetchStats]:
        max_posts = min(limit or MAX_FETCH_POSTS, MAX_FETCH_POSTS)
        stats = FetchStats()

        if source == "x":
            posts = self.twitter.fetch_accounts(
                self.x_accounts,
                window=window,
                max_posts=max_posts,
            )
            stats = self.twitter.last_stats
            return posts[:max_posts], stats

        if source == "wsb":
            posts = self.reddit.fetch_posts(sort=sort, limit=max_posts)
            stats = self.reddit.last_stats
            return [reddit_to_social(p) for p in posts][:max_posts], stats

        if source == "both":
            x_cap = max_posts // 2
            wsb_cap = max_posts - x_cap
            x_posts = self.twitter.fetch_accounts(
                self.x_accounts,
                window=window,
                max_posts=x_cap,
            )
            wsb_posts = [
                reddit_to_social(p)
                for p in self.reddit.fetch_posts(sort=sort, limit=wsb_cap)
            ]
            stats = FetchStats(
                pages_fetched=self.twitter.last_stats.pages_fetched + self.reddit.last_stats.pages_fetched,
                pages_skipped=self.twitter.last_stats.pages_skipped + self.reddit.last_stats.pages_skipped,
                posts_fetched=len(x_posts) + len(wsb_posts),
            )
            merged = x_posts + wsb_posts
            merged.sort(key=lambda p: p.created, reverse=True)
            return merged[:max_posts], stats

        raise ValueError(f"Unknown source: {source}")

    def detection_rate(self, recommended_tickers: set[str], years: int = 4) -> dict:
        end = date.today()
        start = end - timedelta(days=365 * years)
        performers = top_performers(self.sp500, start, end)
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
        authors: dict[str, set[str]] = {}

        for sig in signals:
            if sig.ticker not in by_ticker:
                by_ticker[sig.ticker] = TickerSummary(ticker=sig.ticker)
                authors[sig.ticker] = set()
            summary = by_ticker[sig.ticker]
            summary.mention_posts += 1
            summary.total_score += sig.score
            authors[sig.ticker].add(sig.author or sig.source)
            if sig.source == "x":
                summary.x_mentions += 1
            else:
                summary.wsb_mentions += 1
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
            summary.top_authors = ", ".join(sorted(authors[ticker])[:3])

        return sorted(
            by_ticker.values(),
            key=lambda x: (x.buy_posts, x.x_mentions, x.mention_posts, x.total_score),
            reverse=True,
        )


# Backward compatibility
WSBAnalyzer = SignalAnalyzer
