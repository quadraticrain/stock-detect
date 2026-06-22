"""X (Twitter) API v2 client with OAuth 2.0 Bearer or OAuth 1.0a user context."""

from __future__ import annotations

import base64
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import requests

from stock_detect.config import REQUEST_DELAY_SEC, USER_AGENT, X_API_TIMELINE_EXCLUDES
from stock_detect import config
from stock_detect.fetch_window import FetchStats, FetchWindow
from stock_detect.models import SocialPost

_API_BASE = "https://api.twitter.com/2"
_OAUTH2_TOKEN = "https://api.twitter.com/2/oauth2/token"
_TWEET_FIELDS = "created_at,public_metrics,entities,note_tweet,referenced_tweets"
_USER_FIELDS = "username"
_DEFAULT_SCOPES = "tweet.read users.read offline.access"


@dataclass
class XApiCredentials:
    """Credentials loaded from environment (never commit real values)."""

    bearer_token: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    api_key: str | None = None
    api_secret: str | None = None
    access_token: str | None = None
    access_token_secret: str | None = None

    @classmethod
    def from_env(cls) -> XApiCredentials:
        return cls(
            bearer_token=_env("X_BEARER_TOKEN", "X_API_BEARER_TOKEN") or config.X_BEARER_TOKEN or None,
            client_id=_env("X_CLIENT_ID", "X_API_CLIENT_ID") or config.X_CLIENT_ID or None,
            client_secret=_env("X_CLIENT_SECRET", "X_API_CLIENT_SECRET") or config.X_CLIENT_SECRET or None,
            api_key=_env("X_API_KEY", "X_CONSUMER_KEY") or config.X_API_KEY or None,
            api_secret=_env("X_API_SECRET", "X_CONSUMER_SECRET") or config.X_API_SECRET or None,
            access_token=_env("X_ACCESS_TOKEN") or config.X_ACCESS_TOKEN or None,
            access_token_secret=_env("X_ACCESS_TOKEN_SECRET") or config.X_ACCESS_TOKEN_SECRET or None,
        )

    def is_configured(self) -> bool:
        if self.bearer_token:
            return True
        if self.client_id and self.client_secret:
            return True
        return self.has_oauth1()

    def has_oauth1(self) -> bool:
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
        if self.api_key and self.api_secret and not self.client_id:
            return "oauth2_app_only"
        if self.client_id and self.client_secret:
            return "oauth2_client_credentials"
        if self.has_oauth1():
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
        self._runtime_bearer: str | None = None
        self._runtime_bearer_expires_at: float = 0.0

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
        since_id: str | None = None,
        user_id: str | None = None,
    ) -> list[SocialPost]:
        if not user_id:
            user_id = self.resolve_user_id(screen_name, stats)
        if not user_id:
            return []

        screen_name = screen_name.lstrip("@").lower()
        posts_by_id: dict[str, SocialPost] = {}
        excludes = X_API_TIMELINE_EXCLUDES or (None,)

        for exclude in excludes:
            if len(posts_by_id) >= max_posts:
                break
            remaining = max_posts - len(posts_by_id)
            batch = self._fetch_timeline_pages(
                user_id,
                screen_name,
                window=window,
                max_pages=max_pages,
                max_posts=remaining,
                stats=stats,
                since_id=since_id,
                exclude=exclude,
            )
            for post in batch:
                posts_by_id.setdefault(post.id, post)

        posts = list(posts_by_id.values())
        posts.sort(key=lambda p: p.created, reverse=True)
        return posts[:max_posts]

    def iter_timeline_pages(
        self,
        screen_name: str,
        *,
        window: FetchWindow,
        max_pages: int,
        max_posts: int,
        stats: FetchStats,
        since_id: str | None = None,
        user_id: str | None = None,
        exclude: str | None = None,
        pagination_token: str | None = None,
    ):
        """Yield one API page of posts at a time; carries pagination_token across calls."""
        if not user_id:
            user_id = self.resolve_user_id(screen_name, stats)
        if not user_id:
            return

        screen_name = screen_name.lstrip("@").lower()
        pages = 0
        posts_seen = 0
        token = pagination_token

        while pages < max_pages and posts_seen < max_posts:
            page_posts, token = self._fetch_timeline_page(
                user_id,
                screen_name,
                window=window,
                max_results=min(100, max_posts - posts_seen),
                stats=stats,
                since_id=since_id,
                exclude=exclude,
                pagination_token=token,
            )
            pages += 1
            if not page_posts:
                if not token:
                    break
                time.sleep(REQUEST_DELAY_SEC)
                continue
            posts_seen += len(page_posts)
            yield page_posts
            if not token:
                break
            time.sleep(REQUEST_DELAY_SEC)

    def _fetch_timeline_page(
        self,
        user_id: str,
        screen_name: str,
        *,
        window: FetchWindow,
        max_results: int,
        stats: FetchStats,
        since_id: str | None,
        exclude: str | None,
        pagination_token: str | None,
    ) -> tuple[list[SocialPost], str | None]:
        params: dict = {
            "max_results": max(5, min(100, max_results)),
            "end_time": _iso(window.before),
            "tweet.fields": _TWEET_FIELDS,
            "expansions": "author_id",
            "user.fields": _USER_FIELDS,
        }
        if window.api_start_time:
            params["start_time"] = _iso(window.after)
        if exclude:
            params["exclude"] = exclude
        if since_id:
            params["since_id"] = since_id
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
                return [], None
            payload = resp.json()
        except (requests.RequestException, ValueError, KeyError):
            stats.pages_skipped += 1
            return [], None

        stats.pages_fetched += 1
        page_posts = self._parse_timeline(payload, screen_name)
        next_token = payload.get("meta", {}).get("next_token")
        return page_posts, next_token

    def _fetch_timeline_pages(
        self,
        user_id: str,
        screen_name: str,
        *,
        window: FetchWindow,
        max_pages: int,
        max_posts: int,
        stats: FetchStats,
        since_id: str | None,
        exclude: str | None,
    ) -> list[SocialPost]:
        posts: list[SocialPost] = []
        pagination_token: str | None = None

        for _ in range(max_pages):
            if len(posts) >= max_posts:
                break

            page_posts, pagination_token = self._fetch_timeline_page(
                user_id,
                screen_name,
                window=window,
                max_results=max_posts - len(posts),
                stats=stats,
                since_id=since_id,
                exclude=exclude,
                pagination_token=pagination_token,
            )
            known = {post.id for post in posts}
            for post in page_posts:
                if post.id not in known:
                    posts.append(post)
                    known.add(post.id)

            if not pagination_token or not page_posts:
                break
            time.sleep(REQUEST_DELAY_SEC)

        return posts[:max_posts]

    def resolve_user_id(self, screen_name: str, stats: FetchStats) -> str | None:
        return self._resolve_user_id(screen_name, stats)

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
        bearer = self._resolve_bearer_token()
        if bearer:
            return {"Authorization": f"Bearer {bearer}"}
        return {}

    def _resolve_bearer_token(self) -> str | None:
        if self.credentials.bearer_token:
            return self.credentials.bearer_token
        if self._runtime_bearer and time.time() < self._runtime_bearer_expires_at:
            return self._runtime_bearer
        if self.credentials.api_key and self.credentials.api_secret:
            token, expires_in = self._fetch_legacy_app_token(
                self.credentials.api_key,
                self.credentials.api_secret,
            )
            if token:
                self._runtime_bearer = token
                self._runtime_bearer_expires_at = time.time() + max(60, expires_in - 60)
                return token
        if self.credentials.client_id and self.credentials.client_secret:
            token, expires_in = self._fetch_oauth2_client_token()
            if token:
                self._runtime_bearer = token
                self._runtime_bearer_expires_at = time.time() + max(60, expires_in - 60)
                return token
        return None

    def _fetch_legacy_app_token(self, api_key: str, api_secret: str) -> tuple[str | None, int]:
        basic = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
        try:
            resp = self.session.post(
                "https://api.x.com/oauth2/token",
                headers={
                    "Authorization": f"Basic {basic}",
                    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                },
                data={"grant_type": "client_credentials"},
                timeout=30,
            )
            if resp.status_code != 200:
                return None, 0
            payload = resp.json()
            return payload.get("access_token"), int(payload.get("expires_in") or 7200)
        except (requests.RequestException, ValueError, TypeError):
            return None, 0

    def _fetch_oauth2_client_token(self) -> tuple[str | None, int]:
        client_id = self.credentials.client_id or ""
        client_secret = self.credentials.client_secret or ""
        client_type = _env("X_CLIENT_TYPE") or "third_party_app"
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        try:
            resp = self.session.post(
                _OAUTH2_TOKEN,
                headers={
                    "Authorization": f"Basic {basic}",
                    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                },
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "client_type": client_type,
                    "scope": _DEFAULT_SCOPES,
                },
                timeout=30,
            )
            if resp.status_code != 200:
                return None, 0
            payload = resp.json()
            return payload.get("access_token"), int(payload.get("expires_in") or 7200)
        except (requests.RequestException, ValueError, TypeError):
            return None, 0

    def _oauth1_auth(self):
        if self._resolve_bearer_token():
            return None
        if not self.credentials.has_oauth1():
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
