import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

# 1) Add mode field to AgentPlanRequest (if missing)
if "class AgentPlanRequest" not in txt:
    raise SystemExit("No encuentro class AgentPlanRequest")

if "mode:" not in re.search(r"class\s+AgentPlanRequest\s*\(BaseModel\):([\s\S]*?)(\nclass|\n@app\.post|\Z)", txt).group(1):
    txt = re.sub(
        r"(class\s+AgentPlanRequest\s*\(BaseModel\):\s*\n)",
        r"\1    mode: str = Field('smoke', description='smoke|real')\n",
        txt,
        count=1
    )

# 2) Patch agent_plan to branch by req.mode (default smoke)
m = re.search(r'@app\.post\("/v1/agent/plan".*?\)\s*\ndef\s+agent_plan\s*\(.*?\):\n', txt, flags=re.DOTALL)
if not m:
    raise SystemExit("No encuentro endpoint /v1/agent/plan")

start = m.end()
tail = txt[start:]
m2 = re.search(r"\n@app\.", tail)
end = (start + m2.start()) if m2 else len(txt)
block = txt[m.start():end]

MARK = "PLAN_MODE_SMOKE_REAL_V1"
if MARK in block:
    p.write_text(txt, encoding="utf-8")
    print("SKIP: plan mode patch already present")
    raise SystemExit(0)

# Find where plan["steps"] is assigned (we will wrap smoke branch)
ms = re.search(r'plan\["steps"\]\s*=\s*\[\s*\n', block)
if not ms:
    raise SystemExit('No encuentro plan["steps"] = [ dentro de agent_plan')

# Determine indent for plan assignment line
lines = block.splitlines(True)
idx_steps = None
for i, ln in enumerate(lines):
    if 'plan["steps"]' in ln and "=" in ln:
        idx_steps = i
        break
if idx_steps is None:
    raise SystemExit("No encuentro línea plan['steps']")

indent = re.match(r"(\s*)", lines[idx_steps]).group(1)

# Replace the existing plan["steps"]=... block with:
# if req.mode == 'real': read-only steps; else: existing smoke steps block (we keep existing by capturing old)
# We capture from plan["steps"]= [ ... ] up to the closing ] just before agent_store.save_plan(plan)
pat_steps = r'plan\["steps"\]\s*=\s*\[(?s:.*?)\n\s*\]\s*\n(?=\s*agent_store\.save_plan\(plan\))'
msteps = re.search(pat_steps, block)
if not msteps:
    raise SystemExit("No pude capturar bloque plan['steps'] antes de save_plan(plan)")

old_steps = msteps.group(0)

real_steps = (
    'plan["steps"] = [\n'
    '            {\n'
    '                "id": "S1",\n'
    '                "title": "Inspect risk folder (list_dir)",\n'
    '                "status": "todo",\n'
    '                "tool_name": "list_dir",\n'
    '                "mode": "propose",\n'
    '                "kind": "new_file",\n'
    '                "tool_args": {"path": "C:\\\\AI_VAULT\\\\workspace\\\\brainlab\\\\brainlab\\\\risk"}\n'
    '            },\n'
    '            {\n'
    '                "id": "S2",\n'
    '                "title": "Read risk_engine.py (read_file)",\n'
    '                "status": "todo",\n'
    '                "tool_name": "read_file",\n'
    '                "mode": "propose",\n'
    '                "kind": "new_file",\n'
    '                "tool_args": {"path": "C:\\\\AI_VAULT\\\\workspace\\\\brainlab\\\\brainlab\\\\risk\\\\risk_engine.py", "max_bytes": 200000}\n'
    '            }\n'
    '        ]\n'
)

branch = []
branch.append(f"{indent}# === {MARK} BEGIN ===\n")
branch.append(f"{indent}mode = (getattr(req, 'mode', None) or 'smoke').strip().lower()\n")
branch.append(f"{indent}if mode == 'real':\n")
branch.append(indent + "    " + real_steps.replace("\n", "\n" + indent + "    ").rstrip() + "\n")
branch.append(f"{indent}else:\n")
# keep old smoke steps, indented one level deeper
old_indented = old_steps.replace("\n", "\n" + indent + "    ")
branch.append(indent + "    " + old_indented.rstrip() + "\n")
branch.append(f"{indent}# === {MARK} END ===\n")

new_block = re.sub(pat_steps, "".join(branch), block, count=1)
txt2 = txt[:m.start()] + new_block + txt[end:]

p.write_text(txt2, encoding="utf-8")
print("OK: agent_plan now supports req.mode smoke|real (real=read-only steps, smoke=existing minimal mission)")
