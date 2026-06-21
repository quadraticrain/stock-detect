"""X (Twitter) API v2 client with OAuth 2.0 Bearer or OAuth 1.0a user context."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import requests

from stock_detect.config import REQUEST_DELAY_SEC, USER_AGENT
from stock_detect.fetch_window import FetchStats, FetchWindow
from stock_detect.models import SocialPost

_API_BASE = "https://api.twitter.com/2"
_TWEET_FIELDS = "created_at,public_metrics,entities,note_tweet,referenced_tweets"
_USER_FIELDS = "username"


@dataclass
class XApiCredentials:
    """Credentials loaded from environment (never commit real values)."""

    bearer_token: str | None = None
    api_key: str | None = None
    api_secret: str | None = None
    access_token: str | None = None
    access_token_secret: str | None = None

    @classmethod
    def from_env(cls) -> XApiCredentials:
        return cls(
            bearer_token=_env("X_BEARER_TOKEN", "X_API_BEARER_TOKEN"),
            api_key=_env("X_API_KEY", "X_CONSUMER_KEY"),
            api_secret=_env("X_API_SECRET", "X_CONSUMER_SECRET"),
            access_token=_env("X_ACCESS_TOKEN"),
            access_token_secret=_env("X_ACCESS_TOKEN_SECRET"),
        )

    def is_configured(self) -> bool:
        if self.bearer_token:
            return True
        return all(
            [
                self.api_key,
                self.api_secret,
                self.access_token,
                self.access_token_secret,
            ]
        )

    def auth_mode(self) -> str | None:
        if self.bearer_token:
            return "oauth2_bearer"
        if self.is_configured():
            return "oauth1_user"
        return None


def _env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


class XApiClient:
    """Paginated user timeline via official X API v2."""

    def __init__(
        self,
        credentials: XApiCredentials | None = None,
        *,
        user_agent: str = USER_AGENT,
    ):
        self.credentials = credentials or XApiCredentials.from_env()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def is_configured(self) -> bool:
        return self.credentials.is_configured()

    def fetch_user_timeline(
        self,
        screen_name: str,
        *,
        window: FetchWindow,
        max_pages: int,
        max_posts: int,
        stats: FetchStats,
    ) -> list[SocialPost]:
        user_id = self._resolve_user_id(screen_name, stats)
        if not user_id:
            return []

        posts: list[SocialPost] = []
        pagination_token: str | None = None
        screen_name = screen_name.lstrip("@").lower()

        for _ in range(max_pages):
            if len(posts) >= max_posts:
                break

            params: dict = {
                "max_results": max(5, min(100, max_posts - len(posts))),
                "start_time": _iso(window.after),
                "end_time": _iso(window.before),
                "tweet.fields": _TWEET_FIELDS,
                "expansions": "author_id",
                "user.fields": _USER_FIELDS,
            }
            if pagination_token:
                params["pagination_token"] = pagination_token

            try:
                resp = self.session.get(
                    f"{_API_BASE}/users/{user_id}/tweets",
                    params=params,
                    headers=self._auth_headers(),
                    auth=self._oauth1_auth(),
                    timeout=45,
                )
                if resp.status_code != 200:
                    stats.pages_skipped += 1
                    break
                payload = resp.json()
            except (requests.RequestException, ValueError, KeyError):
                stats.pages_skipped += 1
                break

            stats.pages_fetched += 1
            page_posts = self._parse_timeline(payload, screen_name)
            known = {post.id for post in posts}
            for post in page_posts:
                if post.id not in known:
                    posts.append(post)
                    known.add(post.id)

            pagination_token = payload.get("meta", {}).get("next_token")
            if not pagination_token or not page_posts:
                break
            time.sleep(REQUEST_DELAY_SEC)

        return posts[:max_posts]

    def _resolve_user_id(self, screen_name: str, stats: FetchStats) -> str | None:
        username = screen_name.lstrip("@")
        try:
            resp = self.session.get(
                f"{_API_BASE}/users/by/username/{username}",
                params={"user.fields": "id,username"},
                headers=self._auth_headers(),
                auth=self._oauth1_auth(),
                timeout=30,
            )
            if resp.status_code != 200:
                stats.pages_skipped += 1
                return None
            return str(resp.json().get("data", {}).get("id") or "")
        except (requests.RequestException, ValueError, KeyError):
            stats.pages_skipped += 1
            return None

    def _auth_headers(self) -> dict[str, str]:
        if self.credentials.bearer_token:
            return {"Authorization": f"Bearer {self.credentials.bearer_token}"}
        return {}

    def _oauth1_auth(self):
        if self.credentials.bearer_token:
            return None
        if not self.credentials.is_configured():
            return None
        from requests_oauthlib import OAuth1

        return OAuth1(
            self.credentials.api_key,
            client_secret=self.credentials.api_secret,
            resource_owner_key=self.credentials.access_token,
            resource_owner_secret=self.credentials.access_token_secret,
        )

    @staticmethod
    def _parse_timeline(payload: dict, screen_name: str) -> list[SocialPost]:
        tweets = payload.get("data") or []
        posts: list[SocialPost] = []
        for tweet in tweets:
            post = _tweet_v2_to_post(tweet, screen_name)
            if post is not None:
                posts.append(post)
        return posts


def _iso(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tweet_v2_to_post(tweet: dict, screen_name: str) -> SocialPost | None:
    tweet_id = str(tweet.get("id") or "")
    if not tweet_id:
        return None

    text = tweet.get("text") or ""
    note = tweet.get("note_tweet", {})
    if note.get("text"):
        text = note["text"]

    created_raw = tweet.get("created_at")
    if not created_raw:
        return None
    created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)

    metrics = tweet.get("public_metrics") or {}
    entities = tweet.get("entities") or {}
    symbols = [c.get("tag", "").upper() for c in entities.get("cashtags", []) if c.get("tag")]
    if not symbols:
        symbols = sorted(set(re.findall(r"\$([A-Z]{1,5})\b", text.upper())))

    return SocialPost(
        id=tweet_id,
        text=text,
        author=screen_name,
        source="x",
        created=created,
        score=int(metrics.get("like_count") or 0),
        url=f"https://x.com/{screen_name}/status/{tweet_id}",
        tickers=sorted(set(symbols)),
    )
