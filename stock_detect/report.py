"""Generate static HTML report for GitHub Pages."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from stock_detect.analyzer import AnalysisReport


def report_to_dict(report: AnalysisReport, *, accounts: list[str]) -> dict:
    def eval_block(data: dict | None) -> dict | None:
        if not data:
            return None
        windows = {}
        for key, stats in data.get("windows", {}).items():
            windows[key] = {
                "count": stats.get("count", 0),
                "accuracy": stats.get("accuracy"),
                "avg_return_pct": stats.get("avg_return_pct"),
            }
        return {"windows": windows, "ma_filter": data.get("ma_filter")}

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": report.source,
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
        "evaluation": eval_block(report.evaluation),
        "evaluation_ma30": eval_block(report.evaluation_ma30),
        "evaluation_ma90": eval_block(report.evaluation_ma90),
    }


def write_site(output_dir: str | Path, report: AnalysisReport, *, accounts: list[str]) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    data = report_to_dict(report, accounts=accounts)
    (out / "report.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    (out / "index.html").write_text(_html_template(), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return out


_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Stock Detect — X Signal Report</title>
  <style>
    :root {
      --bg: #0d1117; --card: #161b22; --border: #30363d;
      --text: #e6edf3; --muted: #8b949e; --accent: #58a6ff;
      --buy: #3fb950; --sell: #f85149; --hold: #d29922;
    }
    * { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      background: var(--bg); color: var(--text); margin: 0; line-height: 1.5;
    }
    .wrap { max-width: 1100px; margin: 0 auto; padding: 24px 16px 48px; }
    h1 { font-size: 1.5rem; margin: 0 0 8px; }
    .sub { color: var(--muted); font-size: 0.9rem; margin-bottom: 24px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 24px; }
    .stat { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 14px; }
    .stat .label { color: var(--muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: .04em; }
    .stat .value { font-size: 1.4rem; font-weight: 600; margin-top: 4px; }
    section { margin-bottom: 32px; }
    h2 { font-size: 1.1rem; border-bottom: 1px solid var(--border); padding-bottom: 8px; margin-bottom: 12px; }
    table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
    th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); }
    th { color: var(--muted); font-weight: 500; }
    tr:hover td { background: rgba(88,166,255,.06); }
    .tag { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }
    .tag.buy { background: rgba(63,185,80,.15); color: var(--buy); }
    .tag.sell { background: rgba(248,81,73,.15); color: var(--sell); }
    .tag.neutral, .tag.hold { background: rgba(210,153,34,.15); color: var(--hold); }
    .eval-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
    .eval-card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 14px; }
    .eval-card h3 { margin: 0 0 10px; font-size: 0.95rem; }
    .footer { color: var(--muted); font-size: 0.8rem; margin-top: 32px; }
    a { color: var(--accent); }
    .err { color: var(--sell); padding: 16px; background: var(--card); border-radius: 8px; }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Stock Detect</h1>
    <p class="sub">X/Twitter-first investment signals · auto-updated by GitHub Actions</p>
    <div id="content"><p class="sub">Loading report…</p></div>
    <p class="footer">
      Research only, not investment advice.
      <a href="https://github.com/quadraticrain/stock-detect">Source</a>
    </p>
  </div>
  <script>
    function tag(c) {
      const cls = c === 'buy' ? 'buy' : c === 'sell' ? 'sell' : 'neutral';
      return `<span class="tag ${cls}">${c}</span>`;
    }
    function evalTable(block) {
      if (!block || !block.windows) return '<p class="sub">No data</p>';
      let rows = '';
      for (const [w, s] of Object.entries(block.windows)) {
        const acc = s.accuracy != null ? (s.accuracy * 100).toFixed(1) + '%' : 'n/a';
        const ret = s.avg_return_pct != null ? s.avg_return_pct.toFixed(2) + '%' : 'n/a';
        rows += `<tr><td>${w}</td><td>${s.count}</td><td>${acc}</td><td>${ret}</td></tr>`;
      }
      return `<table><thead><tr><th>Window</th><th>Signals</th><th>Accuracy</th><th>Avg Return</th></tr></thead><tbody>${rows}</tbody></table>`;
    }
    fetch('report.json').then(r => {
      if (!r.ok) throw new Error('report.json not found');
      return r.json();
    }).then(d => {
      const accounts = (d.accounts || []).map(a => '@' + a.replace(/^@/, '')).join(', ') || '—';
      const stats = `
        <div class="grid">
          <div class="stat"><div class="label">Generated (UTC)</div><div class="value" style="font-size:.95rem">${new Date(d.generated_at).toLocaleString('en-GB', {timeZone:'UTC'})} UTC</div></div>
          <div class="stat"><div class="label">Source</div><div class="value">${d.source}</div></div>
          <div class="stat"><div class="label">Posts</div><div class="value">${d.fetched_posts}</div></div>
          <div class="stat"><div class="label">Signals</div><div class="value">${d.signal_count}</div></div>
          <div class="stat"><div class="label">Consensus</div><div class="value">${d.consensus_count}</div></div>
        </div>
        <p class="sub">Accounts: ${accounts}</p>`;
      let rows = '';
      for (const t of d.top_tickers || []) {
        rows += `<tr><td><strong>${t.ticker}</strong></td><td>${t.mentions}</td><td>${t.buy}</td><td>${t.x}</td><td>${t.wsb}</td><td>${t.authors || '—'}</td><td>${tag(t.consensus)}</td></tr>`;
      }
      const evals = `
        <div class="eval-grid">
          <div class="eval-card"><h3>Baseline</h3>${evalTable(d.evaluation)}</div>
          <div class="eval-card"><h3>MA30 filter</h3>${evalTable(d.evaluation_ma30)}</div>
          <div class="eval-card"><h3>MA90 filter</h3>${evalTable(d.evaluation_ma90)}</div>
        </div>`;
      document.getElementById('content').innerHTML = stats + `
        <section><h2>Top Tickers</h2>
          <table><thead><tr><th>Ticker</th><th>Posts</th><th>Buy</th><th>X</th><th>WSB</th><th>Authors</th><th>Consensus</th></tr></thead>
          <tbody>${rows || '<tr><td colspan="7">No tickers</td></tr>'}</tbody></table>
        </section>
        <section><h2>Backtest (Yahoo Finance)</h2>${evals}</section>`;
    }).catch(e => {
      document.getElementById('content').innerHTML = `<div class="err">Failed to load report: ${e.message}</div>`;
    });
  </script>
</body>
</html>
"""


def _html_template() -> str:
    return _HTML
