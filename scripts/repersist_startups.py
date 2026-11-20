import asyncio, logging, sys
sys.path.insert(0, '/home/sandbox/aisignal-pipeline')
logging.basicConfig(level=logging.INFO)
from src.crawler.base import AsyncCrawler
from src.crawler.startups import fetch_startups
from src.pipeline import _persist
from src.resolve.entities import EntityResolver
from src.storage import Store

async def main():
    store = Store()
    async with AsyncCrawler() as c:
        startups = await fetch_startups(c, limit=1500)
    n = _persist(store, EntityResolver(), startups)
    print("startups persisted:", n, "total:", store.count("STARTUP"))

asyncio.run(main())
