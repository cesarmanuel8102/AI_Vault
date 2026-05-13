import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

# We want to redirect mission_log.txt writes from tmp_agent\\runs\\<room> to repo-safe _agent_runs\\<room>
# Match within the planner hard steps block (S1 tool_args path contains mission_log.txt)
# Replace any occurrence of:
#   C:\\AI_VAULT\\tmp_agent\\runs\\ ... \\mission_log.txt
# with:
#   C:\\AI_VAULT\\workspace\\brainlab\\_agent_runs\\ ... \\mission_log.txt

pat = r'C:\\\\AI_VAULT\\\\tmp_agent\\\\runs\\\\([^\\"]+)\\\\mission_log\.txt'
rep = r'C:\\\\AI_VAULT\\\\workspace\\\\brainlab\\\\_agent_runs\\\\\1\\\\mission_log.txt'

txt2, n = re.subn(pat, rep, txt, count=10)
if n == 0:
    # fallback: raw-string concatenation forms
    pat2 = r'tmp_agent\\\\runs\\\\["\']?\s*\+\s*str\(room_id\)\s*\+\s*r?["\']\\\\mission_log\.txt'
    rep2 = r'workspace\\\\brainlab\\\\_agent_runs\\\\' + '" + str(room_id) + r"\\\\mission_log.txt'
    txt2, n = re.subn(pat2, rep2, txt, count=5)

if n == 0:
    raise SystemExit("No encontré el path de mission_log.txt del plan HARD para redirigir.")

p.write_text(txt2, encoding="utf-8")
print(f"OK: redirected mission_log.txt to _agent_runs (replacements={n})")
