import asyncio, json, sys
sys.path.insert(0, r'C:\AI_VAULT_CANONICAL\tmp_agent')
from brain_v9.core.router_entrypoint import handle_user_message
result = asyncio.run(handle_user_message(
    'dry run verification of canonical router entrypoint',
    room='front_safe_restart_direct_dry_run',
    dry_run=True
))
print(json.dumps(result, ensure_ascii=False, indent=2))
