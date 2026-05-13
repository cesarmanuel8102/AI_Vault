import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
lines = p.read_text(encoding="utf-8").splitlines(True)

# locate def agent_execute_step (FastAPI endpoint handler)
i_def = None
for i, ln in enumerate(lines):
    if re.match(r"\s*def\s+agent_execute_step\s*\(", ln):
        i_def = i
        break
if i_def is None:
    raise SystemExit("No encuentro def agent_execute_step(...)")

def_indent = re.match(r"(\s*)def\s+agent_execute_step", lines[i_def]).group(1)

# function ends at next decorator at same indent or EOF
i_end = None
for j in range(i_def + 1, len(lines)):
    if lines[j].startswith(def_indent + "@app."):
        i_end = j
        break
if i_end is None:
    i_end = len(lines)

chunk = lines[i_def:i_end]

# Remove any lines/blocks related to snapshot tool execution inside execute_step.
# (Snapshot execution belongs to agent_execute, not execute_step)
bad_markers = (
    "runtime_snapshot_set",
    "runtime_snapshot_get",
    "_runtime_snapshot_set_kv",
    "_runtime_snapshot_get_kv",
    "EXECUTE_STEP_SNAPSHOT_KV_DISPATCH_V1",
    "Handle runtime_snapshot_set/get",
)

new_chunk = []
for ln in chunk:
    if any(m in ln for m in bad_markers):
        continue
    new_chunk.append(ln)

# Extra safety: remove orphaned 'if' lines that mention runtime_snapshot (just in case)
new_chunk2 = []
for ln in new_chunk:
    if re.search(r"^\s*if\s+tool_name\s+in\s*\(.*runtime_snapshot", ln):
        continue
    new_chunk2.append(ln)

lines2 = lines[:i_def] + new_chunk2 + lines[i_end:]
p.write_text("".join(lines2), encoding="utf-8")
print("OK: cleaned runtime_snapshot leftovers from agent_execute_step")
