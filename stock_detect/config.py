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
MA_WINDOWS = (7, 30, 90)
EVAL_WINDOWS = {"1w": 7, "1m": 30, "3m": 90}

USER_AGENT = "stock-detect/0.2 (research tool; X + WSB signals)"

# Fixed fetch window (paper-style ~63 trading days) and CI-safe caps
FETCH_WINDOW_DAYS = 63
MAX_FETCH_PAGES = 40
MAX_FETCH_POSTS = 4000
REQUEST_DELAY_SEC = 1.5
REDDIT_PAGE_SIZE = 100

# Default X accounts — AI/semi supply-chain analysts (X-first workflow)
DEFAULT_X_ACCOUNTS = [
    "aleabitoreddit",
]

# MySQL cache (investment_cache) — password via MYSQL_PASSWORD env / GitHub Secret only
MYSQL_HOST = "rm-wz91qxav0rb3uxf17ro.mysql.cn-shenzhen.rds.aliyuncs.com"
MYSQL_PORT = 3306
MYSQL_DATABASE = "cache_data"
MYSQL_USER = "cache_data_write"
MYSQL_SERVICE = "stock_detect"
MYSQL_TABLE_POSTS = f"{MYSQL_SERVICE}_x_posts"
MYSQL_TABLE_STATE = f"{MYSQL_SERVICE}_x_fetch_state"

# Incremental API fetch: fewer pages when cache already has history
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
