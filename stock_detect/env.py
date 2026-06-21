"""Load local environment variables from .env when present."""

from __future__ import annotations

from pathlib import Path


def load_env() -> None:
    root = Path(__file__).resolve().parents[1]
    env_path = root / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(env_path, override=True)


def bootstrap() -> None:
    """Load env and sync MySQL schema when MYSQL_PASSWORD is configured."""
    load_env()
    from stock_detect.tweet_cache import init_mysql_cache

    init_mysql_cache()
