from pathlib import Path
import re

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")
lines = txt.splitlines(True)

# We'll fix the specific block by pattern, only once.
# Target: after "content = str(rf.get("content", "") or "")"
# Current broken indentation starts with 12 spaces before "# === PLAN_REFRESH..."
pat = (
    r'(content\s*=\s*str\(rf\.get\("content",\s*""\)\s*or\s*""\)\s*)\n'
    r'(\s{12}# === PLAN_REFRESH ROOM-SAFE \(FIX\): strip any PLANNER_PLACEHOLDER lines to avoid refresh loop ===\n'
    r'\s{12}try:\n'
    r'\s{16}_ls = content\.splitlines\(True\)\n'
    r'\s{16}_ls = \[ln for ln in _ls if \'PLANNER_PLACEHOLDER\' not in ln\]\n'
    r'\s{16}content = \'\'.join\(_ls\)\n'
    r'\s{12}except Exception:\n'
    r'\s{16}pass\n)'
)

m = re.search(pat, txt)
if not m:
    raise SystemExit("No encontré el bloque roto de strip PLANNER_PLACEHOLDER (pattern mismatch).")

# Rebuild with correct indentation (8 spaces)
fixed = (
    m.group(1) + "\n"
    "        # === PLAN_REFRESH ROOM-SAFE (FIX): strip any PLANNER_PLACEHOLDER lines to avoid refresh loop ===\n"
    "        try:\n"
    "            _ls = content.splitlines(True)\n"
    "            _ls = [ln for ln in _ls if 'PLANNER_PLACEHOLDER' not in ln]\n"
    "            content = ''.join(_ls)\n"
    "        except Exception:\n"
    "            pass\n"
)

txt2 = txt[:m.start()] + fixed + txt[m.end():]
p.write_text(txt2, encoding="utf-8")
print("OK: fixed indentation of PLANNER_PLACEHOLDER strip block in agent_plan_refresh")
