# FrontierAtlas Ingestion Pipeline - Architecture

**Scope.** This document covers the design of the AI-intelligence ingestion
pipeline: bulk acquisition, fresh-signal monitoring, LLM extraction,
entity resolution, and how each scales from the demo target (3k records)
to the production target (500k+ records).

## 1. System overview

```
sources (APIs, RSS, HTML) --> AsyncCrawler --> deterministic parsers
                                    |                  |
                                    |            (fallback)
                                    |                  v
                                    |        LLM Orchestrator
                                    |     Gemini -> Groq -> DeepSeek
                                    v                  v
                              Entity Resolver --> PostgreSQL (canonical JSONB)
                                                         |
                                          FastAPI + UI / Google Sheets export
```

The guiding rule: **deterministic first, LLM second.** Structured sources
(APIs, feeds, embedded JSON) are parsed with code, not prompts. The LLM
tier only handles pages whose structure defeats the parser, which keeps
cost near zero, throughput high, and removes hallucination surface for
the bulk of records. Every record keeps `source.url` for auditability.

## 2. Scale strategy: 500k+ records

The same code scales to 500k+ by scaling infrastructure, not code:

- **Work unit = one URL.** Crawlers consume URL queues; acquisition is
  embarrassingly parallel. For 500k records we shard source lists across
  N worker nodes (Redis/Kafka queue), each running the same AsyncCrawler.
- **Bounded concurrency per node** (semaphore + per-host pacing) makes a
  node's footprint predictable; adding nodes adds linear throughput.
- **Backpressure**: workers acknowledge a URL only after persistence;
  failed URLs requeue with capped retries, then land in a dead-letter
  table for review.
- **Idempotent persistence**: `dedupe_hash` primary key + upsert means a
  record can be safely written twice - crashes and requeues are harmless.

## 3. Rate limits (429) and payload size (413)

**429s.** Three layers: (1) per-host pacing prevents most limit hits;
(2) retries use exponential backoff with *full jitter*
(`random(0, min(cap, base*2^attempt))`) so concurrent workers don't retry
in lockstep; (3) the LLM chain treats a provider that 429s repeatedly as
*cooling down* (5 min circuit breaker) and falls through to the next
provider - Gemini Flash -> Groq Llama 3 -> DeepSeek.

**413s / context windows.** Payloads are budgeted *before* the call using
a chars/4 token estimate. `semantic_chunk()` drops boilerplate lines
(cookies, newsletters, nav), keeps the document head (where titles, lead
paragraphs and metadata live) and fills the remainder with
information-dense tail content, marking the elision. If a provider still
returns 413, the payload is halved and retried. We never learn about an
oversized payload from the provider twice.

## 4. Freshness and dedupe across distributed nodes

**Freshness.** Dates are extracted by a confidence ladder:
feed timestamp / `article:published_time` / JSON-LD `datePublished`
(high) -> relative expressions like "2 hours ago" (medium) -> last-run
watermark heuristic (a URL new to a source we poll is treated as new only
if the source ran before). Only items inside a strict 24-hour window are
kept; anything unverifiable on a first run is dropped rather than risk
staleness.

**Dedupe.** Each record's identity is a SHA-256 hash of its canonical
identity (type + source URL / arXiv id / slug). At demo scale it is the
Postgres primary key. At 500k+ scale a Redis SETNX seen-set sits in front
of the database so distributed nodes never process the same item twice;
the Postgres unique constraint remains the final arbiter.

## 5. Storage strategy

- **Primary: PostgreSQL.** JSONB payloads give schema-versioned canonical
  records with relational integrity, `GIN` indexes for JSON queries, and
  `pgvector` for embeddings - one system instead of two. At scale:
  partition `records` by `record_type` and month; read replicas serve the
  API tier.
- **Vector/graph**: `pgvector` (or Qdrant when ANN latency budgets demand
  it) for semantic similarity over titles/abstracts; Neo4j for the entity
  relationship graph (startup -> product -> paper -> repo) once
  traversal-heavy queries justify a dedicated graph store.
- **Entity resolution** is deterministic (exact -> normalized -> alias ->
  token-Jaccard fuzzy) against a seed registry; every decision lands in
  the Entity Mapping Log with strategy + confidence for audit.

## 6. Anti-bot and JS-rendered sources

Tiered escalation: (1) plain async HTTP with browser-grade headers, UA
rotation and per-host pacing; (2) Playwright Async for JS-rendered pages,
with shared browser contexts and request interception to block
images/media (3-5x cheaper); (3) for Cloudflare/Datadome fronts, real
browser profiles with persistent cookies, human-like pacing and
residential-proxy rotation - never hammering a protected endpoint.
CAPTCHAs are treated as a stop signal, not a challenge to brute force:
the source is cooled down and retried later or through an official API.
