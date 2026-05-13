import asyncio, sys
sys.path.insert(0, 'C:/AI_VAULT/tmp_agent')
from brain_v9.agent.tools import list_processes

async def run():
    r = await list_processes()
    if not isinstance(r, dict):
        print('FAIL not_dict=' + str(type(r)))
        return False
    needed = ('count', 'returned', 'truncated', 'processes')
    missing = [k for k in needed if k not in r]
    if missing:
        print('FAIL missing_keys=' + str(missing))
        return False
    print('OK count=' + str(r['count']) + ' returned=' + str(r['returned']) + ' truncated=' + str(r['truncated']) + ' hint_present=' + str('hint' in r))
    if r['count'] > 4:
        print('  parser_health=OK (more than 4 procs detected)')
    return True

ok = asyncio.run(run())
sys.exit(0 if ok else 1)
