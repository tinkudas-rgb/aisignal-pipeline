"""Re-validate a sample of stored source URLs: every record must trace to a
live URL. Async HEAD with GET fallback, per-host pacing."""
import asyncio, json, random, sys
sys.path.insert(0, '/home/sandbox/aisignal-pipeline')
from src.crawler.base import AsyncCrawler
from src.storage import Store

async def main(sample_per_type=60):
    s = Store()
    report = {}
    async with AsyncCrawler(concurrency=10, per_host_delay=0.2) as c:
        for rtype in ("STARTUP", "PRODUCT", "RESEARCH_PAPER", "JOB", "NEWS"):
            recs = s.records(rtype)
            if not recs:
                report[rtype] = {"total": 0}; continue
            sample = random.sample(recs, min(sample_per_type, len(recs)))
            urls = [r['source']['url'] for r in sample]
            results = await asyncio.gather(*[c.fetch(u) for u in urls])
            ok = sum(1 for r in results if r.ok)
            bad = [(u, r.status) for u, r in zip(urls, results) if not r.ok]
            report[rtype] = {"total": len(recs), "checked": len(sample), "ok": ok, "bad": bad[:10]}
    print(json.dumps(report, indent=1))

asyncio.run(main())
