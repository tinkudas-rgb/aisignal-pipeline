"""Phase V - Playwright Async escalation tier for JS-rendered and
Cloudflare-fronted sources.

Used only when plain HTTP fails or returns a challenge page: the crawler
escalates a URL here, renders it in a real browser context with blocked
media (3-5x cheaper), and returns the rendered HTML. CAPTCHAs are treated
as a stop signal - the source cools down rather than being brute-forced.

Not exercised in the demo run (all listed sources answer plain HTTP); kept
as the production path for high-value protected sources.
"""
from __future__ import annotations

import asyncio
import logging

log = logging.getLogger("crawler.playwright")

CHALLENGE_MARKERS = ("cf-challenge", "Just a moment...", "datadome",
                     "g-recaptcha", "hcaptcha")


def looks_like_challenge(html: str) -> bool:
    return any(m in html for m in CHALLENGE_MARKERS)


async def render_page(url: str, timeout_ms: int = 30000) -> str | None:
    """Render one URL in headless Chromium; None when Playwright is absent
    or the page presents a hard challenge."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log.warning("playwright not installed; cannot render %s", url)
        return None
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context(
                user_agent=("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
                viewport={"width": 1366, "height": 900})
            page = await ctx.new_page()
            await page.route(
                "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,mp4}",
                lambda route: route.abort())
            resp = await page.goto(url, wait_until="domcontentloaded",
                                   timeout=timeout_ms)
            await page.wait_for_timeout(2500)  # let anti-bot checks settle
            html = await page.content()
            if resp is not None and resp.status >= 400:
                return None
            if looks_like_challenge(html):
                log.warning("%s presented a hard challenge; cooling down", url)
                return None
            return html
        finally:
            await browser.close()
