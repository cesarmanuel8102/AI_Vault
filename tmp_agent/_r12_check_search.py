import asyncio, sys
sys.path.insert(0, 'C:/AI_VAULT/tmp_agent')
from brain_v9.agent.tools import search_files

async def run():
    r = await search_files(directory='C:/AI_VAULT/tmp_agent/brain_v9/agent', pattern='*.py')
    if not isinstance(r, dict):
        print('FAIL not_dict=' + str(type(r)))
        return False
    needed = ('results', 'returned', 'truncated', 'success')
    missing = [k for k in needed if k not in r]
    if missing:
        print('FAIL missing_keys=' + str(missing))
        return False
    print('OK returned=' + str(r['returned']) + ' truncated=' + str(r['truncated']) + ' success=' + str(r['success']))
    return True

ok = asyncio.run(run())
sys.exit(0 if ok else 1)
