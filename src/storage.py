"""PostgreSQL storage layer with content-hash dedupe.

PostgreSQL 16 (user-space cluster via pgserver for the demo; any managed
Postgres works by changing AISIGNAL_DSN). The architecture doc covers how
the same schema scales to 500k+ records: table partitioning by
record_type/month, a Redis seen-set in front of the unique index, and
read replicas for the API tier.
"""
from __future__ import annotations

import json
import os
import threading

import psycopg

DEFAULT_DSN = os.environ.get(
    "AISIGNAL_DSN",
    "postgresql://postgres:@/aisignal?host=/home/sandbox/aisignal-pipeline/data/pg")

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    dedupe_hash TEXT PRIMARY KEY,
    record_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    canonical_name TEXT,
    payload JSONB NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_type ON records(record_type);
CREATE INDEX IF NOT EXISTS idx_collected ON records(collected_at DESC);
CREATE TABLE IF NOT EXISTS entity_map (
    raw_name TEXT NOT NULL,
    record_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    match_strategy TEXT NOT NULL,
    confidence REAL NOT NULL,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (raw_name, record_type)
);
CREATE TABLE IF NOT EXISTS run_watermarks (
    source_name TEXT PRIMARY KEY,
    last_run_at TIMESTAMPTZ NOT NULL
);
"""


class Store:
    def __init__(self, dsn: str = DEFAULT_DSN):
        self._lock = threading.Lock()
        self.conn = psycopg.connect(dsn, autocommit=True)
        with self.conn.cursor() as cur:
            cur.execute(SCHEMA)

    def upsert_record(self, dedupe_hash: str, record_type: str, source_name: str,
                      source_url: str, canonical_name: str, payload: dict,
                      collected_at: str) -> bool:
        """Insert or replace; True when the record was new, False when deduped."""
        with self._lock, self.conn.cursor() as cur:
            cur.execute("SELECT 1 FROM records WHERE dedupe_hash=%s", (dedupe_hash,))
            is_new = cur.fetchone() is None
            cur.execute(
                """INSERT INTO records VALUES (%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (dedupe_hash) DO UPDATE
                   SET payload=EXCLUDED.payload, collected_at=EXCLUDED.collected_at,
                       canonical_name=EXCLUDED.canonical_name""",
                (dedupe_hash, record_type, source_name, source_url,
                 canonical_name, json.dumps(payload), collected_at))
        return is_new

    def seen(self, dedupe_hash: str) -> bool:
        with self.conn.cursor() as cur:
            cur.execute("SELECT 1 FROM records WHERE dedupe_hash=%s", (dedupe_hash,))
            return cur.fetchone() is not None

    def records(self, record_type: str, limit: int | None = None) -> list[dict]:
        q = "SELECT payload FROM records WHERE record_type=%s ORDER BY collected_at DESC"
        if limit:
            q += f" LIMIT {int(limit)}"
        with self.conn.cursor() as cur:
            cur.execute(q, (record_type,))
            return [r[0] for r in cur.fetchall()]

    def count(self, record_type: str) -> int:
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM records WHERE record_type=%s",
                        (record_type,))
            return cur.fetchone()[0]

    def counts_by_type(self) -> dict[str, int]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT record_type, COUNT(*) FROM records GROUP BY 1")
            return dict(cur.fetchall())

    def log_mapping(self, raw: str, rtype: str, canonical: str,
                    strategy: str, confidence: float, decided_at: str):
        with self._lock, self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO entity_map VALUES (%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (raw_name, record_type) DO UPDATE
                   SET canonical_name=EXCLUDED.canonical_name,
                       match_strategy=EXCLUDED.match_strategy,
                       confidence=EXCLUDED.confidence,
                       decided_at=EXCLUDED.decided_at""",
                (raw, rtype, canonical, strategy, confidence, decided_at))

    def mappings(self) -> list[tuple]:
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT raw_name, canonical_name, record_type, match_strategy,
                          confidence, decided_at::text
                   FROM entity_map ORDER BY decided_at DESC""")
            return cur.fetchall()

    def set_watermark(self, source: str, iso_ts: str):
        with self._lock, self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO run_watermarks VALUES (%s,%s)
                   ON CONFLICT (source_name) DO UPDATE
                   SET last_run_at=EXCLUDED.last_run_at""", (source, iso_ts))

    def get_watermark(self, source: str) -> str | None:
        with self.conn.cursor() as cur:
            cur.execute("SELECT last_run_at::text FROM run_watermarks WHERE source_name=%s",
                        (source,))
            row = cur.fetchone()
            return row[0] if row else None

    def close(self):
        self.conn.close()
