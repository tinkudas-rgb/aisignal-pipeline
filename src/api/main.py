"""FastAPI backend: pipeline control + record browsing + the single-page UI.

Endpoints
  GET  /                      -> single-page UI (plain HTML/vanilla JS/CSS)
  GET  /api/stats             -> record counts per vertical + LLM tier status
  GET  /api/records/{kind}    -> paginated records (?q= filters by name/title)
  GET  /api/entity-map        -> entity resolution log
  POST /api/run/{phase}       -> trigger a pipeline phase (async background)
  GET  /api/runs              -> recent run status
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from ..llm.orchestrator import LLMOrchestrator
from ..pipeline import run_phase
from ..storage import Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

STATIC = Path(__file__).parent / "static"
KINDS = {"startups": "STARTUP", "products": "PRODUCT", "papers": "RESEARCH_PAPER",
         "jobs": "JOB", "news": "NEWS"}

app = FastAPI(title="FrontierAtlas Intelligence Pipeline", version="1.0")
store = Store()
orchestrator = LLMOrchestrator()
RUNS: list[dict] = []


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/stats")
def stats():
    counts = store.counts_by_type()
    return {
        "counts": {k: counts.get(v, 0) for k, v in KINDS.items()},
        "entity_mappings": len(store.mappings()),
        "llm_tiers": orchestrator.status(),
        "runs": RUNS[-10:],
    }


@app.get("/api/records/{kind}")
def records(kind: str, q: str = Query("", max_length=120),
            limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    if kind not in KINDS:
        raise HTTPException(404, f"unknown vertical {kind!r}")
    items = store.records(KINDS[kind])
    if q:
        ql = q.lower()
        items = [r for r in items if ql in str(r.get("content", {})).lower()]
    return {"total": len(items), "offset": offset,
            "items": items[offset:offset + limit]}


@app.get("/api/entity-map")
def entity_map(limit: int = Query(200, ge=1, le=2000)):
    rows = store.mappings()[:limit]
    return {"total": len(store.mappings()),
            "items": [{"raw": r[0], "canonical": r[1], "record_type": r[2],
                       "strategy": r[3], "confidence": r[4], "decided_at": r[5]}
                      for r in rows]}


@app.post("/api/run/{phase}")
async def run(phase: str, background: BackgroundTasks):
    if phase not in ("phase1", "phase2", "all"):
        raise HTTPException(404, f"unknown phase {phase!r}")
    run_id = len(RUNS) + 1
    RUNS.append({"id": run_id, "phase": phase, "status": "running",
                 "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})

    async def go():
        try:
            summary = await run_phase(phase, store)
            RUNS[-1].update(status="done", summary=summary)
        except Exception as e:  # surfaced in /api/runs
            RUNS[-1].update(status="failed", error=str(e))

    background.add_task(asyncio.get_event_loop().create_task, go())
    return {"run_id": run_id, "status": "running"}


@app.get("/api/runs")
def runs():
    return {"runs": RUNS[-20:]}
