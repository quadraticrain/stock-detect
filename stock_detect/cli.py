"""Command-line interface for stock-detect."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from rich.console import Console
from rich.table import Table

from stock_detect.analyzer import WSBAnalyzer
from stock_detect.market_data import top_performers
from stock_detect.reddit_fetcher import RedditFetcher


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


def cmd_scan(args: argparse.Namespace) -> int:
    analyzer = WSBAnalyzer(subreddit=args.subreddit)
    posts = None
    if args.file:
        console.print(f"[cyan]Loading posts from {args.file}...[/cyan]")
        posts = RedditFetcher.from_json_file(args.file)
    else:
        console.print(f"[cyan]Fetching up to {args.limit} posts from r/{args.subreddit}...[/cyan]")
    report = analyzer.analyze(
        limit=args.limit,
        sort=args.sort,
        use_proximity=args.proximity,
        evaluate=not args.no_eval,
        lookback_days=args.lookback,
        posts=posts,
        after=args.after,
        before=args.before,
    )

    console.print(
        f"\nPosts fetched: {report.fetched_posts} | "
        f"Actionable: {report.actionable_posts} | "
        f"Signals: {len(report.signals)} | "
        f"Daily consensus events: {len(report.daily_consensus)}"
    )

    if report.ticker_summaries:
        table = Table(title="Top Mentioned S&P 500 Tickers (WSB Signals)", show_header=True)
        table.add_column("Ticker")
        table.add_column("Posts")
        table.add_column("Buy")
        table.add_column("Sell")
        table.add_column("Hold")
        table.add_column("Consensus")
        for row in report.ticker_summaries[: args.top]:
            table.add_row(
                row.ticker,
                str(row.mention_posts),
                str(row.buy_posts),
                str(row.sell_posts),
                str(row.hold_posts),
                row.latest_signal,
            )
        console.print(table)

    _print_evaluation("Buy Signal Performance (baseline)", report.evaluation)
    _print_evaluation("Buy Signal Performance (MA30 filter)", report.evaluation_ma30)
    _print_evaluation("Buy Signal Performance (MA90 filter)", report.evaluation_ma90)

    if args.json:
        payload = {
            "fetched_posts": report.fetched_posts,
            "actionable_posts": report.actionable_posts,
            "top_tickers": [
                {
                    "ticker": t.ticker,
                    "mentions": t.mention_posts,
                    "buy": t.buy_posts,
                    "sell": t.sell_posts,
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
    if recommended and args.detection:
        stats = analyzer.detection_rate(recommended)
        console.print("\n[bold]Top Performer Detection (paper §4.2)[/bold]")
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
            "WSB investment signal detector — implements methodology from "
            "'Democratization of Retail Trading' (Buz & de Melo, 2023)."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Fetch WSB posts and extract buy/sell signals")
    scan.add_argument("--limit", type=int, default=300, help="Number of posts to fetch")
    scan.add_argument("--sort", choices=["new", "hot", "top"], default="new")
    scan.add_argument("--subreddit", default="wallstreetbets")
    scan.add_argument("--file", help="Load posts from a local JSON file instead of fetching")
    scan.add_argument("--after", type=_parse_date, help="Only posts after YYYY-MM-DD")
    scan.add_argument("--before", type=_parse_date, help="Only posts before YYYY-MM-DD")
    scan.add_argument("--proximity", action="store_true", help="Use proximity-based buy detection")
    scan.add_argument("--no-eval", action="store_true", help="Skip Yahoo Finance backtest")
    scan.add_argument("--lookback", type=int, default=120, help="Days for performance evaluation")
    scan.add_argument("--top", type=int, default=20, help="Rows to display")
    scan.add_argument("--detection", action="store_true", help="Show top-performer detection stats")
    scan.add_argument("--json", action="store_true", help="Print JSON summary")
    scan.set_defaults(func=cmd_scan)

    top = sub.add_parser("top", help="List current S&P 500 top performers")
    top.add_argument("--limit", type=int, default=30)
    top.set_defaults(func=cmd_top)

    return parser


def main(argv: list[str] | None = None) -> int:
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
