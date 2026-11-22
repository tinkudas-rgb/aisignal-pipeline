# FrontierAtlas - AI Intelligence Ingestion Pipeline

Demo task for The AI Signal (AI Engineer internship): a production-grade,
async ingestion pipeline that acquires, normalizes, resolves and serves
AI-ecosystem intelligence: startups, products, research papers, jobs and news.

## What it does

| Phase | Capability |
|-------|-----------|
| I | Bulk acquisition: 1,000+ startups (YC directory), 1,000+ products (OpenTools.ai), 1,000+ research papers with GitHub repos + star counts (paperswithcode.co API, arXiv supplement) |
| II | High-fidelity signals: 5 AI news feeds + 5 job boards, full-text crawl, strict 24-hour freshness window, cross-run dedupe |
| III | Multi-tier LLM extraction: Gemini Flash -> Groq (Llama 3) -> DeepSeek fallback chain, semantic chunking (no 413s), exponential backoff + full jitter on 429s |
| IV | Deterministic entity resolution against a seed registry of 50 canonical AI companies, with a full mapping log |
| V | Anti-bot strategy: async crawling (asyncio + httpx), per-host pacing, UA rotation, backoff; Cloudflare/JS-rendered sources handled via Playwright (documented in architecture.pdf) |
| VI | `architecture.pdf` - scale, freshness, dedupe and storage design |

Every record carries `schemaVersion`, `recordType`, source provenance and a
collection timestamp, and traces back to a real, live source URL.

## Tech stack

- **Backend**: Python 3.10+, FastAPI, vanilla HTML/JS/CSS single-page UI
- **Crawler**: asyncio + httpx (bounded concurrency, per-host politeness)
- **Storage**: PostgreSQL 16 (JSONB payloads, content-hash dedupe)
- **LLM**: Gemini Flash / Groq / DeepSeek free tiers, deterministic parsers first
- **Tests**: pytest (36 tests)

## Setup

```bash
pip install -r requirements.txt

# 1. PostgreSQL: point AISIGNAL_DSN at any Postgres 14+ database, e.g.
#    export AISIGNAL_DSN="postgresql://user:pass@localhost/aisignal"
#    No server handy? This starts a bundled user-space cluster instead:
python scripts/db_server.py &          # writes data/pg.uri, no root needed

# 2. Run Phase I (bulk acquisition, ~20 min, no API keys needed)
python scripts/run_phase1.py

# 3. Run Phase II (fresh news + jobs, 24h window)
python scripts/run_phase2.py

# 4. Serve the API + UI
uvicorn src.api.main:app --port 8000
# open http://localhost:8000
```

LLM extraction (Phase III) needs one or more free-tier keys as env vars:
`GEMINI_API_KEY`, `GROQ_API_KEY`, `DEEPSEEK_API_KEY`. Without keys the
pipeline still runs: deterministic parsers handle all listed sources, and
`/api/stats` reports which LLM tiers are configured.

## Repo layout

```
src/
  config.py            sources, AI keywords, seed canonical registry
  models.py            canonical pydantic schemas (all 5 verticals)
  storage.py           PostgreSQL store: dedupe, watermarks, entity log
  pipeline.py          phase orchestrator + entity-resolution wiring
  crawler/
    base.py            AsyncCrawler: concurrency, retries, backoff+jitter
    dates.py           date extraction ladder + 24h freshness window
    startups.py        Phase I startups
    products.py        Phase I products
    papers.py          Phase I papers (+ GitHub stars)
    news.py            Phase II news (5 feeds, full text)
    jobs.py            Phase II jobs (5 boards)
  llm/orchestrator.py  Phase III fallback chain + chunking
  resolve/entities.py  Phase IV deterministic resolution
  api/main.py          FastAPI backend + static UI
  api/static/index.html
tests/                 36 tests: dates, entities, chunking, backoff, dedupe, API
scripts/               db server, phase runners, CSV export, URL validator
architecture.pdf       2-page design doc, max 3 allowed (Phase VI)
```

## Data quality guarantees

- **No hallucinated records**: deterministic parsing is the primary path;
  the LLM only ever sees raw page text and is schema-validated, and every
  emitted record keeps its source URL.
- **Freshness**: news/jobs pass a strict 24-hour window using a
  meta-tag -> relative-date -> watermark-heuristic ladder.
- **Dedupe**: SHA-256 content hash over the canonical identity of a record;
  re-runs refresh payloads instead of duplicating rows.
