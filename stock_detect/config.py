"""Constants from 'Democratization of Retail Trading' (Buz & de Melo, 2023)."""

# Proactive flairs — posts intended to provide predictive value
PROACTIVE_FLAIRS = {
    "discussion",
    "yolo",
    "dd",
    "news",
    "options",
    "stocks",
    "technical analysis",
    "fundamentals",
    "chart",
    "technicals",
    "daily discussion",
    "futures",
}

# Reactive flairs — excluded from signal extraction
REACTIVE_FLAIRS = {
    "meme",
    "gain",
    "loss",
    "shitpost",
    "satire",
    "storytime",
    "donation",
    "question",
}

BUY_WORDS = {"buy", "call", "calls", "long", "bullish", "moon", "yolo"}
SELL_WORDS = {"sell", "put", "puts", "short", "bearish", "dump"}
HOLD_WORDS = {"hold", "holding", "diamond", "hands"}

BUY_NEGATIONS = {"not buy", "don't buy", "dont buy", "do not buy", "never buy"}
SELL_NEGATIONS = {"not sell", "don't sell", "dont sell", "do not sell", "never sell"}
HOLD_NEGATIONS = {"not hold", "don't hold", "dont hold", "do not hold"}

# Tickers that are common English words — require $ prefix
AMBIGUOUS_TICKERS = {
    "ALL", "ARE", "CEO", "DD", "DOW", "FAST", "INFO", "IP", "IT",
    "LOW", "MA", "NOW", "PSA", "SEE", "SO", "TECH", "HAS", "KEY",
    "ON", "OR", "OUT", "RUN", "WELL", "YOU", "CAN", "FOR", "GOOD",
}

# Single-character tickers require $ prefix
SINGLE_CHAR_TICKERS = {"F", "T", "C", "X", "V", "Z", "W", "U", "S", "O", "L", "K", "G", "E", "D", "B", "A"}

PROXIMITY_CHARS = 20
CONSENSUS_THRESHOLD = 1.5  # buy count must be 50% higher than sell count

USER_AGENT = "stock-detect/0.2 (research tool; X + WSB signals)"

# Fixed fetch window (paper-style ~63 trading days) and CI-safe caps
FETCH_WINDOW_DAYS = 63
# Official X API user-timeline start_time cannot go further back than this
X_API_MAX_DAYS = 63
MAX_FETCH_PAGES = 40
MAX_FETCH_POSTS = 4000
# Manual / extended runs (e.g. prolific accounts over 180 days)
EXTENDED_MAX_FETCH_PAGES = 300
EXTENDED_MAX_FETCH_POSTS = 25000
# Guest backfill: scale pages per day beyond the X API floor
GUEST_PAGES_PER_EXTRA_DAY = 3
GUEST_POSTS_PER_EXTRA_DAY = 80
REQUEST_DELAY_SEC = 1.5
REDDIT_PAGE_SIZE = 100

# Default X accounts — AI/semi supply-chain analysts (X-first workflow)
DEFAULT_X_ACCOUNTS = [
    "aleabitoreddit",
]

# GitHub Actions scheduled scan + OpenClaw AI analysis (comma-separated author slugs)
CI_SCHEDULED_X_ACCOUNTS = (
    "aleabitoreddit",
    "mingchikuo",
    "justinsuntron",
)
CI_SCHEDULED_X_ACCOUNTS_CSV = ",".join(CI_SCHEDULED_X_ACCOUNTS)
CI_SCHEDULED_XUEQIU_USERS = ("1247347556",)  # 段永平
CI_SCHEDULED_XUEQIU_ACCOUNTS = tuple(f"xueqiu:{user}" for user in CI_SCHEDULED_XUEQIU_USERS)

# Accounts explicitly removed from future monitoring. Keep historical MySQL rows,
# but ignore these accounts in scheduled/manual fetch entrypoints.
DISABLED_X_ACCOUNTS = {
    "elonmusk",
    "justinsuntron",
    "sunyuchentron",
}

# MySQL cache (investment_cache) — password via MYSQL_PASSWORD env / GitHub Secret only
MYSQL_HOST = "rm-wz91qxav0rb3uxf17ro.mysql.cn-shenzhen.rds.aliyuncs.com"
MYSQL_PORT = 3306
MYSQL_DATABASE = "cache_data"
MYSQL_USER = "cache_data_write"
MYSQL_SERVICE = "stock_detect"
MYSQL_TABLE_POSTS = f"{MYSQL_SERVICE}_x_posts"
MYSQL_TABLE_STATE = f"{MYSQL_SERVICE}_x_fetch_state"
# AI analysis output (written by OpenClaw / external scheduler — not by stock-detect scan code)
MYSQL_TABLE_AI_RUNS = f"{MYSQL_SERVICE}_ai_runs"
MYSQL_TABLE_AI_SIGNALS = f"{MYSQL_SERVICE}_ai_signals"
MYSQL_TABLE_AI_CONSENSUS = f"{MYSQL_SERVICE}_ai_consensus"
MYSQL_TABLE_AI_TOP_TICKERS = f"{MYSQL_SERVICE}_ai_top_tickers"

# OpenClaw AI analysis schedule — daily 23:00 Beijing (Asia/Shanghai)
AI_ANALYSIS_TIMEZONE = "Asia/Shanghai"
AI_ANALYSIS_CRON_BEIJING = "0 23 * * *"   # 23:00 every day, use with timezone above
AI_ANALYSIS_CRON_UTC = "0 15 * * *"       # equivalent when scheduler runs in UTC

# New-ticker Bark alerts (run after daily AI incremental analysis)
BARK_PUSH_URL = "https://api.day.app/CXFgAnMVdZXTPvsKRgWKFo"
NEW_TICKER_LOOKBACK_HOURS = 24


def active_scheduled_x_accounts() -> tuple[str, ...]:
    """CI scheduled accounts minus explicitly disabled slugs."""
    return tuple(a for a in CI_SCHEDULED_X_ACCOUNTS if a not in DISABLED_X_ACCOUNTS)


def active_scheduled_social_accounts() -> tuple[str, ...]:
    return active_scheduled_x_accounts() + CI_SCHEDULED_XUEQIU_ACCOUNTS

# X API timeline: exclude retweets only (includes replies + originals; single pass)
X_API_TIMELINE_EXCLUDES = ("retweets",)
INCREMENTAL_MAX_PAGES = 8
FULL_FETCH_MAX_PAGES = MAX_FETCH_PAGES

# X API credentials (non-password config in repo; override via env if needed)
X_BEARER_TOKEN = ""
X_CLIENT_ID = "YzBxeEd6WDBTMEY5VnZjZHp0aFg6MTpjaQ"
X_CLIENT_SECRET = "J-yTu1l52IjH3goD8CiMx7Yixx_Ac9GX9Xx9uGGPxm6Gf2qLw7"
X_API_KEY = ""
X_API_SECRET = ""
X_ACCESS_TOKEN = ""
X_ACCESS_TOKEN_SECRET = ""
