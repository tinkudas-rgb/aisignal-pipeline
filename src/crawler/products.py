"""Phase I - product vertical.

Primary source: opentools.ai, an AI-tools directory. The public sitemap
lists every tool page; each page embeds a JSON payload with the tool's
name, description, categories and pricing model. We parse that embedded
payload deterministically (no LLM needed on this source).

Supplement: the Hugging Face Spaces API (keyless) contributes community
AI apps when more volume is required.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re

from ..config import HF_SPACES_API, OPENTOOLS_BASE, OPENTOOLS_SITEMAP
from ..models import PricingModel, ProductContent, ProductRecord, Source
from .base import AsyncCrawler, content_hash

log = logging.getLogger("crawler.products")

_LOC_RE = re.compile(r"<loc>(https://opentools\.ai/tools/[^<]+)</loc>")
_JSON_RE = re.compile(r'\\"(?:pricingModel|pricing_type)\\"', re.I)
_PRICE_RE = re.compile(r'\\"pricingModel\\":\\"(Free|Freemium|Paid|Enterprise)\\"', re.I)
_NAME_RE = re.compile(r'\\"tool_name\\":\\"((?:[^"\\]|\\.){1,120}?)\\"')
_DESC_RE = re.compile(r'\\"(?:description|short_description)\\":\\"((?:[^"\\]|\\.){0,400}?)\\"')
_CAT_RE = re.compile(r'\\"category\\":\\"((?:[^"\\]){1,60}?)\\"', re.I)

_PRICING_MAP = {"free": PricingModel.FREE, "freemium": PricingModel.FREEMIUM,
                "paid": PricingModel.PAID, "enterprise": PricingModel.ENTERPRISE}


def _unescape(s: str) -> str:
    out = s.replace('\\"', '"').replace("\\n", " ").replace("\\/", "/")
    out = out.replace("\\\\", " ").replace("\\", " ")
    return " ".join(out.split())


def parse_tool_page(html: str, url: str) -> ProductRecord | None:
    """Deterministic extraction from the embedded Next.js JSON payload."""
    m = _PRICE_RE.search(html)
    pricing = _PRICING_MAP.get(m.group(1).lower()) if m else None
    name_m = _NAME_RE.search(html)
    if not name_m:
        # fall back to the URL slug as the raw name candidate
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        if not slug:
            return None
        name = slug.replace("-", " ").title()
    else:
        name = _unescape(name_m.group(1))
    desc_m = _DESC_RE.search(html)
    desc = _unescape(desc_m.group(1))[:300] if desc_m else None
    cats: list[str] = []
    for cm in _CAT_RE.finditer(html):
        cats.append(cm.group(1))
        if len(cats) >= 5:
            break
    content = ProductContent(
        productName=name,
        startupName=name,
        description=desc,
        pricingModel=pricing or PricingModel.FREEMIUM,
        categories=list(dict.fromkeys(cats))[:5],
    )
    return ProductRecord(source=Source(name="OpenTools.ai", url=url), content=content)


async def fetch_products(crawler: AsyncCrawler, target: int = 1100) -> list[tuple[ProductRecord, str]]:
    res = await crawler.fetch(OPENTOOLS_SITEMAP)
    if not res.ok:
        raise RuntimeError(f"opentools sitemap failed: {res.status}")
    urls = _LOC_RE.findall(res.text)
    log.info("opentools sitemap: %d tool urls", len(urls))
    out: list[tuple[ProductRecord, str]] = []
    seen: set[str] = set()
    queue = [u for u in urls if u.rsplit("/", 1)[-1] not in seen]
    idx = 0
    batch = 16
    while len(out) < target and idx < len(queue):
        chunk = queue[idx:idx + batch]
        idx += batch
        results = await asyncio.gather(*[crawler.fetch(u) for u in chunk])
        for u, r in zip(chunk, results):
            slug = u.rstrip("/").rsplit("/", 1)[-1]
            seen.add(slug)
            if not r.ok:
                continue
            rec = parse_tool_page(r.text, u)
            if rec is None:
                continue
            h = content_hash("product", slug)
            out.append((rec, h))
        if idx % 160 == 0:
            log.info("products: %d/%d pages, kept %d", idx, len(queue), len(out))
    log.info("products: kept %d of %d fetched", len(out), idx)
    return out


async def fetch_hf_spaces(crawler: AsyncCrawler, needed: int) -> list[tuple[ProductRecord, str]]:
    if needed <= 0:
        return []
    out, skip = [], 0
    while len(out) < needed and skip < needed * 3:
        url = f"{HF_SPACES_API}?limit=100&skip={skip}&full=true&sort=likes&direction=-1"
        res = await crawler.fetch(url)
        if not res.ok:
            break
        try:
            items = json.loads(res.text)
        except ValueError:
            break
        if not items:
            break
        for it in items:
            sid = it.get("id")
            if not sid:
                continue
            card = it.get("cardData") or {}
            content = ProductContent(
                productName=card.get("title") or sid.split("/")[-1],
                startupName=it.get("author") or sid.split("/")[0],
                description=(card.get("short_description") or "")[:300] or None,
                pricingModel=PricingModel.FREE,
                categories=[str(t) for t in (it.get("tags") or [])[:5]],
            )
            rec = ProductRecord(
                source=Source(name="Hugging Face Spaces",
                              url=f"https://huggingface.co/spaces/{sid}"),
                content=content)
            out.append((rec, content_hash("product", "hf", sid)))
            if len(out) >= needed:
                break
        skip += 100
    return out
