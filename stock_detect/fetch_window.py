"""Fixed lookback window and fetch statistics for paginated sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from stock_detect.config import FETCH_WINDOW_DAYS


@dataclass
class FetchStats:
    pages_fetched: int = 0
    pages_skipped: int = 0
    posts_raw: int = 0
    posts_fetched: int = 0
    streams_used: list[str] = field(default_factory=list)
    streams_unavailable: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "pages_fetched": self.pages_fetched,
            "pages_skipped": self.pages_skipped,
            "posts_raw": self.posts_raw,
            "posts_fetched": self.posts_fetched,
            "streams_used": self.streams_used,
            "streams_unavailable": self.streams_unavailable,
        }


@dataclass
class FetchWindow:
    after: datetime
    before: datetime
    window_days: int = FETCH_WINDOW_DAYS

    def contains(self, moment: datetime) -> bool:
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return self.after <= moment <= self.before

    def to_dict(self) -> dict:
        return {
            "window_days": self.window_days,
            "window_start": self.after.isoformat(),
            "window_end": self.before.isoformat(),
        }


def default_fetch_window(
    *,
    window_days: int = FETCH_WINDOW_DAYS,
    before: datetime | None = None,
) -> FetchWindow:
    end = before or datetime.now(timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start = end - timedelta(days=window_days)
    return FetchWindow(after=start, before=end, window_days=window_days)


def filter_to_window(items: list, window: FetchWindow, *, created_at) -> list:
    return [item for item in items if window.contains(created_at(item))]
