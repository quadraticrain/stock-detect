"""CI scan markers persisted to MySQL for downstream services."""

from __future__ import annotations

import re
from datetime import datetime

MARKER_NO_NEW = "###NO_NEW###"
MARKER_NEW_PREFIX = "***NEW:"
MARKER_NEW_SUFFIX = "***"
CI_MARKER_POST_PREFIX = "###CI_SCAN_"


def ci_marker_for(api_posts_new: int) -> str:
    if api_posts_new <= 0:
        return MARKER_NO_NEW
    return f"{MARKER_NEW_PREFIX}{api_posts_new}{MARKER_NEW_SUFFIX}"


def ci_marker_post_id(account: str) -> str:
    return f"{CI_MARKER_POST_PREFIX}{account.lstrip('@').lower()}###"


def ci_marker_text(
    marker: str,
    *,
    window_days: int | None,
    run_id: str | None,
    scanned_at: datetime,
) -> str:
    parts = [marker]
    if window_days is not None:
        parts.append(f"window_days={window_days}")
    if run_id:
        parts.append(f"run_id={run_id}")
    parts.append(f"scanned_at={scanned_at.isoformat()}")
    return " ".join(parts)


def parse_ci_marker(marker: str | None) -> int | None:
    """Return api_posts_new parsed from marker, or 0 for NO_NEW, or None if unknown."""
    if not marker:
        return None
    if marker == MARKER_NO_NEW:
        return 0
    match = re.fullmatch(r"\*\*\*NEW:(\d+)\*\*\*", marker)
    if match:
        return int(match.group(1))
    return None


def is_no_new_marker(marker: str | None) -> bool:
    return marker == MARKER_NO_NEW
