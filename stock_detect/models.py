"""Shared data models for social post sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class SocialPost:
    id: str
    text: str
    author: str
    source: str  # x | wsb
    created: datetime
    score: int
    url: str
    tickers: list[str] = field(default_factory=list)
    meta: str = ""


def sort_posts_chronological(posts: list[SocialPost]) -> list[SocialPost]:
    """Oldest first by created_at, then snowflake post_id (smaller = older)."""

    def _key(post: SocialPost) -> tuple[datetime, int]:
        created = post.created
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        else:
            created = created.astimezone(timezone.utc)
        try:
            post_id = int(post.id)
        except (TypeError, ValueError):
            post_id = 0
        return created, post_id

    return sorted(posts, key=_key)
