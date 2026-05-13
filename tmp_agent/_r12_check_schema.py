import asyncio, sys
sys.path.insert(0, 'C:/AI_VAULT/tmp_agent')
from brain_v9.agent.tools import build_standard_executor
ex = build_standard_executor()

async def run():
    r = await ex.execute('search_files', directory='C:/AI_VAULT')
    if isinstance(r, dict) and r.get('error_type') == 'missing_args':
        print('OK_MISSING missing=' + str(r.get('missing')))
        print('  hint=' + str(r.get('hint',''))[:120])
        return True
    print('FAIL got=' + str(r)[:200])
    return False

ok = asyncio.run(run())
sys.exit(0 if ok else 1)
