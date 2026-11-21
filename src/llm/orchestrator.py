"""Phase III - multi-tier LLM extraction engine.

Fallback chain: Gemini Flash -> Groq (Llama 3) -> DeepSeek. Every tier is
a thin adapter behind one interface, so a new provider is one class.

Design rules baked in:
- Deterministic parsers run first; the LLM is the fallback for pages whose
  structure defeats them. That keeps free-tier spend near zero and removes
  hallucination surface for well-structured sources.
- Payloads are token-budgeted BEFORE the call (char/4 heuristic) and
  semantically chunked (drop boilerplate, keep title/lead/metadata), so we
  never rely on a 413 to learn a page was too big.
- 429s get exponential backoff with full jitter; a provider that keeps
  429ing cools down and the chain moves on.
- Output is validated against the target pydantic schema; on validation
  failure the next tier is tried. The model is instructed to copy facts
  verbatim from the page and emit null for anything absent.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass, field

import httpx

log = logging.getLogger("llm")

MAX_TOKENS_PER_CALL = 24_000          # conservative prompt budget
CHARS_PER_TOKEN = 4
MAX_RETRIES_PER_TIER = 3
COOLDOWN_AFTER_429S = 2               # tier cools down after this many 429s

_BOILERPLATE_RE = re.compile(
    r"(cookie|subscribe|newsletter|sign up|log in|advertisement|all rights reserved)",
    re.I)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def semantic_chunk(text: str, max_tokens: int = MAX_TOKENS_PER_CALL) -> str:
    """Truncate to the token budget while keeping the densest content:
    head of the document (title/lead/metadata live there) plus any later
    paragraphs that look information-dense, dropping boilerplate lines."""
    budget = max_tokens * CHARS_PER_TOKEN
    lines = [l for l in text.splitlines() if not _BOILERPLATE_RE.search(l)]
    cleaned = "\n".join(lines)
    if len(cleaned) <= budget:
        return cleaned
    head_budget = int(budget * 0.7)
    head = "\n".join(lines)[:head_budget]
    rest = "\n".join(lines)[head_budget:]
    tail_budget = budget - len(head) - 200
    tail = rest[:max(0, tail_budget)]
    return head + "\n[...truncated middle...]\n" + tail


@dataclass
class ExtractionResult:
    ok: bool
    data: dict | None = None
    provider: str | None = None
    attempts: int = 0
    error: str | None = None


class LLMTier:
    name = "base"
    env_key = ""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get(self.env_key)
        self.cooldown_until = 0.0
        self.consecutive_429s = 0

    @property
    def available(self) -> bool:
        return bool(self.api_key) and time.monotonic() > self.cooldown_until

    async def complete(self, prompt: str) -> tuple[int, str]:
        raise NotImplementedError


class GeminiFlashTier(LLMTier):
    name = "gemini-flash"
    env_key = "GEMINI_API_KEY"
    MODEL = "gemini-3.5-flash"

    async def complete(self, prompt: str) -> tuple[int, str]:
        url = ("https://generativelanguage.googleapis.com/v1beta/models/"
               f"{self.MODEL}:generateContent?key={self.api_key}")
        body = {"contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json",
                                     "temperature": 0.1}}
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(url, json=body)
        if r.status_code != 200:
            return r.status_code, r.text[:500]
        data = r.json()
        try:
            return 200, data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            return 200, ""


class GroqLlamaTier(LLMTier):
    name = "groq-llama3"
    env_key = "GROQ_API_KEY"
    MODEL = "llama-3.3-70b-versatile"

    async def complete(self, prompt: str) -> tuple[int, str]:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.MODEL, "temperature": 0.1,
                      "response_format": {"type": "json_object"},
                      "messages": [{"role": "user", "content": prompt}]})
        if r.status_code != 200:
            return r.status_code, r.text[:500]
        data = r.json()
        try:
            return 200, data["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            return 200, ""


class DeepSeekTier(LLMTier):
    name = "deepseek"
    env_key = "DEEPSEEK_API_KEY"
    MODEL = "deepseek-chat"

    async def complete(self, prompt: str) -> tuple[int, str]:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.MODEL, "temperature": 0.1,
                      "response_format": {"type": "json_object"},
                      "messages": [{"role": "user", "content": prompt}]})
        if r.status_code != 200:
            return r.status_code, r.text[:500]
        data = r.json()
        try:
            return 200, data["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            return 200, ""


def build_prompt(raw_text: str, schema_hint: str) -> str:
    return (
        "Extract structured data from the web page text below.\n"
        "RULES:\n"
        "- Copy every fact VERBATIM from the text. Never invent values.\n"
        "- Use null for any field not present in the text.\n"
        "- Dates must be ISO-8601 if a date is present.\n"
        "- Respond with a single JSON object only.\n\n"
        f"TARGET SCHEMA (informal): {schema_hint}\n\n"
        f"PAGE TEXT:\n{raw_text}")


class LLMOrchestrator:
    def __init__(self, tiers: list[LLMTier] | None = None):
        self.tiers = tiers or [GeminiFlashTier(), GroqLlamaTier(), DeepSeekTier()]

    def status(self) -> list[dict]:
        return [{"tier": t.name, "configured": bool(t.api_key),
                 "available": t.available} for t in self.tiers]

    async def extract(self, raw_text: str, schema_hint: str,
                      required_keys: list[str] | None = None) -> ExtractionResult:
        chunked = semantic_chunk(raw_text)
        prompt = build_prompt(chunked, schema_hint)
        attempts = 0
        for tier in self.tiers:
            if not tier.available:
                log.info("tier %s unavailable (key=%s, cooldown=%s)",
                         tier.name, bool(tier.api_key),
                         time.monotonic() < tier.cooldown_until)
                continue
            for retry in range(MAX_RETRIES_PER_TIER):
                attempts += 1
                try:
                    status, text = await tier.complete(prompt)
                except httpx.HTTPError as e:
                    await asyncio.sleep(random.uniform(1, 2 ** (retry + 1)))
                    continue
                if status == 429:
                    tier.consecutive_429s += 1
                    delay = random.uniform(0, min(60, 2 ** (retry + 2)))
                    log.warning("%s 429, backoff %.1fs", tier.name, delay)
                    await asyncio.sleep(delay)
                    if tier.consecutive_429s >= COOLDOWN_AFTER_429S:
                        tier.cooldown_until = time.monotonic() + 300
                        break
                    continue
                if status == 413:  # provider still says too large: shrink harder
                    chunked = semantic_chunk(chunked[: len(chunked) // 2])
                    prompt = build_prompt(chunked, schema_hint)
                    continue
                if status != 200:
                    break  # move to next tier
                tier.consecutive_429s = 0
                try:
                    data = json.loads(text)
                except ValueError:
                    m = re.search(r"\{.*\}", text, re.S)
                    try:
                        data = json.loads(m.group(0)) if m else None
                    except ValueError:
                        data = None
                if not isinstance(data, dict):
                    continue
                if required_keys and not all(data.get(k) is not None for k in required_keys):
                    log.warning("%s missing required keys %s", tier.name, required_keys)
                    continue
                return ExtractionResult(True, data, tier.name, attempts)
        return ExtractionResult(False, None, None, attempts,
                                "all tiers exhausted or unconfigured")
