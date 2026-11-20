"""Async crawling primitives: bounded concurrency, retries with
exponential backoff + full jitter, per-host politeness, UA rotation.

Designed so the same code runs 1k records locally or 500k records on a
fleet: concurrency limits and queue depth are configuration, not code.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import time
from dataclasses import dataclass, field

import httpx

from ..config import USER_AGENTS

log = logging.getLogger("crawler")


@dataclass
class FetchResult:
    url: str
    status: int
    text: str
    elapsed: float
    attempts: int = 1
    error: str | None = None

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300 and self.error is None


def backoff_delay(attempt: int, base: float = 1.0, cap: float = 60.0) -> float:
    """Exponential backoff with full jitter (AWS-style)."""
    return random.uniform(0, min(cap, base * (2 ** attempt)))


class AsyncCrawler:
    """httpx-based async crawler with a global semaphore and per-host pacing."""

    def __init__(self, concurrency: int = 8, timeout: float = 30.0,
                 max_retries: int = 4, per_host_delay: float = 0.25):
        self.sem = asyncio.Semaphore(concurrency)
        self.timeout = timeout
        self.max_retries = max_retries
        self.per_host_delay = per_host_delay
        self._host_locks: dict[str, float] = {}
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=64, max_keepalive_connections=16),
        )
        return self

    async def __aexit__(self, *exc):
        if self._client:
            await self._client.aclose()

    async def _pace(self, host: str):
        last = self._host_locks.get(host, 0.0)
        wait = self.per_host_delay - (time.monotonic() - last)
        if wait > 0:
            await asyncio.sleep(wait)
        self._host_locks[host] = time.monotonic()

    async def fetch(self, url: str) -> FetchResult:
        host = httpx.URL(url).host
        async with self.sem:
            for attempt in range(self.max_retries + 1):
                await self._pace(host)
                t0 = time.monotonic()
                try:
                    resp = await self._client.get(
                        url, headers={"User-Agent": random.choice(USER_AGENTS)})
                    elapsed = time.monotonic() - t0
                    if resp.status_code in (429, 500, 502, 503, 504):
                        delay = backoff_delay(attempt)
                        log.warning("%s -> %s, retry %d in %.1fs",
                                    url, resp.status_code, attempt + 1, delay)
                        await asyncio.sleep(delay)
                        continue
                    return FetchResult(url, resp.status_code, resp.text,
                                       elapsed, attempts=attempt + 1)
                except (httpx.HTTPError, asyncio.TimeoutError) as e:
                    delay = backoff_delay(attempt)
                    log.warning("%s -> %s, retry %d in %.1fs", url, e, attempt + 1, delay)
                    if attempt == self.max_retries:
                        return FetchResult(url, 0, "", time.monotonic() - t0,
                                           attempts=attempt + 1, error=str(e))
                    await asyncio.sleep(delay)
        return FetchResult(url, 0, "", 0, error="exhausted")


def content_hash(*parts: str) -> str:
    """Stable dedupe key from the semantically identifying parts of a record."""
    h = hashlib.sha256()
    for p in parts:
        h.update((p or "").strip().lower().encode())
        h.update(b"\x00")
    return h.hexdigest()[:24]
