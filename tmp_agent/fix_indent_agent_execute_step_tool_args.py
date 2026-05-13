from pathlib import Path
import re

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
lines = p.read_text(encoding="utf-8").splitlines(True)

# Find the bad line: "tool_args = step.get("tool_args") or {}" with too much indent
fixed1 = 0
for i, ln in enumerate(lines):
    if "tool_args = step.get(\"tool_args\") or {}" in ln:
        # Set indent to exactly 4 spaces (same level as tool_name assignment)
        lines[i] = "    tool_args = step.get(\"tool_args\") or {}\n"
        fixed1 = 1
        break

if not fixed1:
    raise SystemExit("No encontré la línea tool_args = step.get(... ) para corregir.")

# Fix the indentation for "tool_args=dict(tool_args)," inside AgentExecuteRequest(...)
fixed2 = 0
for i, ln in enumerate(lines):
    if re.search(r"^\s*tool_args\s*=\s*dict\(tool_args\)\s*,\s*$", ln):
        # Set indent to 8 spaces (aligned with other args inside AgentExecuteRequest call)
        lines[i] = "        tool_args=dict(tool_args),\n"
        fixed2 = 1
        break

if not fixed2:
    raise SystemExit("No encontré la línea tool_args=dict(tool_args), para corregir indentación.")

p.write_text("".join(lines), encoding="utf-8")
print("OK: fixed indentation in agent_execute_step for tool_args and exec_req.tool_args")
