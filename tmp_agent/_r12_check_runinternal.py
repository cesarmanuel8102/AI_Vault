import asyncio, sys
sys.path.insert(0, 'C:/AI_VAULT/tmp_agent')
from brain_v9.agent.tools import _run_internal_command

async def run():
    r = await _run_internal_command('powershell -Command "Start-Sleep 10"', timeout=2)
    if r.get('error_type') == 'TimeoutExpired':
        print('OK timeout_surfaced error_type=' + r['error_type'])
        return True
    print('FAIL r=' + str(r)[:200])
    return False

ok = asyncio.run(run())
sys.exit(0 if ok else 1)
