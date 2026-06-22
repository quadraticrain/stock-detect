"""Merge CI scan markers from MySQL fetch_state into report payloads."""

from __future__ import annotations

from datetime import datetime, timezone

from stock_detect.scan_marker import MARKER_NO_NEW, is_no_new_marker, parse_ci_marker
from stock_detect.tweet_cache import FetchState, TweetCache


def merge_ci_scan_metadata(payload: dict, accounts: list[str], cache: TweetCache) -> dict:
    """Attach latest CI scan markers so web/API can detect no-new-data runs."""
    if not cache.available:
        return payload

    markers: dict[str, dict] = {}
    total_new = 0
    saw_marker = False
    all_no_new = True

    for account in accounts:
        state = cache.get_state(account)
        if state is None or not state.last_ci_marker:
            all_no_new = False
            continue
        saw_marker = True
        api_new = state.last_ci_api_posts_new
        if api_new is None:
            api_new = parse_ci_marker(state.last_ci_marker)
        if api_new is None:
            all_no_new = False
        elif api_new > 0:
            all_no_new = False
            total_new += api_new
        markers[account.lstrip("@").lower()] = _state_to_marker_dict(state)

    if not saw_marker:
        return payload

    payload = dict(payload)
    payload["ci_scan_markers"] = markers

    if payload.get("api_posts_new") is None and any(
        m.get("api_posts_new") is not None for m in markers.values()
    ):
        payload["api_posts_new"] = total_new

    if payload.get("data_unchanged") is None:
        payload["data_unchanged"] = all_no_new and all(
            is_no_new_marker(m.get("marker")) for m in markers.values()
        )

    primary = accounts[0].lstrip("@").lower() if accounts else None
    if primary and primary in markers:
        primary_marker = markers[primary]
        payload.setdefault("ci_scan_marker", primary_marker.get("marker"))
        payload.setdefault("ci_scan_at", primary_marker.get("scan_at"))

    return payload


def _state_to_marker_dict(state: FetchState) -> dict:
    scan_at = state.last_ci_scan_at
    if scan_at is not None and scan_at.tzinfo is None:
        scan_at = scan_at.replace(tzinfo=timezone.utc)
    return {
        "marker": state.last_ci_marker,
        "scan_at": scan_at.isoformat() if scan_at else None,
        "api_posts_new": state.last_ci_api_posts_new,
        "window_days": state.last_ci_window_days,
        "run_id": state.last_ci_run_id,
    }
