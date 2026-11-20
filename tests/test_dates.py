import sys
from datetime import datetime, timedelta, timezone
sys.path.insert(0, '/home/sandbox/aisignal-pipeline')
from src.crawler.dates import (extract_date_from_html, is_within_hours,
                               parse_any_date)

NOW = datetime(2026, 11, 20, 12, 0, 0, tzinfo=timezone.utc)


def test_rfc822():
    dt = parse_any_date("Fri, 20 Nov 2026 10:30:00 GMT")
    assert dt == datetime(2026, 11, 20, 10, 30, tzinfo=timezone.utc)


def test_iso8601():
    dt = parse_any_date("2026-11-20T09:15:00+00:00")
    assert dt == datetime(2026, 11, 20, 9, 15, tzinfo=timezone.utc)


def test_relative_hours():
    dt = parse_any_date("3 hours ago")
    assert abs((datetime.now(timezone.utc) - dt) - timedelta(hours=3)) < timedelta(minutes=2)


def test_relative_days():
    dt = parse_any_date("2 days ago")
    assert abs((datetime.now(timezone.utc) - dt) - timedelta(days=2)) < timedelta(minutes=2)


def test_garbage_returns_none():
    assert parse_any_date("not a date at all !!!") is None
    assert parse_any_date("") is None
    assert parse_any_date(None) is None


def test_meta_extraction_high_confidence():
    html = '<html><head><meta property="article:published_time" content="2026-11-20T08:00:00Z"></head></html>'
    dt, conf = extract_date_from_html(html)
    assert conf == "high" and dt == datetime(2026, 11, 20, 8, 0, tzinfo=timezone.utc)


def test_jsonld_extraction():
    html = '<script type="application/ld+json">{"datePublished": "2026-11-19T22:00:00Z"}</script>'
    dt, conf = extract_date_from_html(html)
    assert conf == "high"


def test_no_date_anywhere():
    dt, conf = extract_date_from_html("<html><body>hello world</body></html>")
    assert dt is None and conf == "none"


def test_freshness_window():
    fresh = NOW - timedelta(hours=23, minutes=59)
    stale = NOW - timedelta(hours=24, minutes=1)
    future = NOW + timedelta(hours=2)
    assert is_within_hours(fresh, 24, NOW)
    assert not is_within_hours(stale, 24, NOW)
    assert not is_within_hours(future, 24, NOW)
    assert not is_within_hours(None, 24, NOW)
