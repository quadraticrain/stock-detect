"""Command-line interface for stock-detect."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from rich.console import Console
from rich.table import Table

from stock_detect.analyzer import SignalAnalyzer
from stock_detect.env import bootstrap
from stock_detect.market_data import top_performers
from stock_detect.reddit_fetcher import RedditFetcher
from stock_detect.twitter_fetcher import TwitterFetcher


console = Console()


def _print_evaluation(label: str, evaluation: dict | None) -> None:
    if not evaluation:
        return
    console.print(f"\n[bold]{label}[/bold]")
    table = Table(show_header=True)
    table.add_column("Window")
    table.add_column("Signals")
    table.add_column("Accuracy")
    table.add_column("Avg Return %")
    for window, stats in evaluation.get("windows", {}).items():
        acc = stats.get("accuracy")
        ret = stats.get("avg_return_pct")
        table.add_row(
            window,
            str(stats.get("count", 0)),
            f"{acc * 100:.1f}%" if acc is not None else "n/a",
            f"{ret:.2f}" if ret is not None else "n/a",
        )
    console.print(table)


def _parse_date(value: str) -> datetime:
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"Invalid date: {value}. Use YYYY-MM-DD.")


def _parse_accounts(value: str) -> list[str]:
    return [a.strip().lstrip("@") for a in value.split(",") if a.strip()]


def _source_label(source: str) -> str:
    return {"x": "X/Twitter", "wsb": "WSB", "both": "X + WSB"}.get(source, source)


def cmd_scan(args: argparse.Namespace) -> int:
    analyzer = SignalAnalyzer(
        subreddit=args.subreddit,
        x_accounts=_parse_accounts(args.accounts),
    )

    posts = None
    if args.file:
        console.print(f"[cyan]Loading posts from {args.file}...[/cyan]")
        if args.source == "wsb":
            from stock_detect.analyzer import reddit_to_social

            posts = [reddit_to_social(p) for p in RedditFetcher.from_json_file(args.file)]
        else:
            posts = TwitterFetcher.from_json_file(args.file)
    elif args.source == "x":
        accounts = ", ".join(f"@{a}" for a in analyzer.x_accounts)
        console.print(f"[cyan]Fetching X timelines: {accounts}[/cyan]")
    elif args.source == "wsb":
        console.print(f"[cyan]Fetching up to {args.limit} posts from r/{args.subreddit}...[/cyan]")
    else:
        console.print(
            f"[cyan]Fetching X + WSB (limit {args.limit}, X: {', '.join(analyzer.x_accounts)})...[/cyan]"
        )

    report = analyzer.analyze(
        source=args.source,
        limit=args.limit,
        sort=args.sort,
        use_proximity=args.proximity,
        evaluate=not args.no_eval,
        lookback_days=args.lookback,
        posts=posts,
        after=args.after,
        before=args.before,
        all_cashtags=not args.sp500_only,
        sp500_only=args.sp500_only,
    )

    console.print(
        f"\nSource: {_source_label(report.source)} | "
        f"Posts: {report.fetched_posts} | "
        f"Actionable: {report.actionable_posts} | "
        f"Signals: {len(report.signals)} | "
        f"Consensus events: {len(report.daily_consensus)}"
    )
    if report.accounts_scanned:
        console.print(f"X accounts: {', '.join('@' + a for a in report.accounts_scanned)}")

    if report.ticker_summaries:
        title = f"Top Tickers ({_source_label(report.source)} Signals)"
        table = Table(title=title, show_header=True)
        table.add_column("Ticker")
        table.add_column("Posts")
        table.add_column("Buy")
        table.add_column("X")
        table.add_column("WSB")
        table.add_column("Authors")
        table.add_column("Consensus")
        for row in report.ticker_summaries[: args.top]:
            table.add_row(
                row.ticker,
                str(row.mention_posts),
                str(row.buy_posts),
                str(row.x_mentions),
                str(row.wsb_mentions),
                row.top_authors[:28],
                row.latest_signal,
            )
        console.print(table)

    _print_evaluation("Buy Signal Performance (baseline)", report.evaluation)
    _print_evaluation("Buy Signal Performance (MA30 filter)", report.evaluation_ma30)
    _print_evaluation("Buy Signal Performance (MA90 filter)", report.evaluation_ma90)

    if args.json:
        payload = {
            "source": report.source,
            "fetched_posts": report.fetched_posts,
            "actionable_posts": report.actionable_posts,
            "accounts": report.accounts_scanned,
            "fetch_stats": report.fetch_stats.to_dict() if report.fetch_stats else None,
            "fetch_window": report.fetch_window.to_dict() if report.fetch_window else None,
            "top_tickers": [
                {
                    "ticker": t.ticker,
                    "mentions": t.mention_posts,
                    "buy": t.buy_posts,
                    "x": t.x_mentions,
                    "wsb": t.wsb_mentions,
                    "authors": t.top_authors,
                    "consensus": t.latest_signal,
                }
                for t in report.ticker_summaries[: args.top]
            ],
            "evaluation": report.evaluation,
            "evaluation_ma30": report.evaluation_ma30,
            "evaluation_ma90": report.evaluation_ma90,
        }
        print(json.dumps(payload, indent=2, default=str))

    recommended = {t.ticker for t in report.ticker_summaries if t.buy_posts > 0}
    if recommended and args.detection and args.sp500_only:
        stats = analyzer.detection_rate(recommended)
        console.print("\n[bold]Top Performer Detection (S&P 500, paper §4.2)[/bold]")
        console.print(
            f"Detected {stats['detected_top']}/{stats['top_performers']} top performers "
            f"({stats['detection_rate'] * 100:.1f}%) among {stats['recommended_unique']} recommended tickers."
        )
        if stats["detected_tickers"]:
            console.print(f"Hits: {', '.join(stats['detected_tickers'][:20])}")

    return 0


def cmd_top(args: argparse.Namespace) -> int:
    console.print("[cyan]Computing S&P 500 top performers...[/cyan]")
    df = top_performers()
    top = df[df["top_performer"]].head(args.limit)
    table = Table(title="Top 15% S&P 500 Performers", show_header=True)
    table.add_column("Ticker")
    table.add_column("Total Growth %")
    table.add_column("Median 3M %")
    for _, row in top.iterrows():
        table.add_row(
            row["ticker"],
            f"{row['total_growth_pct']:.1f}",
            f"{row['median_3m_pct']:.2f}",
        )
    console.print(table)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Social investment signal detector — X/Twitter-first, with optional WSB. "
            "Signal extraction follows Buz & de Melo (2023); X accounts like @aleabitoreddit "
            "are the primary alpha source per the author's view."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Scan X/Twitter (default) or WSB for buy/sell signals")
    scan.add_argument(
        "--source",
        choices=["x", "wsb", "both"],
        default="x",
        help="Signal source: X/Twitter (default), WSB, or both",
    )
    scan.add_argument(
        "--accounts",
        default="aleabitoreddit",
        help="Comma-separated X accounts (default: aleabitoreddit)",
    )
    scan.add_argument("--limit", type=int, default=4000, help="Max posts to fetch/analyze")
    scan.add_argument("--sort", choices=["new", "hot", "top"], default="new", help="WSB sort order")
    scan.add_argument("--subreddit", default="wallstreetbets")
    scan.add_argument("--file", help="Load posts from local JSON instead of fetching")
    scan.add_argument("--after", type=_parse_date, help="Only posts after YYYY-MM-DD")
    scan.add_argument("--before", type=_parse_date, help="Only posts before YYYY-MM-DD")
    scan.add_argument("--proximity", action="store_true", help="Proximity-based buy keyword detection")
    scan.add_argument("--sp500-only", action="store_true", help="Restrict to S&P 500 tickers only")
    scan.add_argument("--no-eval", action="store_true", help="Skip Yahoo Finance backtest")
    scan.add_argument("--lookback", type=int, default=120, help="Days for performance evaluation")
    scan.add_argument("--top", type=int, default=25, help="Rows to display")
    scan.add_argument("--detection", action="store_true", help="S&P 500 top-performer detection stats")
    scan.add_argument("--json", action="store_true", help="Print JSON summary")
    scan.set_defaults(func=cmd_scan)

    top = sub.add_parser("top", help="List current S&P 500 top performers")
    top.add_argument("--limit", type=int, default=30)
    top.set_defaults(func=cmd_top)

    return parser


def main(argv: list[str] | None = None) -> int:
    bootstrap()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        return 130
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
