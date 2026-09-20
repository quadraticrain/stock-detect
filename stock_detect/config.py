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

# Phrases where a BUY/SELL/HOLD keyword carries no directional meaning.
#
# 背景：关键词计数器会把「short sellers」「AI bears」「stop the bleeding」这类
# 词当成作者本人的看空表态，但它们大多出现在作者**反驳空方**的语境里；
# 同理「short term」（时间尺度）、「earnings call」（业绩电话会）、「put ... hat on」
# （“戴上帽子”的动词 put）、「long term」（长期，不是做多）都是纯噪声。
#
# 实测（2026-08-24~31 @aleabitoreddit 107 帖）：13 次 SELL_WORDS 命中里 12 次
# 是误报，导致 NVDA / SIVE / AAOI 全部被误标为 consensus="sell"。
#
# 评分前先把这些短语从文本里掩掉（而不是从词表里删词），这样「buy puts」
# 「short $NVDA」这种真实表态仍能正常计分。模式均为小写匹配。
NON_SIGNAL_PHRASES = (
    # "short" 作为时间尺度 / 指代空方而非作者看空
    r"short[\s-]+term",
    r"short[\s-]+dated",
    r"short[\s-]+lived",
    r"short\s+sellers?",
    r"short\s+interest",
    r"short\s+squeeze",
    r"short\s+report",
    r"short\s+thesis",
    r"shorts?\s+(?:are|were|got|keep|piling)",
    r"in\s+short",
    r"short\s+supply",
    r"falls?\s+short",
    r"fell\s+short",
    # "put" 作为普通动词（非看跌期权）
    r"put\s+(?:my|his|her|their|our|its|a|an|the|it|that|this|substantially|more|less|together|forth|out|off)\b",
    r"put\s+\w+\s+hat\s+on",
    r"puts?\s+it\b",
    r"(?:was|were)\s+put\s+on",
    # "call" 作为业绩会 / 电话会议（非看涨期权）
    r"earnings\s+calls?",
    r"conference\s+calls?",
    r"analyst\s+calls?",
    r"(?:the|these|those|their|his|her|its|entire|whole)\s+calls?\b",
    r"on\s+the\s+call",
    r"calls?\s+(?:for|it|him|her|them|into\s+question)\b",
    # "long" 作为时间尺度（非做多）
    r"long[\s-]+term",
    r"long[\s-]+dated",
    r"long[\s-]+run",
    r"long[\s-]+standing",
    r"how\s+long",
    r"(?:as|so)\s+long\s+as",
    # 看空阵营指代（作者通常在反驳他们）
    r"(?:ai|the|these|those)\s+bears?\b",
    r"permabear\w*",
    r"bearish\s+(?:case|thesis|narrative|takes?|arguments?|sentiment)",
    r"bear\s+(?:case|thesis|market|raid)",
    # "sell" 的非表态用法
    r"sell[\s-]+out\s+to",
    r"sell[\s-]?side",
    r"sell\s+order",
    # "dump" 的非表态用法
    r"data\s+dump",
    # "hold" 的非表态用法
    r"hold\s+(?:a|an|the)\s+(?:call|meeting|conference|vote)",
    r"holding\s+company",
    # 其他噪声
    r"stop\s+the\s+bleeding",
)

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
# Xueqiu users (段永平, 但斌) — fetched locally (scripts/local_xueqiu_fetch.py),
# no longer via GitHub Actions (cookie refresh runs on the local Mac).
SCHEDULED_XUEQIU_USERS = ("1247347556", "1102105103")  # 段永平, 但斌
SCHEDULED_XUEQIU_ACCOUNTS = tuple(f"xueqiu:{user}" for user in SCHEDULED_XUEQIU_USERS)

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


def active_scheduled_x_accounts() -> tuple[str, ...]:
    """CI scheduled accounts minus explicitly disabled slugs."""
    return tuple(a for a in CI_SCHEDULED_X_ACCOUNTS if a not in DISABLED_X_ACCOUNTS)


def active_scheduled_social_accounts() -> tuple[str, ...]:
    return active_scheduled_x_accounts() + SCHEDULED_XUEQIU_ACCOUNTS

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
