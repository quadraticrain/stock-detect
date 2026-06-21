"""Generate static HTML reports and manifest for GitHub Pages."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from stock_detect.analyzer import AnalysisReport

MAX_RUNS = 60
_STATIC = Path(__file__).resolve().parent / "static"


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
    return payload


def run_entry(data: dict) -> dict:
    run_id = data["id"]
    return {
        "id": run_id,
        "generated_at": data["generated_at"],
        "source": data["source"],
        "accounts": data["accounts"],
        "html": f"reports/{run_id}.html",
        "json": f"reports/{run_id}.json",
        "fetched_posts": data["fetched_posts"],
        "signal_count": data["signal_count"],
        "consensus_count": data["consensus_count"],
    }


def load_manifest(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"runs": [], "latest": None}


def save_manifest(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def merge_manifest(manifest: dict, entry: dict) -> dict:
    runs = [r for r in manifest.get("runs", []) if r["id"] != entry["id"]]
    runs.insert(0, entry)
    runs.sort(key=lambda r: r["generated_at"], reverse=True)
    runs = runs[:MAX_RUNS]
    return {"runs": runs, "latest": runs[0]["id"] if runs else None}


def refresh_site(output_dir: str | Path, merge_from: str | Path) -> Path:
    """Republish existing gh-pages content with updated assets/nav (no new scan)."""
    out = Path(output_dir)
    src = Path(merge_from)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(src, out)

    manifest_path = out / "manifest.json"
    if not manifest_path.exists() and (out / "report.json").exists():
        legacy = json.loads((out / "report.json").read_text(encoding="utf-8"))
        if "id" not in legacy:
            legacy["id"] = "legacy_" + legacy.get("generated_at", "unknown").replace(":", "").replace("+00:00", "Z")[:15]
        entry = run_entry(legacy)
        run_id = legacy["id"]
        reports_dir = out / "reports"
        reports_dir.mkdir(exist_ok=True)
        shutil.copy2(out / "report.json", reports_dir / f"{run_id}.json")
        (reports_dir / f"{run_id}.html").write_text(_report_html(run_id, f"{run_id}.json"), encoding="utf-8")
        save_manifest(manifest_path, {"runs": [entry], "latest": run_id})

    assets_dir = out / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    _write_assets(assets_dir)
    (out / "index.html").write_text(_index_html(), encoding="utf-8")
    manifest = load_manifest(manifest_path)
    latest = manifest.get("latest")
    if latest:
        redirect = f"""<!DOCTYPE html>
<html lang="zh-CN"><head>
  <meta charset="utf-8"/>
  <meta http-equiv="refresh" content="0; url=reports/{latest}.html"/>
  <script>location.replace('reports/{latest}.html');</script>
  <title>Redirecting…</title>
</head><body><p><a href="reports/{latest}.html">Latest report</a></p></body></html>"""
        (out / "latest.html").write_text(redirect, encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return out


def write_site(
    output_dir: str | Path,
    report: AnalysisReport,
    *,
    accounts: list[str],
    merge_from: str | Path | None = None,
) -> Path:
    out = Path(output_dir)
    reports_dir = out / "reports"
    assets_dir = out / "assets"
    reports_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    if merge_from:
        src = Path(merge_from)
        if src.exists():
            old_manifest = src / "manifest.json"
            if old_manifest.exists():
                shutil.copy2(old_manifest, out / "manifest.json")
            old_reports = src / "reports"
            if old_reports.is_dir():
                for f in old_reports.iterdir():
                    if f.is_file():
                        shutil.copy2(f, reports_dir / f.name)

    _write_assets(assets_dir)

    data = report_to_dict(report, accounts=accounts)
    entry = run_entry(data)
    run_id = data["id"]

    (reports_dir / f"{run_id}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    (reports_dir / f"{run_id}.html").write_text(_report_html(run_id, f"{run_id}.json"), encoding="utf-8")

    manifest = merge_manifest(load_manifest(out / "manifest.json"), entry)
    save_manifest(out / "manifest.json", manifest)

    (out / "index.html").write_text(_index_html(), encoding="utf-8")
    latest = manifest.get("latest")
    if latest:
        redirect = f"""<!DOCTYPE html>
<html lang="zh-CN"><head>
  <meta charset="utf-8"/>
  <meta http-equiv="refresh" content="0; url=reports/{latest}.html"/>
  <script>location.replace('reports/{latest}.html');</script>
  <title>Redirecting…</title>
</head><body><p><a href="reports/{latest}.html">Latest report</a></p></body></html>"""
        (out / "latest.html").write_text(redirect, encoding="utf-8")

    (out / "report.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return out


def _write_assets(assets_dir: Path) -> None:
    shutil.copy2(_STATIC / "style.css", assets_dir / "style.css")
    shutil.copy2(_STATIC / "app.js", assets_dir / "app.js")


def _report_html(run_id: str, json_name: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Stock Detect — {run_id}</title>
  <link rel="stylesheet" href="../assets/style.css"/>
</head>
<body>
  <div id="navbar"></div>
  <div class="wrap">
    <div id="content"><p class="sub">Loading report…</p></div>
    <p class="footer">
      Research only, not investment advice.
      <a href="https://github.com/quadraticrain/stock-detect">Source</a>
    </p>
  </div>
  <script>
    window.STOCK_DETECT = {{
      mode: "report",
      runId: {json.dumps(run_id)},
      dataUrl: {json.dumps(json_name)},
      manifestUrl: "../manifest.json",
      homeUrl: "../index.html"
    }};
  </script>
  <script src="../assets/app.js"></script>
</body>
</html>
"""


def _index_html() -> str:
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Stock Detect — Reports</title>
  <link rel="stylesheet" href="assets/style.css"/>
</head>
<body>
  <div id="navbar"></div>
  <div class="wrap">
    <h1>Stock Detect</h1>
    <p class="sub">X/Twitter-first investment signals · CI report archive</p>
    <div id="content"><p class="sub">Loading…</p></div>
    <p class="footer">
      Research only, not investment advice.
      <a href="https://github.com/quadraticrain/stock-detect">Source</a>
    </p>
  </div>
  <script>
    window.STOCK_DETECT = {
      mode: "index",
      manifestUrl: "manifest.json",
      homeUrl: "index.html"
    };
  </script>
  <script src="assets/app.js"></script>
</body>
</html>
"""
