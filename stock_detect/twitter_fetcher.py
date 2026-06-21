"""Fetch public X/Twitter timelines via the syndication embed (no API key)."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterator

import requests

from stock_detect.config import DEFAULT_X_ACCOUNTS, USER_AGENT
from stock_detect.models import SocialPost

_SYNDICATION = "https://syndication.twitter.com/srv/timeline-profile/screen-name/{screen_name}"
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)


class TwitterFetcher:
    def __init__(self, user_agent: str = USER_AGENT):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def fetch_accounts(
        self,
        accounts: list[str] | None = None,
        *,
        limit_per_account: int | None = None,
        after: datetime | None = None,
        before: datetime | None = None,
    ) -> list[SocialPost]:
        accounts = accounts or DEFAULT_X_ACCOUNTS
        posts: list[SocialPost] = []
        for account in accounts:
            account = account.lstrip("@").lower()
            batch = self.fetch_user(account)
            if after is not None:
                batch = [p for p in batch if p.created >= after]
            if before is not None:
                batch = [p for p in batch if p.created <= before]
            if limit_per_account is not None:
                batch = batch[:limit_per_account]
            posts.extend(batch)
            time.sleep(0.4)
        posts.sort(key=lambda p: p.created, reverse=True)
        return posts

    def fetch_user(self, screen_name: str) -> list[SocialPost]:
        url = _SYNDICATION.format(screen_name=screen_name.lstrip("@"))
        resp = self.session.get(url, timeout=45)
        resp.raise_for_status()
        match = _NEXT_DATA.search(resp.text)
        if not match:
            raise RuntimeError(f"No timeline data returned for @{screen_name}")

        payload = json.loads(match.group(1))
        entries = payload.get("props", {}).get("pageProps", {}).get("timeline", {}).get("entries", [])
        posts: list[SocialPost] = []
        for entry in entries:
            if entry.get("type") != "tweet":
                continue
            tweet = entry.get("content", {}).get("tweet")
            if not tweet:
                continue
            posts.append(_tweet_to_post(tweet, screen_name))
        return posts

    @classmethod
    def from_json_file(cls, path: str | Path) -> list[SocialPost]:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else raw.get("data", raw.get("posts", []))
        posts: list[SocialPost] = []
        for item in items:
            text = item.get("text") or item.get("full_text") or ""
            created_raw = item.get("created") or item.get("created_at")
            if isinstance(created_raw, str) and " +" in created_raw:
                created = parsedate_to_datetime(created_raw)
            elif isinstance(created_raw, (int, float)):
                created = datetime.fromtimestamp(created_raw, tz=timezone.utc)
            else:
                created = datetime.now(timezone.utc)
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            author = item.get("author") or item.get("screen_name") or "unknown"
            posts.append(
                SocialPost(
                    id=str(item.get("id") or item.get("id_str") or ""),
                    text=text,
                    author=author.lstrip("@"),
                    source="x",
                    created=created,
                    score=int(item.get("score") or item.get("favorite_count") or 0),
                    url=item.get("url") or item.get("permalink") or "",
                    tickers=_symbols_from_item(item),
                )
            )
        return posts

    def iter_posts(self, **kwargs) -> Iterator[SocialPost]:
        yield from self.fetch_accounts(**kwargs)


def _tweet_to_post(tweet: dict, screen_name: str) -> SocialPost:
    created = parsedate_to_datetime(tweet["created_at"])
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    text = tweet.get("full_text") or ""
    tweet_id = str(tweet.get("id_str") or "")
    permalink = tweet.get("permalink") or f"/{screen_name}/status/{tweet_id}"
    if not permalink.startswith("http"):
        permalink = f"https://x.com{permalink}"
    return SocialPost(
        id=tweet_id,
        text=text,
        author=screen_name,
        source="x",
        created=created,
        score=int(tweet.get("favorite_count") or 0),
        url=permalink,
        tickers=_symbols_from_tweet(tweet),
    )


def _symbols_from_tweet(tweet: dict) -> list[str]:
    symbols = []
    for sym in tweet.get("entities", {}).get("symbols", []):
        text = sym.get("text", "").upper()
        if text:
            symbols.append(text)
    if symbols:
        return sorted(set(symbols))
    return sorted(set(re.findall(r"\$([A-Z]{1,5})\b", tweet.get("full_text", "").upper())))


def _symbols_from_item(item: dict) -> list[str]:
    if item.get("tickers"):
        return [t.upper() for t in item["tickers"]]
    entities = item.get("entities", {})
    symbols = [s.get("text", "").upper() for s in entities.get("symbols", []) if s.get("text")]
    if symbols:
        return sorted(set(symbols))
    text = item.get("text") or item.get("full_text") or ""
    return sorted(set(re.findall(r"\$([A-Z]{1,5})\b", text.upper())))
