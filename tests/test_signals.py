"""Tests for WSB signal extraction."""

from datetime import datetime, timezone

from stock_detect.signal_extractor import (
    aggregate_daily_consensus,
    extract_post_signals,
    is_actionable_post,
)


def test_buy_signal_from_dd_post():
    created = datetime(2024, 1, 15, tzinfo=timezone.utc)
    signals = extract_post_signals(
        title="$NVDA is a buy before earnings",
        body="I'm loading calls on NVDA. Strong AI demand, definitely a buy.",
        flair="DD",
        created=created,
        score=120,
        valid_tickers={"NVDA", "AMD"},
    )
    assert len(signals) == 1
    assert signals[0].ticker == "NVDA"
    assert signals[0].recommendation == "buy"


def test_reactive_flair_excluded():
    assert is_actionable_post("Loss", "I lost everything on GME") is False
    assert is_actionable_post("DD", "Detailed analysis here") is True


def test_ambiguous_ticker_requires_dollar():
    created = datetime(2024, 1, 15, tzinfo=timezone.utc)
    without = extract_post_signals(
        "IT sector looks good",
        "buy tech stocks",
        "Discussion",
        created,
        10,
        {"IT"},
    )
    with_dollar = extract_post_signals(
        "$IT sector looks good",
        "buy $IT now",
        "Discussion",
        created,
        10,
        {"IT"},
    )
    assert without == []
    assert len(with_dollar) == 1


def test_daily_consensus_threshold():
    created = datetime(2024, 1, 15, 12, tzinfo=timezone.utc)
    signals = []
    for _ in range(3):
        signals.extend(
            extract_post_signals(
                "$AMD buy",
                "buy AMD calls",
                "DD",
                created,
                50,
                {"AMD"},
            )
        )
    signals.extend(
        extract_post_signals(
            "$AMD sell",
            "sell AMD puts",
            "Discussion",
            created,
            10,
            {"AMD"},
        )
    )
    daily = aggregate_daily_consensus(signals)
    assert daily[0].signal == "buy"
