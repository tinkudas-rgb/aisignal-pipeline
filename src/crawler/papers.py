"""Phase I - research-paper vertical.

Primary source: paperswithcode.co's public JSON API (the successor mirror
of Papers with Code). Listing pages give title/arxiv id/published date;
the per-paper /repositories endpoint returns GitHub repo URL + star count
(synced from the GitHub/HF APIs, freshness stamped per repo).

Supplement: the arXiv API tops up recent cs.AI/cs.LG/cs.CL papers that have
no code link yet, so the vertical still grows past the mirror's catalog.
"""
from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET

from ..config import ARXIV_API, PWC_API
from ..models import PaperContent, PaperRecord, Source
from .base import AsyncCrawler, content_hash

log = logging.getLogger("crawler.papers")


async def _paper_repo(crawler: AsyncCrawler, paper_id: str) -> dict | None:
    res = await crawler.fetch(f"{PWC_API}/papers/{paper_id}/repositories")
    if not res.ok:
        return None
    import json
    try:
        repos = json.loads(res.text)
    except ValueError:
        return None
    gh = [r for r in repos if "github.com" in (r.get("url") or "")]
    if not gh:
        return None
    gh.sort(key=lambda r: (not r.get("is_official"), -(r.get("num_stars") or 0)))
    return gh[0]


async def fetch_papers(crawler: AsyncCrawler, target: int = 1100) -> list[tuple[PaperRecord, str]]:
    out, seen_arxiv, page = [], set(), 1
    while len(out) < target and page <= 60:
        res = await crawler.fetch(f"{PWC_API}/papers/?page={page}")
        if not res.ok:
            log.warning("papers page %d failed (%s)", page, res.status)
            break
        import json
        data = json.loads(res.text)
        results = data.get("results") or []
        if not results:
            break
        repo_tasks = {}
        for r in results:
            if not r.get("title") or not r.get("published"):
                continue
            key = r.get("arxiv_id") or r["id"]
            if key in seen_arxiv:
                continue
            seen_arxiv.add(key)
            if (r.get("code_repository_count") or 0) > 0:
                repo_tasks[r["id"]] = r
        # resolve repos for this page concurrently
        async def one(pid):
            return pid, await _paper_repo(crawler, pid)
        repo_map = dict(await asyncio.gather(*[one(pid) for pid in repo_tasks])) if repo_tasks else {}
        for pid, r in repo_tasks.items():
            repo = repo_map.get(pid)
            if not repo:
                continue
            authors = [a.get("name") if isinstance(a, dict) else str(a)
                       for a in (r.get("authors") or [])][:20]
            content = PaperContent(
                title=r["title"].strip(),
                authors=[a for a in authors if a],
                paper_url=(f"https://arxiv.org/abs/{r['arxiv_id']}"
                           if r.get("arxiv_id") else r.get("url_abs") or ""),
                abstract=(r.get("abstract") or "")[:1000] or None,
                github_url=repo.get("url"),
                github_stars=repo.get("num_stars"),
                stars_source=f"paperswithcode.co (synced {repo.get('updated_at')})",
                published_date=r.get("published"),
            )
            if not content.paper_url:
                continue
            rec = PaperRecord(
                source=Source(name="Papers with Code",
                              url=f"https://paperswithcode.co/paper/{pid}"),
                content=content)
            out.append((rec, content_hash("paper", r.get("arxiv_id") or pid)))
            if len(out) >= target:
                break
        log.info("papers: page %d, kept %d", page, len(out))
        page += 1
    return out


ARXIV_NS = {"a": "http://www.w3.org/2005/Atom"}


async def fetch_arxiv_supplement(crawler: AsyncCrawler, needed: int) -> list[tuple[PaperRecord, str]]:
    """Recent cs.AI/cs.LG/cs.CL papers without code links, straight from arXiv."""
    if needed <= 0:
        return []
    q = ("search_query=cat:cs.AI+OR+cat:cs.LG+OR+cat:cs.CL"
         "&sortBy=submittedDate&sortOrder=descending&max_results=" + str(min(needed * 2, 500)))
    res = await crawler.fetch(f"{ARXIV_API}?{q}")
    if not res.ok:
        return []
    root = ET.fromstring(res.text)
    out = []
    for e in root.findall("a:entry", ARXIV_NS):
        aid = (e.findtext("a:id", default="", namespaces=ARXIV_NS) or "").strip()
        title = " ".join((e.findtext("a:title", default="", namespaces=ARXIV_NS) or "").split())
        published = e.findtext("a:published", default="", namespaces=ARXIV_NS)
        authors = [a.findtext("a:name", default="", namespaces=ARXIV_NS)
                   for a in e.findall("a:author", ARXIV_NS)][:20]
        if not aid or not title:
            continue
        content = PaperContent(title=title, authors=[a for a in authors if a],
                               paper_url=aid, published_date=published)
        rec = PaperRecord(source=Source(name="arXiv", url=aid), content=content)
        out.append((rec, content_hash("paper", aid)))
        if len(out) >= needed:
            break
    return out
