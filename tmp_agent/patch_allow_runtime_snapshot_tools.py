import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")
lines = txt.splitlines(True)

# locate agent_execute_step def region
i_def = None
for i, ln in enumerate(lines):
    if re.match(r"\s*def\s+agent_execute_step\s*\(", ln):
        i_def = i
        break
if i_def is None:
    raise SystemExit("No encuentro def agent_execute_step(...)")

# find end at next @app. decorator at same indent
def_indent = re.match(r"(\s*)def\s+agent_execute_step", lines[i_def]).group(1)
i_end = None
for j in range(i_def+1, len(lines)):
    if lines[j].startswith(def_indent + "@app."):
        i_end = j
        break
if i_end is None:
    i_end = len(lines)

chunk = lines[i_def:i_end]
chunk_txt = "".join(chunk)

MARK = "ALLOW_RUNTIME_SNAPSHOT_TOOLS_V1"
if MARK in chunk_txt:
    print("SKIP: allow runtime snapshot already patched")
    raise SystemExit(0)

# find the deny line containing "tool_name not allowed:"
i_deny = None
for k, ln in enumerate(chunk):
    if "tool_name not allowed:" in ln:
        i_deny = k
        break
if i_deny is None:
    raise SystemExit("No encuentro 'tool_name not allowed:' dentro de agent_execute_step")

# We want to insert just BEFORE the line that raises/returns the deny.
# Detect indent of the deny line
indent = re.match(r"(\s*)", chunk[i_deny]).group(1)

block = []
block.append(f"{indent}# === {MARK} BEGIN ===\n")
block.append(f"{indent}# Allow runtime snapshot tools as non-gated read-like operations\n")
block.append(f"{indent}if tool_name in ('runtime_snapshot_set','runtime_snapshot_get'):\n")
block.append(f"{indent}    # bypass deny-list / allowlist gate\n")
block.append(f"{indent}    pass\n")
block.append(f"{indent}# === {MARK} END ===\n")

new_chunk = chunk[:i_deny] + block + chunk[i_deny:]
new_lines = lines[:i_def] + new_chunk + lines[i_end:]
p.write_text("".join(new_lines), encoding="utf-8")
print(f"OK: inserted allow runtime_snapshot_* bypass before deny at execute_step (line ~{i_def+i_deny+1})")
