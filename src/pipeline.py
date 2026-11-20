"""Pipeline orchestrator: runs the acquisition phases and persists records.

Phase I (bulk): startups + products + papers, with entity resolution.
Phase II (fresh): news + jobs inside the 24h window.
Entity resolution runs over startup/product names as they land, so the
Entity Mapping Log is always a byproduct of ingestion, never a bolt-on.
"""
from __future__ import annotations

import logging

from .crawler.base import AsyncCrawler
from .crawler.jobs import fetch_jobs
from .crawler.news import fetch_news
from .crawler.papers import fetch_arxiv_supplement, fetch_papers
from .crawler.products import fetch_hf_spaces, fetch_products
from .crawler.startups import fetch_startups
from .resolve.entities import EntityResolver
from .storage import Store

log = logging.getLogger("pipeline")


def _name_of(rec) -> str:
    c = rec.content
    if rec.recordType == "JOB":
        return getattr(c, "company", None) or ""
    if rec.recordType == "NEWS":
        return ""  # headlines are not entities
    return getattr(c, "entityName", None) or getattr(c, "productName", None) \
        or getattr(c, "title", None) or ""


async def run_phase(phase: str, store: Store, targets: dict | None = None) -> dict:
    targets = targets or {"startups": 1500, "products": 1100, "papers": 1100}
    resolver = EntityResolver()
    summary: dict[str, int] = {}
    async with AsyncCrawler(concurrency=8, per_host_delay=0.3) as crawler:
        if phase in ("phase1", "all"):
            startups = await fetch_startups(crawler, limit=targets["startups"])
            summary["startups"] = _persist(store, resolver, startups)
            papers = await fetch_papers(crawler, target=targets["papers"])
            if len(papers) < targets["papers"]:
                papers += await fetch_arxiv_supplement(
                    crawler, targets["papers"] - len(papers))
            summary["papers"] = _persist(store, resolver, papers)
            products = await fetch_products(crawler, target=targets["products"])
            if len(products) < targets["products"]:
                products += await fetch_hf_spaces(
                    crawler, targets["products"] - len(products))
            summary["products"] = _persist(store, resolver, products)
        if phase in ("phase2", "all"):
            news = await fetch_news(crawler, store)
            summary["news"] = _persist(store, resolver, news)
            jobs = await fetch_jobs(crawler, store)
            summary["jobs"] = _persist(store, resolver, jobs)
    return summary


def _persist(store: Store, resolver: EntityResolver,
             records: list[tuple]) -> int:
    new = 0
    for rec, h in records:
        raw = _name_of(rec)
        canonical = resolver.resolve_and_log(store, raw, rec.recordType) if raw else ""
        if store.upsert_record(h, rec.recordType, rec.source.name, rec.source.url,
                               canonical, rec.model_dump(mode="json"),
                               rec.collectedAt):
            new += 1
    return new
