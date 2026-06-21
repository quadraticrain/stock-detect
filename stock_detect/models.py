"""Shared data models for social post sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SocialPost:
    id: str
    text: str
    author: str
    source: str  # x | wsb
    created: datetime
    score: int
    url: str
    tickers: list[str] = field(default_factory=list)
    meta: str = ""
