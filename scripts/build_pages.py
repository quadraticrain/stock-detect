#!/usr/bin/env python3
"""Run scan and write static site for GitHub Pages."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_detect.analyzer import SignalAnalyzer  # noqa: E402
from stock_detect.report import write_site  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build GitHub Pages report")
    parser.add_argument("--output", default="site", help="Output directory")
    parser.add_argument("--merge-from", help="Existing gh-pages dir to preserve history")
    parser.add_argument("--source", choices=["x", "wsb", "both"], default="x")
    parser.add_argument("--accounts", default="aleabitoreddit")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--no-eval", action="store_true")
    args = parser.parse_args()

    accounts = [a.strip().lstrip("@") for a in args.accounts.split(",") if a.strip()]
    analyzer = SignalAnalyzer(x_accounts=accounts)
    report = analyzer.analyze(
        source=args.source,
        limit=args.limit,
        evaluate=not args.no_eval,
    )
    out = write_site(
        args.output,
        report,
        accounts=accounts,
        merge_from=args.merge_from,
    )
    print(f"Wrote {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
