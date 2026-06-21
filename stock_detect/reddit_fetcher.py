"""Fetch posts from r/wallstreetbets via archive APIs (Arctic Shift / PullPush)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import requests

from stock_detect.config import USER_AGENT


@dataclass
class RedditPost:
    id: str
    title: str
    body: str
    flair: str | None
    created: datetime
    score: int
    num_comments: int
    permalink: str


class RedditFetcher:
    ARCTIC_SHIFT = "https://arctic-shift.photon-reddit.com/api/posts/search"
    PULLPUSH = "https://api.pullpush.io/reddit/search/submission/"

    def __init__(self, subreddit: str = "wallstreetbets", user_agent: str = USER_AGENT):
        self.subreddit = subreddit
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def fetch_posts(
        self,
        *,
        sort: str = "new",
        limit: int = 100,
        time_filter: str = "week",
        after: datetime | None = None,
        before: datetime | None = None,
    ) -> list[RedditPost]:
        posts = self._fetch_arctic_shift(
            limit=limit, sort=sort, after=after, before=before
        )
        if len(posts) < limit:
            posts.extend(
                self._fetch_pullpush(
                    limit=limit - len(posts),
                    sort=sort,
                    after=after,
                    before=before,
                )
            )
        return posts[:limit]

    @classmethod
    def from_json_file(cls, path: str | Path) -> list[RedditPost]:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else raw.get("data", raw.get("posts", []))
        return [_post_from_dict(item) for item in items]

    def _fetch_arctic_shift(
        self,
        *,
        limit: int,
        sort: str,
        after: datetime | None = None,
        before: datetime | None = None,
    ) -> list[RedditPost]:
        posts: list[RedditPost] = []
        before_ts: int | None = int(before.timestamp()) if before else None
        order = "desc" if sort in {"new", "hot"} else "asc"

        while len(posts) < limit:
            batch = min(100, limit - len(posts))
            params: dict = {
                "subreddit": self.subreddit,
                "limit": batch,
                "sort": order,
            }
            if after is not None:
                params["after"] = int(after.timestamp())
            if before_ts is not None:
                params["before"] = before_ts

            resp = self.session.get(self.ARCTIC_SHIFT, params=params, timeout=45)
            resp.raise_for_status()
            payload = resp.json()
            data = payload.get("data", [])
            if not data:
                break

            for item in data:
                posts.append(_post_from_dict(item))

            before_ts = min(int(item.get("created_utc", 0)) for item in data)
            if len(data) < batch:
                break
            time.sleep(0.3)

        return posts

    def _fetch_pullpush(
        self,
        *,
        limit: int,
        sort: str,
        after: datetime | None = None,
        before: datetime | None = None,
    ) -> list[RedditPost]:
        posts: list[RedditPost] = []
        before_ts: int | None = int(before.timestamp()) if before else None

        while len(posts) < limit:
            batch = min(100, limit - len(posts))
            params: dict = {
                "subreddit": self.subreddit,
                "size": batch,
                "sort": "desc" if sort in {"new", "hot"} else "asc",
                "sort_type": "created_utc",
            }
            if after is not None:
                params["after"] = int(after.timestamp())
            if before_ts is not None:
                params["before"] = before_ts

            resp = self.session.get(self.PULLPUSH, params=params, timeout=45)
            resp.raise_for_status()
            data = resp.json().get("data", [])
            if not data:
                break

            for item in data:
                posts.append(_post_from_dict(item))

            before_ts = min(int(item.get("created_utc", 0)) for item in data)
            if len(data) < batch:
                break
            time.sleep(0.3)

        return posts

    def iter_posts(self, **kwargs) -> Iterator[RedditPost]:
        yield from self.fetch_posts(**kwargs)


def _post_from_dict(data: dict) -> RedditPost:
    created = datetime.fromtimestamp(int(data.get("created_utc", 0)), tz=timezone.utc)
    permalink = data.get("permalink") or data.get("full_link") or ""
    if permalink and not permalink.startswith("http"):
        permalink = f"https://www.reddit.com{permalink}"
    return RedditPost(
        id=data.get("id", ""),
        title=data.get("title", ""),
        body=data.get("selftext", "") or "",
        flair=data.get("link_flair_text"),
        created=created,
        score=int(data.get("score", 0)),
        num_comments=int(data.get("num_comments", 0)),
        permalink=permalink,
    )
