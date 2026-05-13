import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

# Find the agent_run endpoint
m = re.search(r'@app\.post\("/v1/agent/run".*?\)\s*\ndef\s+agent_run\s*\(.*?\):\n', txt, flags=re.DOTALL)
if not m:
    raise SystemExit('No encuentro el decorador/def de /v1/agent/run')

start = m.start()
# Find end of function by next top-level decorator or EOF
tail = txt[m.end():]
m2 = re.search(r'\n@app\.', tail)
end = (m.end() + m2.start()) if m2 else len(txt)

old_block = txt[start:end]

# Build replacement: preserve signature line (we re-capture it)
sig = re.search(r'def\s+agent_run\s*\(.*?\):\n', old_block)
if not sig:
    raise SystemExit("No pude extraer la firma de agent_run")
sig_line = sig.group(0)

indent = "    "

new_func = []
new_func.append(old_block.splitlines(True)[0])  # decorator line
new_func.append(sig_line)
new_func.append(f"{indent}# v6.2: run loop MUST respect per-room plan.json and stop if complete\n")
new_func.append(f"{indent}try:\n")
new_func.append(f'{indent}    hdr_room = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or None\n')
new_func.append(f"{indent}except Exception:\n")
new_func.append(f"{indent}    hdr_room = None\n")
new_func.append(f"{indent}room_id = getattr(req, 'room_id', None) or hdr_room or \"default\"\n")
new_func.append(f"{indent}max_steps = int(getattr(req, 'max_steps', 10) or 10)\n")
new_func.append(f"{indent}if max_steps < 1: max_steps = 1\n")
new_func.append(f"{indent}if max_steps > 200: max_steps = 200\n")
new_func.append("\n")
new_func.append(f"{indent}# Always read per-room status first (via agent_status which loads from disk)\n")
new_func.append(f"{indent}st0 = agent_status(AgentStatusRequest(room_id=room_id), request)\n")
new_func.append(f"{indent}plan0 = (st0.get('plan') or {{}})\n")
new_func.append(f"{indent}mission0 = (st0.get('mission') or {{}})\n")
new_func.append(f"{indent}summary0 = (st0.get('summary') or {{}})\n")
new_func.append(f"{indent}pending0 = (st0.get('pending_approvals') or {{}})\n")
new_func.append("\n")
new_func.append(f"{indent}if str(plan0.get('status','')).lower() == 'complete':\n")
new_func.append(f"{indent}    return {{\n")
new_func.append(f"{indent}        'ok': True,\n")
new_func.append(f"{indent}        'room_id': room_id,\n")
new_func.append(f"{indent}        'executed': [],\n")
new_func.append(f"{indent}        'needs_approval': False,\n")
new_func.append(f"{indent}        'approve_token': None,\n")
new_func.append(f"{indent}        'summary': summary0,\n")
new_func.append(f"{indent}        'pending_approvals': pending0,\n")
new_func.append(f"{indent}        'plan': plan0,\n")
new_func.append(f"{indent}        'mission': mission0,\n")
new_func.append(f"{indent}    }}\n")
new_func.append("\n")
new_func.append(f"{indent}executed = []\n")
new_func.append(f"{indent}needs_approval = False\n")
new_func.append(f"{indent}approve_token = None\n")
new_func.append("\n")
new_func.append(f"{indent}for _i in range(max_steps):\n")
new_func.append(f"{indent}    r = agent_run_once(AgentRunOnceRequest(room_id=room_id), request)\n")
new_func.append(f"{indent}    executed.append({{'action': r.get('action'), 'step_id': r.get('step_id')}})\n")
new_func.append(f"{indent}    if bool(r.get('needs_approval', False)):\n")
new_func.append(f"{indent}        needs_approval = True\n")
new_func.append(f"{indent}        approve_token = r.get('approve_token')\n")
new_func.append(f"{indent}        break\n")
new_func.append(f"{indent}    if str(r.get('action') or '') == 'noop_complete':\n")
new_func.append(f"{indent}        break\n")
new_func.append(f"{indent}    if str(r.get('action') or '') in ('noop_no_todo','evaluate_sweep'):\n")
new_func.append(f"{indent}        break\n")
new_func.append("\n")
new_func.append(f"{indent}# Recompute status from disk at end\n")
new_func.append(f"{indent}st = agent_status(AgentStatusRequest(room_id=room_id), request)\n")
new_func.append(f"{indent}return {{\n")
new_func.append(f"{indent}    'ok': True,\n")
new_func.append(f"{indent}    'room_id': room_id,\n")
new_func.append(f"{indent}    'executed': executed,\n")
new_func.append(f"{indent}    'needs_approval': needs_approval,\n")
new_func.append(f"{indent}    'approve_token': approve_token,\n")
new_func.append(f"{indent}    'summary': st.get('summary') or {{}},\n")
new_func.append(f"{indent}    'pending_approvals': st.get('pending_approvals') or {{}},\n")
new_func.append(f"{indent}    'plan': st.get('plan') or {{}},\n")
new_func.append(f"{indent}    'mission': st.get('mission') or {{}},\n")
new_func.append(f"{indent}}}\n")

new_block = "".join(new_func)
txt2 = txt[:start] + new_block + txt[end:]
p.write_text(txt2, encoding="utf-8")
print("OK: /v1/agent/run patched to respect per-room complete status")
