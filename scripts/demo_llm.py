"""Small live demo of the Phase III LLM fallback chain (Gemini tier)."""
import asyncio, json, sys
sys.path.insert(0, '/home/sandbox/aisignal-pipeline')
from src.llm.orchestrator import LLMOrchestrator
from src.storage import Store

SAMPLES = [
    ("product", "{productName, startupName, description, pricingModel, categories[]}"),
    ("news", "{headline, published_date, summary, companies_mentioned[]}"),
]

async def main():
    s = Store()
    orch = LLMOrchestrator()
    print("tier status before:", json.dumps(orch.status()))
    prod = s.records("PRODUCT")[0]["content"]
    news = s.records("NEWS")[0]["content"]
    texts = {
        "product": json.dumps(prod, indent=2)[:3000],
        "news": (news.get("full_text") or news.get("summary") or "")[:3000],
    }
    for kind, hint in SAMPLES:
        r = await orch.extract(texts[kind], hint)
        print(f"--- {kind}: tier_used={r.provider} attempts={r.attempts}")
        print(json.dumps(r.data, indent=1)[:500])
    print("tier status after:", json.dumps(orch.status()))

asyncio.run(main())
