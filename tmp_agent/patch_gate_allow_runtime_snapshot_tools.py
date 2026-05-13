import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
lines = p.read_text(encoding="utf-8").splitlines(True)

MARK = "GATE_ALLOW_RUNTIME_SNAPSHOT_TOOLS_V1"
if any(MARK in ln for ln in lines):
    print("SKIP: gate allow runtime_snapshot already patched")
    raise SystemExit(0)

# Find the exact raise line (tool_name not allowed)
idx = None
for i, ln in enumerate(lines):
    if 'detail=f"tool_name not allowed: {tool_name}"' in ln:
        idx = i
        break

if idx is None:
    raise SystemExit("No encuentro la línea raise HTTPException(... tool_name not allowed ...)")

indent = re.match(r"(\s*)", lines[idx]).group(1)

block = []
block.append(f"{indent}# === {MARK} BEGIN ===\n")
block.append(f"{indent}# Allow runtime snapshot tools (room-scoped KV) through the tool gate\n")
block.append(f"{indent}if tool_name in ('runtime_snapshot_set','runtime_snapshot_get'):\n")
block.append(f"{indent}    pass\n")
block.append(f"{indent}else:\n")
block.append(f"{indent}    raise HTTPException(status_code=400, detail=f\"tool_name not allowed: {tool_name}\")\n")
block.append(f"{indent}# === {MARK} END ===\n")

# Replace the single raise line with our guarded block
lines[idx:idx+1] = block

p.write_text("".join(lines), encoding="utf-8")
print(f"OK: patched gate allowlist for runtime_snapshot_* at line {idx+1}")
