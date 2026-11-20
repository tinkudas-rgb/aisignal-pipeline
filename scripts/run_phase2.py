import asyncio, json, logging, sys
sys.path.insert(0, '/home/sandbox/aisignal-pipeline')
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
from src.pipeline import run_phase
from src.storage import Store

async def main():
    store = Store()
    summary = await run_phase('phase2', store)
    print("PHASE2 SUMMARY:", json.dumps(summary))
    print("DB counts:", store.counts_by_type())

asyncio.run(main())
