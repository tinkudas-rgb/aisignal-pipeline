"""Phase II - AI news ingestion with a strict 24-hour freshness window.

Five RSS/Atom feeds give candidate items with timestamps; every candidate
is then crawled for full text. Publication dates come from the feed first
(high confidence), then page meta/JSON-LD (high), then relative-date text
(medium); items with no date at all fall back to the source's last-run
watermark heuristic. Anything outside 24h or already seen is dropped.
"""
from __future__ import annotations

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from ..config import NEWS_FEED_FALLBACKS, NEWS_FEEDS
from ..models import NewsContent, NewsRecord, Source
from .base import AsyncCrawler, content_hash
from .dates import extract_date_from_html, is_within_hours, parse_any_date

log = logging.getLogger("crawler.news")

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    return _WS_RE.sub(" ", text).strip()


def extract_full_text(html: str) -> str:
    """Lightweight readability: prefer <article>, else the densest <p> run."""
    m = re.search(r"<article[^>]*>(.*?)</article>", html, re.S | re.I)
    body = m.group(1) if m else html
    paras = re.findall(r"<p[^>]*>(.*?)</p>", body, re.S | re.I)
    text = "\n\n".join(strip_html(p) for p in paras if len(strip_html(p)) > 60)
    return text[:12000]


def parse_feed(xml_text: str) -> list[dict]:
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    for item in root.iter("item"):
        items.append({
            "headline": (item.findtext("title") or "").strip(),
            "url": (item.findtext("link") or "").strip(),
            "published": (item.findtext("pubDate") or
                          item.findtext("date") or "").strip(),
        })
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
        link = ""
        for l in entry.findall("a:link", ns):
            if l.get("rel") in (None, "alternate"):
                link = l.get("href", "")
        items.append({
            "headline": (entry.findtext("a:title", default="", namespaces=ns) or "").strip(),
            "url": link.strip(),
            "published": (entry.findtext("a:published", default="", namespaces=ns) or
                          entry.findtext("a:updated", default="", namespaces=ns)).strip(),
        })
    return items


async def fetch_news(crawler: AsyncCrawler, store, window_hours: float = 24.0
                     ) -> list[tuple[NewsRecord, str]]:
    out: list[tuple[NewsRecord, str]] = []
    now = datetime.now(timezone.utc)
    for source_name, feed_url in NEWS_FEEDS.items():
        feed_res = await crawler.fetch(feed_url)
        if not feed_res.ok:
            for alt in NEWS_FEED_FALLBACKS.get(source_name, []):
                log.warning("news feed %s failed (%s); trying fallback %s",
                            source_name, feed_res.status, alt)
                feed_res = await crawler.fetch(alt)
                if feed_res.ok:
                    break
        if not feed_res.ok:
            log.warning("news feed %s and fallbacks failed", source_name)
            continue
        candidates = parse_feed(feed_res.text)[:40]
        watermark = store.get_watermark(source_name)
        watermark_dt = parse_any_date(watermark) if watermark else None

        async def one(item: dict) -> tuple[NewsRecord, str] | None:
            url, headline = item["url"], item["headline"]
            if not url or not headline:
                return None
            h = content_hash("news", url)
            if store.seen(h):
                return None
            feed_dt = parse_any_date(item.get("published"))
            confidence = "high" if feed_dt else "none"
            page = await crawler.fetch(url)
            full_text = extract_full_text(page.text) if page.ok else ""
            dt = feed_dt
            if dt is None and page.ok:
                page_dt, confidence = extract_date_from_html(page.text)
                dt = page_dt
            if dt is None:
                # Heuristic: no date anywhere; treat as fresh only when the
                # link is new since the last successful run of this source.
                if watermark_dt is None:
                    return None  # first run: cannot vouch for freshness
                confidence = "heuristic"
                dt = now
            if not is_within_hours(dt, window_hours, now):
                return None
            content = NewsContent(headline=headline, url=url,
                                  published_date=dt.isoformat(),
                                  full_text=full_text or None,
                                  date_confidence=confidence)
            return NewsRecord(source=Source(name=source_name, url=url),
                              content=content), h

        results = await asyncio.gather(*[one(c) for c in candidates])
        kept = [r for r in results if r]
        out.extend(kept)
        store.set_watermark(source_name, now.isoformat())
        log.info("news %s: %d fresh of %d candidates", source_name, len(kept),
                 len(candidates))
    return out
