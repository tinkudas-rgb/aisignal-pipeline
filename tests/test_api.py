import sys
sys.path.insert(0, '/home/sandbox/aisignal-pipeline')
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)


def test_index_served():
    r = client.get("/")
    assert r.status_code == 200 and b"FrontierAtlas" in r.content


def test_stats_shape():
    r = client.get("/api/stats")
    assert r.status_code == 200
    body = r.json()
    assert set(body["counts"]) == {"startups", "products", "papers", "jobs", "news"}
    assert len(body["llm_tiers"]) == 3


def test_records_verticals():
    for kind in ("startups", "products", "papers", "jobs", "news"):
        r = client.get(f"/api/records/{kind}?limit=5")
        assert r.status_code == 200 and "items" in r.json()


def test_unknown_vertical_404():
    assert client.get("/api/records/bogus").status_code == 404


def test_entity_map_endpoint():
    r = client.get("/api/entity-map")
    assert r.status_code == 200 and "items" in r.json()


def test_bad_phase_404():
    assert client.post("/api/run/bogus").status_code == 404
