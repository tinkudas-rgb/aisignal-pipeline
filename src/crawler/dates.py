"""Publication-date extraction and normalization (Phase II).

Strategy ladder: structured meta/JSON-LD -> feed timestamps -> relative
expressions ("2 hours ago") -> last-run watermark heuristic. Every result
carries a confidence label so downstream freshness filtering can be strict.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import dateparser

RELATIVE_RE = re.compile(
    r"(\d+)\s+(second|minute|hour|day|week|month)s?\s+ago", re.I)

_META_PATTERNS = [
    re.compile(r'property="article:published_time"\s+content="([^"]+)"', re.I),
    re.compile(r'name="(?:date|publishdate|pubdate|parsely-pub-date)"\s+content="([^"]+)"', re.I),
    re.compile(r'"datePublished"\s*:\s*"([^"]+)"', re.I),
    re.compile(r'itemprop="datePublished"\s+content="([^"]+)"', re.I),
    re.compile(r'<time[^>]+datetime="([^"]+)"', re.I),
]


def parse_any_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    try:
        dt = parsedate_to_datetime(raw)  # RFC-822 (RSS pubDate)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        pass
    m = RELATIVE_RE.search(raw)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        delta = {"second": timedelta(seconds=n), "minute": timedelta(minutes=n),
                 "hour": timedelta(hours=n), "day": timedelta(days=n),
                 "week": timedelta(weeks=n), "month": timedelta(days=30 * n)}[unit]
        return datetime.now(timezone.utc) - delta
    dt = dateparser.parse(raw, settings={"TO_TIMEZONE": "UTC",
                                         "RETURN_AS_TIMEZONE_AWARE": True})
    return dt


def extract_date_from_html(html: str) -> tuple[datetime | None, str]:
    """Return (datetime, confidence). Confidence: high = structured tag,
    medium = relative text found in page."""
    for pat in _META_PATTERNS:
        m = pat.search(html)
        if m:
            dt = parse_any_date(m.group(1))
            if dt:
                return dt, "high"
    m = RELATIVE_RE.search(html)
    if m:
        return parse_any_date(m.group(0)), "medium"
    return None, "none"


def is_within_hours(dt: datetime | None, hours: float,
                    now: datetime | None = None) -> bool:
    if dt is None:
        return False
    now = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt) <= timedelta(hours=hours) and dt <= now + timedelta(minutes=5)
