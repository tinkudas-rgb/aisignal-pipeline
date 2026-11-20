"""Phase I - startup vertical.

Primary source: the yc-oss mirror of the public Y Combinator directory
(~6.4k companies, one bulk JSON pull, no auth). Each record keeps its
canonical directory URL as source.url; the architecture doc describes the
per-company detail-page enrichment pass used for full 500k runs.
"""
from __future__ import annotations

import logging

from ..config import YC_OSS_ALL
from ..models import Source, StartupContent, StartupRecord
from .base import AsyncCrawler, content_hash

log = logging.getLogger("crawler.startups")

import re

AI_PATTERNS = [
    re.compile(r"\bai\b"), re.compile(r"artificial intelligence"),
    re.compile(r"machine learning"), re.compile(r"generative ai"),
    re.compile(r"\bml\b"), re.compile(r"deep learning"),
    re.compile(r"\bllms?\b"), re.compile(r"ai agents?"),
    re.compile(r"\bnlp\b"), re.compile(r"computer vision"),
]


def is_ai_company(c: dict) -> bool:
    hay = " ".join([str(c.get("industry") or ""), str(c.get("subindustry") or ""),
                    " ".join(c.get("tags") or []),
                    str(c.get("one_liner") or "")]).lower()
    return any(p.search(hay) for p in AI_PATTERNS)


async def fetch_startups(crawler: AsyncCrawler, limit: int = 1500,
                         ai_only: bool = True) -> list[tuple[StartupRecord, str]]:
    res = await crawler.fetch(YC_OSS_ALL)
    if not res.ok:
        raise RuntimeError(f"YC dataset fetch failed: {res.status} {res.error}")
    import json
    companies = json.loads(res.text)
    out = []
    for c in companies:
        if c.get("status") not in ("Active", "Public", None):
            continue
        if ai_only and not is_ai_company(c):
            continue
        slug = c.get("slug") or ""
        source_url = f"https://www.ycombinator.com/companies/{slug}"
        content = StartupContent(
            entityName=c.get("name") or slug,
            website=c.get("website"),
            description=(c.get("one_liner") or c.get("long_description") or "")[:500] or None,
            batch=c.get("batch"),
            location=c.get("all_locations"),
            tags=[t for t in (c.get("tags") or [])][:10],
            data={"employeeCount": c.get("team_size"),
                  "launchedAt": c.get("launched_at"),
                  "stage": c.get("stage"),
                  "isHiring": c.get("isHiring")},
        )
        rec = StartupRecord(source=Source(name="Y Combinator Directory", url=source_url),
                            content=content)
        out.append((rec, content_hash("startup", slug or content.entityName)))
        if len(out) >= limit:
            break
    log.info("startups: %d records prepared", len(out))
    return out
