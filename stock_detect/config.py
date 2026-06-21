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

USER_AGENT = "stock-detect/0.1 (research tool; Buz-deMelo methodology)"
