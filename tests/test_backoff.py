import asyncio
import sys
sys.path.insert(0, '/home/sandbox/aisignal-pipeline')
from src.crawler.base import backoff_delay, content_hash
from src.llm.orchestrator import ExtractionResult, LLMOrchestrator, LLMTier


def test_backoff_bounds_and_jitter():
    for attempt in range(6):
        d = backoff_delay(attempt, base=1.0, cap=60)
        assert 0 <= d <= min(60, 2 ** attempt)


def test_backoff_cap():
    assert backoff_delay(20, cap=60) <= 60


def test_hash_stability_and_normalization():
    assert content_hash("a", "B") == content_hash("a", "B")
    assert content_hash("a", " b ") == content_hash("a", "B")
    assert content_hash("a", "b") != content_hash("a", "c")


class Fake429Tier(LLMTier):
    name = "always-429"

    def __init__(self):
        super().__init__(api_key="fake")
        self.calls = 0

    async def complete(self, prompt):
        self.calls += 1
        return 429, "rate limited"


class FakeOKTier(LLMTier):
    name = "ok"

    def __init__(self):
        super().__init__(api_key="fake")

    async def complete(self, prompt):
        return 200, '{"title": "Hello", "company": "Acme"}'


def test_fallback_chain_moves_past_429(monkeypatch):
    async def no_sleep(_):
        return None
    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    orch = LLMOrchestrator(tiers=[Fake429Tier(), FakeOKTier()])
    result = asyncio.run(orch.extract("page text", '{"title": str}',
                                      required_keys=["title"]))
    assert result.ok and result.provider == "ok" and result.data["title"] == "Hello"


def test_unconfigured_tiers_fail_clean():
    orch = LLMOrchestrator(tiers=[])  # no keys anywhere
    orch.tiers = [t for t in [Fake429Tier()]]
    orch.tiers[0].api_key = None
    result = asyncio.run(orch.extract("text", "{}"))
    assert not result.ok
