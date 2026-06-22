"""Report JSON payloads for stock-detect analysis (no static site generation)."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from stock_detect.analyzer import AnalysisReport
from stock_detect.scan_marker import MARKER_NO_NEW


def report_to_dict(report: AnalysisReport, *, accounts: list[str]) -> dict:
    now = datetime.now(timezone.utc)
    source = report.source
    account_slug = "_".join(a.lower() for a in accounts) or "unknown"
    run_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}_{source}_{account_slug}"

    payload = {
        "id": run_id,
        "generated_at": now.isoformat(),
        "source": source,
        "accounts": accounts,
        "fetched_posts": report.fetched_posts,
        "actionable_posts": report.actionable_posts,
        "signal_count": len(report.signals),
        "consensus_count": len(report.daily_consensus),
        "top_tickers": [
            {
                "ticker": t.ticker,
                "mentions": t.mention_posts,
                "buy": t.buy_posts,
                "sell": t.sell_posts,
                "hold": t.hold_posts,
                "x": t.x_mentions,
                "wsb": t.wsb_mentions,
                "authors": t.top_authors,
                "consensus": t.latest_signal,
                "score": t.total_score,
            }
            for t in report.ticker_summaries[:50]
        ],
        "buy_consensus": [
            {"date": d.isoformat(), "ticker": t}
            for d, t in report.buy_consensus_signals[:100]
        ],
    }
    if report.fetch_window is not None:
        payload.update(report.fetch_window.to_dict())
    if report.fetch_stats is not None:
        payload.update(report.fetch_stats.to_dict())

    github_run_id = os.environ.get("GITHUB_RUN_ID", "").strip()
    github_repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if github_run_id and github_repo:
        payload["ci_run_url"] = f"https://github.com/{github_repo}/actions/runs/{github_run_id}"

    api_new = payload.get("api_posts_new")
    if api_new is not None:
        payload["data_unchanged"] = api_new == 0
    elif payload.get("ci_scan_marker"):
        payload["data_unchanged"] = payload["ci_scan_marker"] == MARKER_NO_NEW

    return payload


def run_entry(data: dict) -> dict:
    run_id = data["id"]
    api_new = data.get("api_posts_new")
    entry = {
        "id": run_id,
        "generated_at": data["generated_at"],
        "source": data["source"],
        "accounts": data["accounts"],
        "fetched_posts": data["fetched_posts"],
        "signal_count": data["signal_count"],
        "consensus_count": data["consensus_count"],
    }
    if api_new is not None:
        entry["api_posts_new"] = api_new
        entry["data_unchanged"] = api_new == 0
    if data.get("pages_fetched") is not None:
        entry["pages_fetched"] = data["pages_fetched"]
    if data.get("cache_posts") is not None:
        entry["cache_posts"] = data["cache_posts"]
    if data.get("ci_run_url"):
        entry["ci_run_url"] = data["ci_run_url"]
    if data.get("ci_scan_marker"):
        entry["ci_scan_marker"] = data["ci_scan_marker"]
    if data.get("ci_scan_at"):
        entry["ci_scan_at"] = data["ci_scan_at"]
    return entry
