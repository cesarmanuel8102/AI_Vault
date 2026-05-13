import sys, asyncio, json
sys.path.insert(0, r"C:\AI_VAULT\tmp_agent\brain_v9")
from agent.tools import search_files

async def main():
    r = await search_files(directory="C:/AI_VAULT/00_identity", pattern="*.py")
    print("KEYS:", list(r.keys()))
    print("returned:", r.get("returned"))
    print("truncated:", r.get("truncated"))
    print("hint:", r.get("hint"))
    for x in r.get("results", [])[:5]:
        print(" ", x)

    print("\n--- pattern='**/*.py' (recursive glob) ---")
    r2 = await search_files(directory="C:/AI_VAULT/00_identity", pattern="**/*.py")
    print("returned:", r2.get("returned"), "truncated:", r2.get("truncated"))
    for x in r2.get("results", [])[:3]:
        print(" ", x)

asyncio.run(main())
