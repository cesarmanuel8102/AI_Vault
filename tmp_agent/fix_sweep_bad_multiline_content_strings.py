import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

# Fix any content strings that became multiline, specifically START markers.
# Replace: "content": "MISSION START<newline>..."
txt2 = txt

# 1) mission start
txt2, n1 = re.subn(
    r'("content"\s*:\s*)("MISSION START)(\r?\n)([^"]*)(")',
    r'\1"MISSION START\\n"',
    txt2,
    count=5
)

# 2) real v2 start
txt2, n2 = re.subn(
    r'("content"\s*:\s*)("REAL_V2 START)(\r?\n)([^"]*)(")',
    r'\1"REAL_V2 START\\n"',
    txt2,
    count=5
)

# 3) f-strings variants that got broken
txt2, n3 = re.subn(
    r'("content"\s*:\s*)f"MISSION START[\s\S]*?"\s*,',
    r'\1"MISSION START\\n",',
    txt2,
    count=2
)
txt2, n4 = re.subn(
    r'("content"\s*:\s*)f"REAL_V2 START[\s\S]*?"\s*,',
    r'\1"REAL_V2 START\\n",',
    txt2,
    count=2
)

if txt2 != txt:
    p.write_text(txt2, encoding="utf-8")
    print(f"OK: swept multiline content strings (n1={n1}, n2={n2}, n3={n3}, n4={n4})")
else:
    print("SKIP: no multiline content strings matched")
