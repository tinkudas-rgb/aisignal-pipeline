import sys
sys.path.insert(0, '/home/sandbox/aisignal-pipeline')
from src.storage import Store


def make_store(tmp_path):
    return Store()


def test_upsert_dedupes():
    s = Store()
    try:
        assert s.upsert_record("x1", "JOB", "B", "https://j/1", "Acme", {"a": 1},
                               "2026-11-20T00:00:00Z") is True
        assert s.upsert_record("x1", "JOB", "B", "https://j/1", "Acme", {"a": 2},
                               "2026-11-20T01:00:00Z") is False
        with s.conn.cursor() as cur:
            cur.execute("SELECT payload->>'a' FROM records WHERE dedupe_hash='x1'")
            assert cur.fetchone()[0] == "2"  # payload refreshed
    finally:
        with s.conn.cursor() as cur:
            cur.execute("DELETE FROM records WHERE dedupe_hash LIKE 'x%'")
        s.close()


def test_watermark_roundtrip():
    s = Store()
    try:
        assert s.get_watermark("nope") is None
        s.set_watermark("src", "2026-11-20T00:00:00Z")
        assert s.get_watermark("src") is not None
    finally:
        with s.conn.cursor() as cur:
            cur.execute("DELETE FROM run_watermarks WHERE source_name='src'")
        s.close()
