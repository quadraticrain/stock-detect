"""Per-phase fetch caps so extended windows do not exhaust API budget before guest depth."""

from __future__ import annotations

from dataclasses import dataclass

from stock_detect.config import (
    EXTENDED_MAX_FETCH_PAGES,
    EXTENDED_MAX_FETCH_POSTS,
    FULL_FETCH_MAX_PAGES,
    INCREMENTAL_MAX_PAGES,
    X_API_MAX_DAYS,
)


@dataclass(frozen=True)
class FetchBudget:
    api_posts: int
    api_pages: int
    guest_posts: int
    guest_pages: int
    guest_passes: int = 1


def extended_fetch_budget(
    window_days: int,
    max_posts: int,
    max_pages: int,
) -> FetchBudget:
    """Split caps: guest gets independent budget for pre-API history on long lookbacks."""
    posts = min(max(max_posts, 1), EXTENDED_MAX_FETCH_POSTS)
    pages = min(max(max_pages, 1), EXTENDED_MAX_FETCH_PAGES)

    if window_days <= X_API_MAX_DAYS:
        return FetchBudget(
            api_posts=posts,
            api_pages=pages,
            guest_posts=0,
            guest_pages=0,
            guest_passes=0,
        )

    extra_days = window_days - X_API_MAX_DAYS
    guest_pages = min(
        EXTENDED_MAX_FETCH_PAGES,
        max(pages, pages + extra_days * 3),
    )
    guest_posts = min(
        EXTENDED_MAX_FETCH_POSTS,
        max(posts, posts + extra_days * 80),
    )
    api_pages = min(pages, FULL_FETCH_MAX_PAGES)
    api_posts = min(posts, max(4000, posts // 2))
    guest_passes = max(2, min(6, extra_days // 25 + 2))
    return FetchBudget(
        api_posts=api_posts,
        api_pages=api_pages,
        guest_posts=guest_posts,
        guest_pages=guest_pages,
        guest_passes=guest_passes,
    )


def incremental_api_pages(budget: FetchBudget) -> int:
    return min(INCREMENTAL_MAX_PAGES, budget.api_pages)
