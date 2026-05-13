import sys
sys.path.insert(0, 'C:/AI_VAULT/tmp_agent')
from brain_v9.agent.tools import build_standard_executor
ex = build_standard_executor()
sigs = ex._TOOL_SIGNATURES
total = len(ex._tools)
covered = sum(1 for t in ex._tools if t in sigs)
print(f'TOOLS={total} SIG_COVERED={covered} COVERAGE={100*covered/total:.1f}%')
# Sample a few previously-missing
for name in ('check_url', 'find_dashboard_files', 'check_port', 'detect_local_network'):
    if name in sigs:
        print(f'  {name}: {sigs[name][:80]}')
