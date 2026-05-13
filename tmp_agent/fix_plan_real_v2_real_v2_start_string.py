import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

BEGIN = "# === PLAN_REAL_ENDPOINT_V2_GATED_V1 BEGIN ==="
END   = "# === PLAN_REAL_ENDPOINT_V2_GATED_V1 END ==="
i0 = txt.find(BEGIN)
i1 = txt.find(END)
if i0 < 0 or i1 < 0 or i1 < i0:
    raise SystemExit("No encuentro el bloque PLAN_REAL_ENDPOINT_V2_GATED_V1 (BEGIN/END).")

blk = txt[i0:i1]

# Fix any broken REAL_V2 START content line(s) inside this block
# 1) replace an unterminated multiline string: "content": "REAL_V2 START<newline>"
blk2, n = re.subn(
    r'("content"\s*:\s*)"REAL_V2 START[\s\S]*?"\s*',
    r'\1"REAL_V2 START\\n"',
    blk,
    count=1
)

# If not matched, still normalize any content value containing REAL_V2 START to escaped \n
if n == 0:
    blk2 = re.sub(
        r'("content"\s*:\s*)"REAL_V2 START\\?n"\s*',
        r'\1"REAL_V2 START\\n"',
        blk
    )

txt2 = txt[:i0] + blk2 + txt[i1:]
p.write_text(txt2, encoding="utf-8")
print("OK: plan_real_v2 content normalized to literal 'REAL_V2 START\\\\n'")
