"""Phase II - AI job-board ingestion with a strict 24-hour window.

Five keyless job APIs/feeds. Each normalizer maps the board's payload to
the canonical Job schema; dates are normalized through the same ladder as
news. AI relevance is a keyword filter over title + description.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from ..config import AI_KEYWORDS, JOB_SOURCES
from ..models import JobContent, JobRecord, Source
from .base import AsyncCrawler, content_hash
from .dates import is_within_hours, parse_any_date
from .news import strip_html

log = logging.getLogger("crawler.jobs")

_ROLE_FAMILIES = [
    (r"\b(ml|machine learning|ai)\b", "Machine Learning"),
    (r"data scien", "Data Science"),
    (r"data engineer", "Data Engineering"),
    (r"\b(nlp|llm|language)\b", "NLP"),
    (r"computer vision|vision", "Computer Vision"),
    (r"robot", "Robotics"),
    (r"research", "Research"),
    (r"engineer|developer|software", "Engineering"),
]


def role_family(title: str, description: str = "") -> str:
    hay = f"{title} {description}".lower()
    for pat, fam in _ROLE_FAMILIES:
        if re.search(pat, hay):
            return fam
    return "Engineering"


def is_ai_job(title: str, description: str = "") -> bool:
    hay = f" {title} {description[:600]} ".lower()
    return any(k in hay for k in AI_KEYWORDS)


def _norm_arbeitnow(data: dict) -> list[dict]:
    return [{"title": j.get("title", ""), "company": j.get("company_name", ""),
             "url": j.get("url", ""), "date": j.get("created_at"),
             "location": j.get("location", ""),
             "is_remote": bool(j.get("remote")),
             "description": strip_html(j.get("description") or "")[:2000]}
            for j in data.get("data", [])]


def _norm_remoteok(data) -> list[dict]:
    out = []
    for j in (data if isinstance(data, list) else []):
        if not isinstance(j, dict) or "position" not in j:
            continue
        out.append({"title": j.get("position", ""), "company": j.get("company", ""),
                    "url": j.get("url") or j.get("apply_url") or "",
                    "date": j.get("date"), "location": j.get("location") or "Remote",
                    "is_remote": True,
                    "description": strip_html(j.get("description") or "")[:2000]})
    return out


def _norm_jobicy(data: dict) -> list[dict]:
    return [{"title": j.get("jobTitle", ""), "company": j.get("companyName", ""),
             "url": j.get("url", ""), "date": j.get("pubDate"),
             "location": j.get("jobGeo") or "Remote", "is_remote": True,
             "description": strip_html(j.get("jobDescription") or "")[:2000]}
            for j in data.get("jobs", [])]


def _norm_remotive(data: dict) -> list[dict]:
    return [{"title": j.get("title", ""), "company": j.get("company_name", ""),
             "url": j.get("url", ""), "date": j.get("publication_date"),
             "location": j.get("candidate_required_location") or "Remote",
             "is_remote": True,
             "description": strip_html(j.get("description") or "")[:2000]}
            for j in data.get("jobs", [])]


def _norm_wwr(xml_text: str) -> list[dict]:
    out = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    for item in root.iter("item"):
        out.append({"title": (item.findtext("title") or "").strip(),
                    "company": "",  # WWR embeds company in title "Company: Role"
                    "url": (item.findtext("link") or "").strip(),
                    "date": (item.findtext("pubDate") or "").strip(),
                    "location": "Remote", "is_remote": True,
                    "description": strip_html(item.findtext("description") or "")[:2000]})
    for j in out:
        if ": " in j["title"]:
            j["company"], j["title"] = [p.strip() for p in j["title"].split(": ", 1)]
    return out


NORMALIZERS = {"Arbeitnow": _norm_arbeitnow, "RemoteOK": _norm_remoteok,
               "Jobicy": _norm_jobicy, "Remotive": _norm_remotive,
               "WeWorkRemotely": _norm_wwr}


async def fetch_jobs(crawler: AsyncCrawler, store, window_hours: float = 24.0
                     ) -> list[tuple[JobRecord, str]]:
    out: list[tuple[JobRecord, str]] = []
    now = datetime.now(timezone.utc)
    for source_name, api_url in JOB_SOURCES.items():
        res = await crawler.fetch(api_url)
        if not res.ok:
            log.warning("jobs %s failed: %s", source_name, res.status)
            continue
        try:
            payload = json.loads(res.text)
            jobs = NORMALIZERS[source_name](payload)
        except ValueError:
            jobs = NORMALIZERS[source_name](res.text)
        kept = 0
        for j in jobs:
            if not j["title"] or not j["url"]:
                continue
            if not is_ai_job(j["title"], j.get("description") or ""):
                continue
            dt = parse_any_date(str(j.get("date") or ""))
            if dt is None:
                if store.get_watermark(source_name) is None:
                    continue
                dt = now  # heuristic: new link on a board we poll
            if not is_within_hours(dt, window_hours, now):
                continue
            h = content_hash("job", j["url"])
            if store.seen(h):
                continue
            content = JobContent(title=j["title"], company=j["company"] or "Unknown",
                                 date=dt.isoformat(), url=j["url"],
                                 location=j.get("location"),
                                 is_remote=bool(j.get("is_remote")),
                                 role_family=role_family(j["title"], j.get("description") or ""),
                                 description=(j.get("description") or "")[:2000] or None)
            out.append((JobRecord(source=Source(name=source_name, url=j["url"]),
                                  content=content), h))
            kept += 1
        store.set_watermark(source_name, now.isoformat())
        log.info("jobs %s: %d fresh AI jobs", source_name, kept)
    return out
